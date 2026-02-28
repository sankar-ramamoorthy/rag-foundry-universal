from __future__ import annotations

import uuid
from typing import List

from shared.chunks import Chunk

# from shared.embedders.factory import get_embedder
from shared.embedders.base import BaseEmbedder


def embed_query(query: str, embedder: BaseEmbedder) -> List[float]:
    """
    Embed a single query string using the provided embedder.

    This is a thin helper that:
    - Wraps the query in a temporary Chunk
    - Uses the given embedder
    - Returns a single embedding vector

    No persistence, no chunking, no side effects.
    """
    query_chunk = Chunk(
        chunk_id=f"query:{uuid.uuid4()}",
        content=query,
        metadata={"type": "query"},
    )

    embeddings = embedder.embed([query_chunk])

    if not embeddings or len(embeddings) != 1:
        raise RuntimeError(f"Expected 1 embedding for query, got {len(embeddings)}")

    return embeddings[0]
