# src/ingestion_service/core/chunks.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Chunk:
    chunk_id: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    ocr_text: Optional[str] = None
