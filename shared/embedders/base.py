from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List

from shared.chunks import Chunk


class BaseEmbedder(ABC):
    """Abstract interface for embedding chunk content."""

    name: str = "base"

    @abstractmethod
    def embed(self, chunks: List[Chunk]) -> List[List[float]]:
        """
        Generate embeddings for chunks.

        :param chunks: List of Chunk objects
        :return: List of embedding vectors
        """
        raise NotImplementedError
