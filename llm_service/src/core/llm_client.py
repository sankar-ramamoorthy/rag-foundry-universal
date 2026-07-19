# llm_service/src/core/llm_client.py
# WP-M1: LiteLLM core swap. Any LiteLLM-supported model works via the
# provider/model params; Ollama remains the default; llm_service stays
# the seam owning prompts and model policy — other services never call
# vendors directly.
import logging

import litellm

from src.core.model_registry import ResolvedModel, get_registry
from src.core.prompts import PROMPT_TEMPLATE_VERSION, build_messages

logger = logging.getLogger(__name__)


async def generate_completion(
    *,
    context: str,
    query: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    resolved = get_registry().resolve(provider, model)
    return await _complete(resolved, context=context, query=query)


async def _complete(
    resolved: ResolvedModel, *, context: str, query: str
) -> dict:
    kwargs: dict = {
        "model": resolved.model,
        "messages": build_messages(context, query),
        "timeout": resolved.timeout,
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
