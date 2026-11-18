"""Capacity admission for ordinary RAG at the resolved provider boundary."""

import httpx
from litellm.llms.ollama.completion.transformation import OllamaConfig
from pydantic import BaseModel, Field


class RagCapacity(BaseModel):
    enlarged: bool
    output_reserve_tokens: int = Field(gt=0)
    evidence_passages: list[str] | None = None


class OllamaProfile(BaseModel):
    """Operator-calibrated for one endpoint, digest and template."""

    model: str
    api_base: str
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    window_tokens: int = Field(gt=0)
    template_overhead_tokens: int = Field(ge=0)


class CapacityError(Exception):
    pass


async def check_candidate(candidate, messages, request, profile, fallback):
    if profile is None:
        if fallback or request.enlarged:
            raise CapacityError("candidate has no verified capacity profile")
        return {}, {"method": "unknown_legacy_primary"}
    name = candidate.model.removeprefix("ollama/")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            tags = await client.get(f"{profile.api_base.rstrip('/')}/api/tags")
            tags.raise_for_status()
            pinned = any(
                row.get("name") == name and row.get("digest") == profile.digest
                for row in tags.json()["models"]
            )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise CapacityError("could not verify configured model digest") from exc
    if not pinned:
        raise CapacityError("configured model digest unavailable")
    # Use the same LiteLLM Ollama transform as dispatch, including role wrappers.
    wire = OllamaConfig().transform_request(name, messages, {}, {}, {})
    prompt_bytes = len(wire["prompt"].encode("utf-8"))
    bound = prompt_bytes + profile.template_overhead_tokens
    if bound + request.output_reserve_tokens > profile.window_tokens:
        raise CapacityError(
            "rendered prompt and output reserve exceed candidate window"
        )
    return {
        "num_ctx": profile.window_tokens,
        "max_tokens": request.output_reserve_tokens,
    }, {
        "method": "ollama_utf8_upper_bound",
        "prompt_bytes": prompt_bytes,
        "prompt_token_upper_bound": bound,
        "window_tokens": profile.window_tokens,
        "output_reserve_tokens": request.output_reserve_tokens,
        "digest": profile.digest,
    }
