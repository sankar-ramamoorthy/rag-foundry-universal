from __future__ import annotations
from typing import List

from shared.chunks import Chunk
from shared.embedders.base import BaseEmbedder


class MockEmbedder(BaseEmbedder):
    """
    Deterministic embedder for tests.
    Produces stable vectors based on chunk content length.
    """

    name = "mock"
    dimension = 768

    def embed(self, chunks: List[Chunk]) -> List[List[float]]:
        embeddings: List[List[float]] = []

        for chunk in chunks:
            length = len(str(chunk.content))
            embeddings.append(
                [
                    float(length),
                    float(length % 10),
                    1.0,
                ]
            )

        return embeddings
