# llm_service/src/core/provider_capture.py
"""
Issue #344: opt-in capture of the exact provider-bound LLM request.

Disabled unless LLM_PROVIDER_CAPTURE_DIR is set. When enabled, every
provider attempt made by llm_client._complete() writes one versioned JSON
record (schema ``llm_provider_capture.v1``) containing:

- application_input: the pre-transform chat messages (prompt template,
  context/query hashes and sizes) -- what llm_service *asked* for.
- provider_request: the body LiteLLM built for the provider, snapshotted
  in its pre-API-call hook (all providers). For the ``ollama/`` route this
  is the flattened ``prompt`` string; for ``ollama_chat/`` the role list.
- wire: for Ollama routes only, the exact HTTP request bytes and the raw
  provider response, recorded by httpx event hooks on a per-attempt client
  passed to LiteLLM. LiteLLM discards the raw ``/api/generate`` response
  (thinking text, done_reason, eval counts), so this is the only place it
  is observable.
- environment: LiteLLM version, llm_service git sha and, for Ollama, the
  server version, model digest/parameters/template hash and the
  post-call ``/api/ps`` entry (effective ``context_length`` / VRAM of the
  loaded runner).

What this cannot see: Ollama's own chat-template rendering and
tokenization happen inside the server. The record names that boundary
rather than claiming visibility past it.

Capture must never change or fail generation: every capture step is
best-effort and swallows its own errors.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import copy
import hashlib
import importlib.metadata
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import httpx
from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger(__name__)

SCHEMA = "llm_provider_capture.v1"
DEFAULT_MAX_BYTES = 8_000_000
_REDACTED = "<redacted>"
_SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "api-key",
    "x-api-key",
    "x-goog-api-key",
    "cookie",
    "set-cookie",
}
_OLLAMA_ROUTES = ("ollama", "ollama_chat")
_PROVIDER_DEFAULTS_NOTE = (
    "Fields absent from options are not sent: their effective values come "
    "from the provider server / Modelfile and are not observed here."
)
_NOT_OBSERVABLE = (
    "Provider-side chat-template rendering and tokenization happen inside "
    "the provider and are not observable from llm_service."
)

# Correlation metadata for the current /generate request (set by the API
# layer from X-Trace-Id / X-Repo-Id / X-Generation-Id headers).
_request_meta: contextvars.ContextVar[Dict[str, Optional[str]]] = (
    contextvars.ContextVar("llm_capture_request_meta", default={})
)
# The record being filled for the current provider attempt.
_current: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "llm_capture_current_attempt", default=None
)


def capture_dir() -> Optional[Path]:
    value = os.getenv("LLM_PROVIDER_CAPTURE_DIR", "").strip()
    return Path(value) if value else None


def is_enabled() -> bool:
    return capture_dir() is not None


def max_bytes() -> int:
    try:
        return int(os.getenv("LLM_PROVIDER_CAPTURE_MAX_BYTES", DEFAULT_MAX_BYTES))
    except ValueError:
        return DEFAULT_MAX_BYTES


def set_request_meta(
    *,
    trace_id: Optional[str] = None,
    repo_id: Optional[str] = None,
    generation_id: Optional[str] = None,
) -> None:
    _request_meta.set(
        {"trace_id": trace_id, "repo_id": repo_id, "generation_id": generation_id}
    )


def sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def redact_headers(headers: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in dict(headers or {}).items():
        out[str(key)] = (
            _REDACTED if str(key).lower() in _SENSITIVE_HEADERS else str(value)
        )
    return out


def route_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else model


# ---------------------------------------------------------------- LiteLLM hook


class ProviderRequestLogger(CustomLogger):
    """Snapshots the provider-bound body in LiteLLM's pre-API-call hook.

    The snapshot must be taken here: LiteLLM later mutates
    ``kwargs["additional_args"]`` (verified on 1.93.0 -- for ``ollama/`` the
    ``complete_input_dict`` key is gone after the call returns)."""

    def log_pre_api_call(self, model, messages, kwargs):  # noqa: D401
        record = _current.get()
        if record is None:
            return
        try:
            additional = kwargs.get("additional_args") or {}
            record["provider_request"] = {
                "source": "litellm.log_pre_api_call",
                "url": str(additional.get("api_base") or ""),
                "headers": redact_headers(additional.get("headers")),
                "body": copy.deepcopy(additional.get("complete_input_dict")),
                "litellm_call_id": kwargs.get("litellm_call_id"),
                "options_note": _PROVIDER_DEFAULTS_NOTE,
            }
        except Exception as e:  # noqa: BLE001
            record.setdefault("capture_errors", []).append(f"pre_api_call: {e}")


_LOGGER = ProviderRequestLogger()


def install_litellm_hook(litellm_module: Any) -> None:
    """Register the hook once (idempotent)."""
    callbacks = list(getattr(litellm_module, "callbacks", None) or [])
    if not any(isinstance(cb, ProviderRequestLogger) for cb in callbacks):
        callbacks.append(_LOGGER)
        litellm_module.callbacks = callbacks


# ------------------------------------------------------------ wire capture


async def _on_request(request: httpx.Request) -> None:
    record = _current.get()
    if record is None:
        return
    try:
        body = request.content
        record["wire"]["exchanges"].append(
            {
                "request": {
                    "method": request.method,
                    "url": str(request.url),
                    "headers": redact_headers(request.headers),
                    "body_text": body.decode("utf-8", errors="replace"),
                    "body_sha256": sha256(body),
                    "body_bytes": len(body),
                },
                "response": None,
            }
        )
    except Exception as e:  # noqa: BLE001
        record.setdefault("capture_errors", []).append(f"wire request: {e}")


async def _on_response(response: httpx.Response) -> None:
    record = _current.get()
    if record is None:
        return
    try:
        raw = await response.aread()
        text = raw.decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(text)
        except ValueError:
            parsed = None
        exchanges = record["wire"]["exchanges"]
        if not exchanges:
            exchanges.append({"request": None, "response": None})
        exchanges[-1]["response"] = {
            "status_code": response.status_code,
            "headers": redact_headers(response.headers),
            "body_text": text,
            "body_json": parsed,
            "body_bytes": len(raw),
        }
    except Exception as e:  # noqa: BLE001
        record.setdefault("capture_errors", []).append(f"wire response: {e}")


def wire_client(timeout: float) -> Any:
    """A fresh LiteLLM AsyncHTTPHandler whose httpx client records the
    exact request bytes and raw response. Per attempt, so it is never
    shared across event loops."""
    from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler

    return AsyncHTTPHandler(
        timeout=timeout,
        event_hooks={"request": [_on_request], "response": [_on_response]},
    )


# ------------------------------------------------------------ environment

_ENV_CACHE: Dict[str, Dict[str, Any]] = {}


async def _ollama_environment(api_base: str, model_name: str) -> Dict[str, Any]:
    """Static model/server facts, cached per (api_base, model). Read-only
    Ollama endpoints only; never triggers inference."""
    key = f"{api_base}|{model_name}"
    if key in _ENV_CACHE:
        return copy.deepcopy(_ENV_CACHE[key])
    env: Dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=3) as client:
        with contextlib.suppress(Exception):
            env["version"] = (
                (await client.get(f"{api_base}/api/version")).json().get("version")
            )
        with contextlib.suppress(Exception):
            tags = (await client.get(f"{api_base}/api/tags")).json().get("models", [])
            match = [
                m
                for m in tags
                if m.get("name") == model_name or m.get("model") == model_name
            ]
            if match:
                env["tag"] = {
                    k: match[0].get(k)
                    for k in ("name", "digest", "size", "modified_at", "details")
                }
        with contextlib.suppress(Exception):
            show = (
                await client.post(f"{api_base}/api/show", json={"model": model_name})
            ).json()
            template = show.get("template") or ""
            env["show"] = {
                "parameters": show.get("parameters"),
                "details": show.get("details"),
                "capabilities": show.get("capabilities"),
                "template_sha256": sha256(template) if template else None,
                "model_info_context_length": next(
                    (
                        v
                        for k, v in (show.get("model_info") or {}).items()
                        if k.endswith(".context_length")
                    ),
                    None,
                ),
            }
    _ENV_CACHE[key] = env
    return copy.deepcopy(env)


async def _ollama_ps(api_base: str, model_name: str) -> Optional[List[Dict[str, Any]]]:
    """Post-call loaded-runner state: the effective context_length and VRAM
    of the runner that just served the request."""
    with contextlib.suppress(Exception):
        async with httpx.AsyncClient(timeout=3) as client:
            models = (await client.get(f"{api_base}/api/ps")).json().get("models", [])
        return [
            {
                k: m.get(k)
                for k in (
                    "name",
                    "digest",
                    "size",
                    "size_vram",
                    "context_length",
                    "expires_at",
                )
            }
            for m in models
            if m.get("name") == model_name or m.get("model") == model_name
        ]
    return None


# ------------------------------------------------------------ attempt record


@contextlib.contextmanager
def _bind(record: Dict[str, Any]) -> Iterator[None]:
    token = _current.set(record)
    try:
        yield
    finally:
        _current.reset(token)


class Attempt:
    """One provider attempt. Use as::

    attempt = Attempt.start(...)
    with attempt.bound():
        response = await litellm.acompletion(...)
    attempt.finish_ok(response) / attempt.finish_error(exc)
    await attempt.write()
    """

    def __init__(self, record: Dict[str, Any], api_base: Optional[str]):
        self.record = record
        self.api_base = api_base
        self._t0 = time.monotonic()

    @classmethod
    def start(
        cls,
        *,
        model: str,
        model_alias: Optional[str],
        api_base: Optional[str],
        messages: List[Dict[str, str]],
        prompt_template: str,
        context: str,
        query: str,
    ) -> "Attempt":
        meta = dict(_request_meta.get() or {})
        record: Dict[str, Any] = {
            "schema": SCHEMA,
            "capture_id": uuid.uuid4().hex,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "trace_id": meta.get("trace_id"),
            "repo_id": meta.get("repo_id"),
            "generation_id": meta.get("generation_id"),
            "attempt": {
                "model": model,
                "model_alias": model_alias,
                "route": route_of(model),
                "api_base": api_base,
            },
            "application_input": {
                "prompt_template": prompt_template,
                "messages": copy.deepcopy(messages),
                "context_bytes": len(context.encode("utf-8")),
                "context_sha256": sha256(context),
                "query_sha256": sha256(query),
            },
            "provider_request": None,
            "wire": {"exchanges": []},
            "result": None,
            "environment": {
                "litellm_version": _litellm_version(),
                "llm_service_git_sha": os.getenv("APP_GIT_SHA", "unknown"),
            },
            "not_observable": _NOT_OBSERVABLE,
        }
        return cls(record, api_base)

    @property
    def wants_wire(self) -> bool:
        return self.record["attempt"]["route"] in _OLLAMA_ROUTES

    def bound(self):
        return _bind(self.record)

    def finish_ok(self, response: Any) -> None:
        with contextlib.suppress(Exception):
            choice = response.choices[0]
            usage = getattr(response, "usage", None)
            self.record["result"] = {
                "status": "ok",
                "latency_ms": round((time.monotonic() - self._t0) * 1000, 1),
                "finish_reason": getattr(choice, "finish_reason", None),
                "content": getattr(choice.message, "content", None),
                "reasoning_content": getattr(choice.message, "reasoning_content", None),
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
                if usage is not None
                else None,
            }

    def finish_error(self, exc: BaseException) -> None:
        self.record["result"] = {
            "status": "error",
            "latency_ms": round((time.monotonic() - self._t0) * 1000, 1),
            "error_type": type(exc).__name__,
            "error": str(exc)[:4000],
        }

    async def write(self) -> Optional[Path]:
        """Best-effort: never raises."""
        try:
            if self.wants_wire and self.api_base:
                model_name = self.record["attempt"]["model"].split("/", 1)[1]
                ollama = await _ollama_environment(self.api_base, model_name)
                ollama["ps_after_call"] = await _ollama_ps(self.api_base, model_name)
                self.record["environment"]["ollama"] = ollama
            if not self.wants_wire:
                self.record["wire"] = None
                self.record["wire_note"] = (
                    "wire capture is implemented for Ollama routes only"
                )
            return await asyncio.to_thread(_write_record, self.record)
        except Exception as e:  # noqa: BLE001
            logger.warning("provider capture write failed: %s", e)
            return None


def _write_record(record: Dict[str, Any]) -> Optional[Path]:
    directory = capture_dir()
    if directory is None:
        return None
    payload = json.dumps(record, ensure_ascii=False, indent=1, default=str)
    limit = max_bytes()
    if len(payload.encode("utf-8")) > limit:
        payload = json.dumps(
            _omit_bodies(record, limit), ensure_ascii=False, indent=1, default=str
        )
    day = record["captured_at"][:10]
    target_dir = directory / day
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{record.get('trace_id') or 'no-trace'}-{record['capture_id']}.json"
    path = target_dir / name
    path.write_text(payload, encoding="utf-8")
    return path


def _omit_bodies(record: Dict[str, Any], limit: int) -> Dict[str, Any]:
    """Over the size limit: drop bulky text explicitly (never silently),
    keeping hashes and sizes so the omission is visible and checkable."""
    slim = copy.deepcopy(record)
    omitted: Dict[str, Any] = {"reason": f"record exceeded {limit} bytes"}
    inputs = slim.get("application_input") or {}
    if inputs.get("messages") is not None:
        omitted["application_input.messages_sha256"] = sha256(
            json.dumps(inputs["messages"], ensure_ascii=False)
        )
        inputs["messages"] = None
    request = slim.get("provider_request") or {}
    if request.get("body") is not None:
        omitted["provider_request.body_sha256"] = sha256(
            json.dumps(request["body"], ensure_ascii=False)
        )
        request["body"] = None
    wire = slim.get("wire") or {}
    for i, exchange in enumerate(wire.get("exchanges") or []):
        for side in ("request", "response"):
            part = exchange.get(side) or {}
            if part.get("body_text") is not None:
                omitted[f"wire.exchanges[{i}].{side}.body_sha256"] = sha256(
                    part["body_text"]
                )
                part["body_text"] = None
                part.pop("body_json", None)
    slim["omitted"] = omitted
    return slim


def _litellm_version() -> Optional[str]:
    with contextlib.suppress(Exception):
        return importlib.metadata.version("litellm")
    return None
