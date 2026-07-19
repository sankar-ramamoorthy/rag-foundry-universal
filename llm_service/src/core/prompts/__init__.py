# llm_service/src/core/prompts/__init__.py
"""
Versioned prompt templates (WP-M1).

The template version travels in every /generate response
(`prompt_template`) so eval runs stay reproducible. Changing the prompt
means adding rag_answer.v2.txt and bumping PROMPT_TEMPLATE_VERSION —
never editing v1 in place.
"""
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

PROMPT_TEMPLATE_VERSION = "rag_answer.v1"

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache
def _system_prompt() -> str:
    return (_PROMPTS_DIR / f"{PROMPT_TEMPLATE_VERSION}.txt").read_text(
        encoding="utf-8"
    ).strip()


def build_messages(context: str, query: str) -> List[Dict[str, str]]:
    """System prompt + user message carrying the retrieved context."""
    return [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{query}"},
    ]
