# rag_orchestrator/src/core/config.py
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # -------------------------------------------------
    # Embedding configuration
    # -------------------------------------------------
    EMBEDDING_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    #OLLAMA_EMBED_MODEL: str = "nomic-embed-text:v1.5"
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large:latest"

    OLLAMA_BATCH_SIZE: int = 50

    # -------------------------------------------------
    # Retrieval expansion limits (issue #30 Part 3)
    # -------------------------------------------------
    # Cap on graph-expanded documents fetched per query; ranked expanded
    # docs beyond this are reported as considered-but-unused.
    MAX_EXPANDED_DOCS: int = 20
    # Chunks fetched per expanded doc — expansion is context, not the
    # primary hit, so this stays well below the seed top_k.
    EXPANDED_DOC_CHUNKS: int = 3
    # Overall chunk cap handed to the agent adapter (was 9999).
    MAX_TOTAL_CHUNKS: int = 50
    # Concurrency of search-by-doc fetches for expanded docs.
    MAX_CONCURRENT_DOC_FETCHES: int = 8

    # -------------------------------------------------
    # Doc-type-aware seed tie-break (issue #142, fix for #141)
    # -------------------------------------------------
    # Off by default (Stage A, mirrors WP-L5's rollout-flag precedent):
    # this changes retrieval ranking, which this repo's Constitution
    # gates on measured evaluation evidence before becoming the default
    # (see DOCS/audit/09-Retrieval-Technique-Decision-Gates.md and the
    # DOCS/test_results/ entry for issue #141). When False, hybrid_retrieve
    # behaves exactly as before this feature existed -- k=top_k, no
    # reordering.
    DOC_TYPE_TIE_BREAK_ENABLED: bool = False
    # When enabled, the seed vector search over-fetches to this many
    # candidates (instead of just top_k) before doc-type-aware selection
    # narrows back down to top_k. This is load-bearing, not cosmetic:
    # confirmed live against issue #141's exact reproduction query that
    # the real base.py answer chunk is excluded from the DB's own
    # similarity-ordered LIMIT at k=20, and only enters the result set at
    # k=100 -- a client-side reorder of an already-narrow top-20 cannot
    # recover a candidate that was never fetched. 100 is an empirically
    # validated floor for that one case, not a tuned optimum; revisit
    # with the evaluation evidence in DOCS/test_results/.
    DOC_TYPE_TIE_BREAK_SEED_POOL_SIZE: int = 100
    # Cosine-similarity score band (vector_store_service returns
    # 1 - cosine_distance, range 0-1, higher = more similar) within which
    # two candidates are treated as a near-tie for tie-break purposes.
    # Conservative starting value -- needs empirical tuning against real
    # score distributions, not derived from a live measurement the way
    # SEED_POOL_SIZE above was.
    DOC_TYPE_TIE_BREAK_EPSILON: float = 0.03
    # document_nodes.doc_type values considered "implementation" for
    # tie-break purposes -- preferred over everything else (markdown_
    # section, markdown_module, etc.) within an epsilon-band near-tie.
    # Keep in sync with the doc_type strings each extractor actually
    # writes (ingestion_service/src/core/extractors/*).
    IMPLEMENTATION_DOC_TYPES: frozenset[str] = frozenset({
        "python source",
        "rust source",
        "java source",
        "typescript source",
        "javascript source",
    })

    # -------------------------------------------------
    # Service URLs (Docker service names)
    # -------------------------------------------------
    VECTOR_STORE_URL: str = "http://vector_store_service:8002"
    LLM_SERVICE_URL: str = "http://llm_service:8000"
    INGESTION_SERVICE_URL: str = "http://ingestion_service:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings."""
    return Settings()


def reset_settings_cache():
    """Clear cached settings for testing or reload."""
    get_settings.cache_clear()
