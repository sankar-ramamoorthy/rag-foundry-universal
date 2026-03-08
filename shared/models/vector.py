# shared/models/vector.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Dict, Optional


@dataclass
class VectorMetadata:
    ingestion_id: str
    chunk_id: str
    chunk_index: int
    chunk_strategy: str
    chunk_text: str
    source_metadata: Optional[Dict] = field(default_factory=dict)
    provider: str = "ollama"
    document_id: Optional[str] = None
    score: float = 0.0  # cosine similarity score from pgvector (1 - cosine_distance)
    


@dataclass
class VectorRecord:
    vector: Sequence[float]
    metadata: VectorMetadata
