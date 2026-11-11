# src/ingestion_service/core/chunkers/selector.py

from typing import Any, Dict
from shared.chunkers.base import BaseChunker
from shared.chunkers.text import TextChunker
from shared.embedders.input_contract import (
    EMBEDDING_INPUT_MAX_CHARS,
    EMBEDDING_INPUT_MAX_EST_TOKENS,
    EMBEDDING_INPUT_OVERLAP_CHARS,
)

# Every strategy below receives these so no chunk exceeds one embedding input.
_FIT = {
    "max_chars": EMBEDDING_INPUT_MAX_CHARS,
    "max_tokens": EMBEDDING_INPUT_MAX_EST_TOKENS,
}


class ChunkerFactory:
    """Selects chunker strategy dynamically (potentially LLM-driven)."""

    # Issue #196 (R4): a stable identifier for the *selection heuristic and
    # registry* as a whole, not a per-file resolved strategy name.
    # choose_strategy() picks a strategy per file based on content length,
    # so two different files in the same ingestion can legitimately resolve
    # to different chunk_strategy values even though the config itself
    # hasn't changed. The incremental-ingestion reuse gate needs a single,
    # ingestion-wide "did the chunking config change" signal independent of
    # any one file's content -- bump this whenever the heuristic thresholds
    # or the registry (_registry) change in a way that could alter how an
    # unchanged file gets chunked.
    #
    # CI-06 (#337): v2 sizes every passage to the embedding-input contract
    # and chunks repository artifacts as exact line windows. "heuristic-v1"
    # passages were cut at 800 characters by the embedder, so they must not
    # be reused.
    VERSION = "budgeted-v2"

    # Registry: name → instance
    _registry: dict[str, BaseChunker] = {
        "fixed_char": TextChunker(chunk_strategy="simple"),
        "sentence": TextChunker(chunk_strategy="sentence"),
        "paragraph": TextChunker(chunk_strategy="paragraph"),
        "line_window": TextChunker(chunk_strategy="line_window"),
    }

    @classmethod
    def get_chunker(cls, strategy_name: str = "fixed_char") -> BaseChunker:
        if strategy_name not in cls._registry:
            raise ValueError(f"Chunker strategy '{strategy_name}' not found.")
        return cls._registry[strategy_name]

    @classmethod
    def choose_strategy(cls, content: Any, **context) -> tuple[BaseChunker, Dict]:
        """
        Heuristic to choose a chunk strategy based on content type and length.
        Returns (chunker instance, chunk_strategy parameters)

        ``source_type="code"`` (repository artifacts) always uses exact line
        windows: every passage is a verbatim slice of the artifact and the
        passages cover all of it (CI-06). Other text keeps the length
        heuristic, with each unit capped to one embedding input.
        """
        if isinstance(content, str):
            if context.get("source_type") == "code":
                return cls.get_chunker("line_window"), {
                    "chunk_size": EMBEDDING_INPUT_MAX_CHARS,
                    "overlap": EMBEDDING_INPUT_OVERLAP_CHARS,
                    **_FIT,
                }
            if len(content) < 2000:
                return cls.get_chunker("sentence"), {
                    "chunk_size": 200, "overlap": 20, **_FIT,
                }
            elif len(content) < 10000:
                return cls.get_chunker("paragraph"), {
                    "chunk_size": 500, "overlap": 50, **_FIT,
                }
            else:
                return cls.get_chunker("fixed_char"), {
                    "chunk_size": EMBEDDING_INPUT_MAX_CHARS,
                    "overlap": EMBEDDING_INPUT_OVERLAP_CHARS,
                    **_FIT,
                }

        # Default for other modalities (audio, video, images)
        return cls.get_chunker("fixed_char"), {"chunk_size": 500, "overlap": 50}
