# ingestion_service/src/core/config.py

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    VECTOR_STORE_SERVICE_URL: str = "http://vector_store_service:8002"
    EMBEDDING_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"

    # Coderag upgrade
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large:latest"
    OLLAMA_BATCH_SIZE: int = 50
    VECTOR_DIMENSION: int = 1024

    # Universal feature
    DOCLING_ENABLED: bool = True   # When False → PyMuPDF fallback for PDF

    # WP-L5 (DOCS/audit/03-Multi-Language-Graph-Plan.md, issue #134): Python
    # tree-sitter extractor rollout. PYTHON_TREESITTER_ENABLED selects
    # which extractor RepoGraphBuilder registers for `.py` files;
    # PYTHON_TREESITTER_AUTO_FALLBACK controls whether an exception from
    # the tree-sitter path is caught and silently retried with the
    # legacy ast extractor at ingest time (no code revert needed to roll
    # back in production -- see repo_graph_builder.py's
    # _select_extractor / _PythonExtractorProxy for the rollback
    # mechanism this flag drives). NOTE: this fallback catches only parse
    # exceptions -- it is a crash safety net, not proof of semantic
    # equivalence. Semantic parity is established separately by the A/B
    # parity harness (tests/codebase/test_python_parity_harness.py).
    PYTHON_TREESITTER_ENABLED: bool = False   # Stage A default: opt-in.
                                               # Flip to True as the Stage B
                                               # default once the parity
                                               # harness is green on >=5
                                               # real repos.
    PYTHON_TREESITTER_AUTO_FALLBACK: bool = True  # When True, exceptions
                                                   # from the tree-sitter
                                                   # Python extractor are
                                                   # caught and retried with
                                                   # PythonASTExtractor
                                                   # automatically; set
                                                   # False only to surface
                                                   # raw failures during the
                                                   # parity/rollout window.

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


def reset_settings_cache():
    get_settings.cache_clear()
