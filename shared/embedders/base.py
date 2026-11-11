from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

from shared.chunks import Chunk


class EmbeddingInputTooLong(RuntimeError):
    """Inputs the model rejected as longer than its context (CI-06, #337).

    ``positions`` are indexes into the ``chunks`` passed to ``embed``.
    ``vectors`` holds the embedding for every other position (``None`` at the
    rejected ones) so callers can split only the rejected passages without
    re-embedding the rest.
    """

    def __init__(
        self, positions: Sequence[int], vectors: Sequence[Optional[List[float]]]
    ):
        self.positions = list(positions)
        self.vectors = list(vectors)
        super().__init__(
            f"{len(self.positions)} embedding input(s) exceed the model context"
        )


class BaseEmbedder(ABC):
    """Abstract interface for embedding chunk content."""

    name: str = "base"

    @abstractmethod
    def embed(
        self, chunks: List[Chunk], *, truncate_overflow: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for chunks.

        :param chunks: List of Chunk objects
        :param truncate_overflow: queries only. When False (the default, used
            for every stored passage) an input longer than the model context
            raises :class:`EmbeddingInputTooLong`; it is never shortened. When
            True the provider may encode a truncated prefix, and the chunk is
            marked ``metadata["embedding_input"]["truncated"] = True``.
        :return: List of embedding vectors
        """
        raise NotImplementedError
