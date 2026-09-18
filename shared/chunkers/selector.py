# src/ingestion_service/core/chunkers/selector.py

from typing import Any, Dict
from shared.chunkers.base import BaseChunker
from shared.chunkers.text import TextChunker


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
    VERSION = "heuristic-v1"

    # Registry: name → instance
    _registry: dict[str, BaseChunker] = {
        "fixed_char": TextChunker(chunk_strategy="simple"),
        "sentence": TextChunker(chunk_strategy="sentence"),
        "paragraph": TextChunker(chunk_strategy="paragraph"),
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
        """
        if isinstance(content, str):
            if len(content) < 2000:
                return cls.get_chunker("sentence"), {"chunk_size": 200, "overlap": 20}
            elif len(content) < 10000:
                return cls.get_chunker("paragraph"), {"chunk_size": 500, "overlap": 50}
            else:
                return cls.get_chunker("fixed_char"), {
                    "chunk_size": 1000,
                    "overlap": 100,
                }

        # Default for other modalities (audio, video, images)
        return cls.get_chunker("fixed_char"), {"chunk_size": 500, "overlap": 50}
