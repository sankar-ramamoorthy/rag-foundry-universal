# llm_service/src/core/llm_client.py
# WP-M1: LiteLLM core swap. Any LiteLLM-supported model works via the
# provider/model params; Ollama remains the default; llm_service stays
# the seam owning prompts and model policy — other services never call
# vendors directly.
# WP-M2: provider outages degrade gracefully — per-attempt LiteLLM
# retries with backoff, then the registry's fallback chain; only when
# every candidate fails does the request error (503 at the API layer).
import logging

import litellm

from src.core.model_registry import ResolvedModel, get_registry
from src.core.prompts import PROMPT_TEMPLATE_VERSION, build_messages

logger = logging.getLogger(__name__)

# WP-M2: retries within one candidate model before falling back.
# LiteLLM applies exponential backoff between attempts.
NUM_RETRIES = 2


class AllProvidersFailedError(RuntimeError):
    """Every model in the fallback chain failed (WP-M2 → 503)."""

    def __init__(self, attempted: list[str], last_error: Exception):
        self.attempted = attempted
        self.last_error = last_error
        super().__init__(
            "All configured LLM providers failed. "
            f"Tried, in order: {', '.join(attempted)}. "
            f"Last error: {last_error}. "
            "Check provider availability, API keys, and models.yaml."
        )


async def generate_completion(
    *,
    context: str,
    query: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    registry = get_registry()
    primary = registry.resolve(provider, model)
    chain = registry.fallback_chain(primary)

    last_error: Exception | None = None
    for position, candidate in enumerate(chain):
        try:
            result = await _complete(candidate, context=context, query=query)
        except Exception as e:  # noqa: BLE001 - any provider error → next
            last_error = e
            logger.warning(
                "LLM candidate failed, %s remaining",
                len(chain) - position - 1,
                extra={"failed_model": candidate.model, "error": str(e)},
            )
            continue

        if position > 0:
            # structured circuit-note: a fallback fired
            logger.warning(
                "LLM fallback fired",
                extra={
                    "fallback_from": primary.model,
                    "fallback_to": candidate.model,
                },
            )
            result["fallback_from"] = primary.model
        return result

    assert last_error is not None
    raise AllProvidersFailedError([c.model for c in chain], last_error)


async def _complete(
    resolved: ResolvedModel, *, context: str, query: str
) -> dict:
    kwargs: dict = {
        "model": resolved.model,
        "messages": build_messages(context, query),
        "timeout": resolved.timeout,
        "num_retries": NUM_RETRIES,
    }
    if resolved.api_base:
        kwargs["api_base"] = resolved.api_base

    response = await litellm.acompletion(**kwargs)

    content = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    usage_dict = (
        {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        if usage is not None
        else None
    )

    return {
        # kept for backward compatibility with the pre-LiteLLM shape
        "provider": resolved.model.split("/", 1)[0],
        "model": resolved.model,
        "model_alias": resolved.alias,
        "response": content.strip(),
        "usage": usage_dict,
        "prompt_template": PROMPT_TEMPLATE_VERSION,
    }
