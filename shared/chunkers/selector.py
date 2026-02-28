# src/ingestion_service/core/chunkers/selector.py

from typing import Any, Dict
from shared.chunkers.base import BaseChunker
from shared.chunkers.text import TextChunker


class ChunkerFactory:
    """Selects chunker strategy dynamically (potentially LLM-driven)."""

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
