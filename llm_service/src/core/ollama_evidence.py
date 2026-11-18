"""Admit whole passages against the runner used for this Custom generation."""

import asyncio
import hashlib
import logging
import re
from contextlib import nullcontext
from time import monotonic
from typing import cast

import httpx
from litellm.llms.ollama.completion.transformation import OllamaConfig
from litellm.types.llms.openai import AllMessageValues

from src.core import provider_capture
from src.core.config import MAX_TRANSIENT_RETRIES, RETRY_BACKOFF_BASE_SECONDS
from src.core.prompts import PROMPT_TEMPLATE_VERSION, build_messages
from src.core.rag_capacity import CapacityError

_client = httpx.AsyncClient
logger = logging.getLogger(__name__)
# Only immutable tokenizer facts are cached. The live runner can change at
# any time, including when a different client asks for a different num_ctx.
_verified_until: dict[tuple[str, str, str], float] = {}


def _name(name):
    name = name.casefold()
    return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"


async def _runner(client, name):
    response = await client.get("/api/ps")
    response.raise_for_status()
    for row in response.json()["models"]:
        if _name(row["name"]) == _name(name):
            window = row.get("context_length")
            digest = str(row.get("digest", "")).removeprefix("sha256:")
            if (
                type(window) is not int
                or window <= 0
                or not re.fullmatch("[0-9a-f]{64}", digest)
            ):
                raise CapacityError("Ollama runner lacks a verified digest or window")
            return digest, window
    return None


async def _verify_tokenizer(client, name, digest):
    key = (str(client.base_url), name, digest)
    if _verified_until.get(key, 0) > monotonic():
        return
    response = await client.post("/api/show", json={"model": name})
    response.raise_for_status()
    info = response.json()["model_info"]
    if info.get("tokenizer.ggml.model") != "gpt2" or info.get(
        "tokenizer.ggml.pre"
    ) not in {"qwen2", "dbrx", "llama-bpe"}:
        raise CapacityError(
            "automatic admission requires a supported byte-BPE tokenizer"
        )
    expired = [k for k, expiry in _verified_until.items() if expiry <= monotonic()]
    for k in expired:
        del _verified_until[k]
    _verified_until[key] = monotonic() + 60


def _flatten(name, context, query):
    messages = cast(list[AllMessageValues], build_messages(context, query))
    return OllamaConfig().transform_request(name, messages, {}, {}, {})["prompt"]


async def _render(client, body):
    response = await client.post(
        "/api/generate", json={**body, "_debug_render_only": True}
    )
    response.raise_for_status()
    data = response.json()
    rendered = (data.get("_debug_info") or {}).get("rendered_template")
    if (
        data.get("done") is not False
        or not isinstance(rendered, str)
        or body["prompt"] not in rendered
    ):
        raise CapacityError("Ollama did not render the complete input prompt")
    return rendered


# Go's text/template emits the last message (the supplied prompt) verbatim.
# Rendering the frozen string this way keeps Ollama's normal response parser.
_VERBATIM = (
    '{{ $last := "" }}{{ range .Messages }}{{ $last = .Content }}{{ end }}{{ $last }}'
)


async def _fit(client, body, query, request, profile, window):
    name = body["model"]
    passages = request.evidence_passages
    # For byte-level BPE each input byte contributes at most one
    # token; allow an initial space and BOS/EOS tokens as configured by GGUF.
    overhead = max(3, profile.template_overhead_tokens) if profile else 3
    empty = await _render(
        client, {**body, "prompt": _flatten(name, "", query)}
    )
    limit = window - overhead - request.output_reserve_tokens
    allowance = limit - len(empty.encode())
    if allowance < 0:
        raise CapacityError("fixed prompt and output reserve exceed candidate window")
    delivered = []
    used = 0
    for passage in passages:
        size = len(passage.encode()) + (2 if delivered else 0)
        if used + size > allowance:
            break
        delivered.append(passage)
        used += size
    if passages and not delivered:
        raise CapacityError("first complete evidence passage exceeds candidate window")
    evidence = "\n\n".join(delivered)
    context = evidence
    flattened = _flatten(name, context, query)
    if any(
        message["content"] not in flattened
        for message in build_messages(context, query)
    ):
        raise CapacityError("Ollama transform omitted application input")
    prompt = await _render(client, {**body, "prompt": flattened})
    size = len(prompt.encode())
    if size > limit:
        raise CapacityError("final rendered prompt exceeds candidate window")
    return (
        context,
        prompt,
        {
            "method": "ollama_profile" if profile else "ollama_rendered_utf8",
            "model": "ollama/" + name,
            "window_tokens": window,
            "prompt_bytes": size,
            "prompt_token_upper_bound": size + overhead,
            "output_reserve_tokens": request.output_reserve_tokens,
            "evidence_allowance_bytes": allowance,
            "delivered_passage_count": len(delivered),
            "delivered_evidence_sha256": hashlib.sha256(evidence.encode()).hexdigest(),
        },
    )


async def _generate(client, body) -> dict:
    attempt = 0
    while True:
        try:
            response = await client.post("/api/generate", json=body)
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and (
                exc.response.status_code < 500 and exc.response.status_code != 429
            ):
                raise
            if attempt >= MAX_TRANSIENT_RETRIES:
                raise
            await asyncio.sleep(RETRY_BACKOFF_BASE_SECONDS * 2**attempt)
            attempt += 1


async def _dispatch(client, candidate, body, context, query):
    capture = None
    if provider_capture.is_enabled():
        try:
            capture = provider_capture.Attempt.start(
                model=candidate.model,
                model_alias=candidate.alias,
                api_base=candidate.api_base,
                messages=build_messages(context, query),
                prompt_template=PROMPT_TEMPLATE_VERSION,
                context=context,
                query=query,
            )
            capture.record["provider_request"] = {
                "source": "native Ollama /api/generate",
                "body": body,
            }
            capture.record["not_observable"] = "Token IDs are internal to Ollama."
        except Exception:
            logger.exception("Could not initialize native Ollama capture")
            capture = None
    try:
        with capture.bound() if capture else nullcontext():
            data = await _generate(client, body)
        if capture:
            capture.finish_ollama(data)
        return data
    except Exception as exc:
        if capture:
            capture.finish_error(exc)
        raise
    finally:
        if capture:
            capture.schedule()


async def _discover(client, name, profile):
    version = await client.get("/api/version")
    version.raise_for_status()
    if version.json().get("version") != "0.32.1":
        raise CapacityError("render-only admission requires verified Ollama 0.32.1")
    runner = await _runner(client, name)
    if runner is None:
        # An empty generate loads the model using the endpoint's default
        # context. The trained maximum from /show is not the runner window.
        load = await client.post(
            "/api/generate", json={"model": name, "stream": False}
        )
        load.raise_for_status()
        runner = await _runner(client, name)
    if runner is None:
        raise CapacityError("Ollama did not report a loaded runner")
    digest, window = runner
    if profile:
        if profile.digest != digest:
            raise CapacityError("configured model digest changed")
        window = min(window, profile.window_tokens)
    else:
        await _verify_tokenizer(client, name, digest)
    return digest, window


async def complete_evidence(candidate, query, request, profile):
    if not candidate.model.startswith("ollama/") or not candidate.api_base:
        raise CapacityError("automatic evidence admission requires an Ollama endpoint")
    name = candidate.model.removeprefix("ollama/")
    hooks = provider_capture.wire_hooks() if provider_capture.is_enabled() else {}
    async with _client(
        base_url=candidate.api_base, timeout=candidate.timeout, event_hooks=hooks
    ) as client:
        digest, window = await _discover(client, name, profile)
        body = {
            "model": name,
            "stream": False,
            "truncate": False,
            "shift": False,
            "options": {
                "num_ctx": window,
                "num_predict": request.output_reserve_tokens,
            },
        }
        context, prompt, admission = await _fit(
            client, body, query, request, profile, window
        )
        body.update(prompt=prompt, template=_VERBATIM)
        if await _render(client, body) != prompt:
            raise CapacityError("Ollama could not reproduce the admitted prompt")
        data = await _dispatch(client, candidate, body, context, query)
        after = await _runner(client, name)
        if after is None or after[0] != digest or after[1] < window:
            raise CapacityError("Ollama runner changed during generation")
        actual = data.get("prompt_eval_count")
        completion = data.get("eval_count")
        if (
            data.get("done") is not True
            or _name(data.get("model", "")) != _name(name)
            or type(actual) is not int
            or not 0 < actual <= admission["prompt_token_upper_bound"]
            or type(completion) is not int
            or not 0 <= completion <= request.output_reserve_tokens
        ):
            raise CapacityError("Ollama did not confirm the admitted generation")
        admission["digest"] = digest
        if not data.get("response", "").strip():
            raise CapacityError("Ollama returned no answer within the output reserve")
        return {
            "provider": "ollama",
            "model": candidate.model,
            "model_alias": candidate.alias,
            "response": data["response"].strip(),
            "usage": {
                "prompt_tokens": actual,
                "completion_tokens": completion,
                "total_tokens": actual + completion,
            },
            "cost_usd": None,
            "prompt_template": PROMPT_TEMPLATE_VERSION,
        }, admission
