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
    # exceptions (e.g. a native crash bypasses it entirely -- see the
    # tree-sitter==0.26.0 segfault finding in the WP-L5 doc section) -- it
    # is a crash safety net, not proof of semantic equivalence. Semantic
    # parity is established separately by the A/B parity harness
    # (tests/codebase/test_python_parity_harness.py).
    #
    # Stage B (this default): PYTHON_TREESITTER_ENABLED=True is now the
    # production default -- the parity harness is green (structural +
    # semantic, zero diff) on the committed fixture and 6 real service
    # codebases in this monorepo, and PYTHON_TREESITTER_AUTO_FALLBACK
    # stays on indefinitely as the belt-and-suspenders safety net.
    # PythonASTExtractor is NOT deleted -- it remains the rollback target;
    # set PYTHON_TREESITTER_ENABLED=False to revert to it with no code
    # change, no redeploy of anything but this env var.
    PYTHON_TREESITTER_ENABLED: bool = True
    PYTHON_TREESITTER_AUTO_FALLBACK: bool = True  # When True, exceptions
                                                   # from the tree-sitter
                                                   # Python extractor are
                                                   # caught and retried with
                                                   # PythonASTExtractor
                                                   # automatically; set
                                                   # False only to surface
                                                   # raw failures, e.g. when
                                                   # re-running the parity
                                                   # harness.

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


def reset_settings_cache():
    get_settings.cache_clear()
