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

# WP-M8 (issue #125): retries of a *transient* error (rate-limit,
# provider-unavailable, connection/timeout) on the same candidate model,
# before generate_completion()'s fallback chain moves on. A permanent
# error (bad model name, auth, malformed request) is never retried here
# regardless of these settings -- see llm_client._TRANSIENT_LITELLM_ERRORS.
MAX_TRANSIENT_RETRIES: int = int(os.getenv("MAX_TRANSIENT_RETRIES", "2"))
RETRY_BACKOFF_BASE_SECONDS: float = float(
    os.getenv("RETRY_BACKOFF_BASE_SECONDS", "0.5")
)
