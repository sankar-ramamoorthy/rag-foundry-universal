# ingestion_service/src/core/document_graph/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal

from src.core.extractors.base import ExtractedArtifact

RelationType = Literal[
    "image_to_text",
    "image_to_page",
    "text_to_page",
]


@dataclass(frozen=True)
class GraphNode:
    artifact_id: str
    artifact: ExtractedArtifact


@dataclass(frozen=True)
class GraphEdge:
    from_id: str
    to_id: str
    relation: RelationType


@dataclass
class DocumentGraph:
    nodes: Dict[str, GraphNode]
    edges: List[GraphEdge]
