# llm_service/src/core/llm_client.py
# WP-M1: LiteLLM core swap. Any LiteLLM-supported model works via the
# provider/model params; Ollama remains the default; llm_service stays
# the seam owning prompts and model policy — other services never call
# vendors directly.
# WP-M2: provider outages degrade gracefully — retries within one
# candidate model (WP-M8: only for transient errors, with backoff), then
# the registry's fallback chain; only when every candidate fails does the
# request error (503 at the API layer).
import asyncio
import logging

import litellm

from src.core.config import MAX_TRANSIENT_RETRIES, RETRY_BACKOFF_BASE_SECONDS
from src.core.model_registry import ResolvedModel, get_registry
from src.core.prompts import PROMPT_TEMPLATE_VERSION, build_messages

logger = logging.getLogger(__name__)

# WP-M8 (issue #125): litellm's own num_retries retried every exception
# identically -- including permanent ones (e.g. a 404 "model not found"
# on a mistyped/unpulled model burned 2 pointless retries, confirmed
# live). Disabled here; _acompletion_with_backoff below owns retries and
# only retries the errors that can plausibly succeed on a retry.
LITELLM_NUM_RETRIES = 0

# Errors worth retrying the *same* candidate model for: the request
# reached a real provider and got a transient failure (shared free-tier
# rate limits, momentary unavailability, a dropped connection/timeout).
# Deliberately excludes litellm.NotFoundError, AuthenticationError,
# BadRequestError, and anything else -- those can never succeed on retry,
# so generate_completion()'s fallback loop should move to the next
# candidate immediately instead of waiting through a doomed retry.
_TRANSIENT_LITELLM_ERRORS = (
    litellm.RateLimitError,
    litellm.ServiceUnavailableError,
    litellm.APIConnectionError,
    litellm.Timeout,
    litellm.InternalServerError,
)


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


async def _acompletion_with_backoff(kwargs: dict):
    """WP-M8 (issue #125): retry only transient errors on this candidate
    model, with exponential backoff, before letting the caller's
    exception propagate to generate_completion()'s fallback loop."""
    attempt = 0
    while True:
        try:
            return await litellm.acompletion(**kwargs)
        except _TRANSIENT_LITELLM_ERRORS as e:
            if attempt >= MAX_TRANSIENT_RETRIES:
                raise
            delay = RETRY_BACKOFF_BASE_SECONDS * (2**attempt)
            logger.warning(
                "Transient LLM error, retrying same candidate after backoff",
                extra={
                    "model": kwargs["model"],
                    "attempt": attempt + 1,
                    "delay_s": delay,
                    "error": str(e),
                },
            )
            await asyncio.sleep(delay)
            attempt += 1


async def _complete(
    resolved: ResolvedModel, *, context: str, query: str
) -> dict:
    kwargs: dict = {
        "model": resolved.model,
        "messages": build_messages(context, query),
        "timeout": resolved.timeout,
        "num_retries": LITELLM_NUM_RETRIES,
    }
    if resolved.api_base:
        kwargs["api_base"] = resolved.api_base

    response = await _acompletion_with_backoff(kwargs)

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

    # WP-M4 (issue #46 follow-up), scoped down: per-request cost visibility
    # ahead of substantial cloud-model use, without the Prometheus/Grafana
    # dashboard (WP-E5, not built) or per-request DB persistence (would
    # need ingestion_service, the only service allowed DB access) the full
    # plan doc envisioned. completion_cost() has no pricing data for many
    # models (local Ollama, some free-tier cloud models) -- that's a
    # normal, expected case, not an error, so it degrades to None rather
    # than failing the request.
    try:
        cost_usd = litellm.completion_cost(completion_response=response)
    except Exception:
        cost_usd = None

    logger.info(
        "LLM completion",
        extra={
            "model": resolved.model,
            "model_alias": resolved.alias,
            "usage": usage_dict,
            "cost_usd": cost_usd,
        },
    )

    return {
        # kept for backward compatibility with the pre-LiteLLM shape
        "provider": resolved.model.split("/", 1)[0],
        "model": resolved.model,
        "model_alias": resolved.alias,
        "response": content.strip(),
        "usage": usage_dict,
        "cost_usd": cost_usd,
        "prompt_template": PROMPT_TEMPLATE_VERSION,
    }
