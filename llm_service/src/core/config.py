import os

DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi4-mini:latest")
VECTOR_DIMENSION: int = 1024

# WP-M1: default LiteLLM request timeout in seconds; per-alias overrides
# live in models.yaml. API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...)
# are env-only and read natively by LiteLLM — never accepted in requests.
LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "120"))

# WP-M6: how long a provider's discovered model catalog is cached before
# being re-fetched. The catalog is advisory (visibility/filtering only,
# never a gate on resolve()), so a generous TTL is fine.
MODEL_CATALOG_TTL_SECONDS: float = float(
    os.getenv("MODEL_CATALOG_TTL_SECONDS", "3600")
)
