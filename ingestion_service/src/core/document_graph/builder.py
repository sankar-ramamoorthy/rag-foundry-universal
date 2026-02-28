# ingestion_service/src/core/document_graph/builder.py
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from src.core.document_graph.models import (
    DocumentGraph,
    GraphEdge,
    GraphNode,
)
from src.core.extractors.base import ExtractedArtifact


class DocumentGraphBuilder:
    """
    Builds a deterministic document graph from extracted artifacts.

    Rules (IS2 baseline):
    - Same-page association only
    - Images link to nearest following text on the page
    - Fallback: image → page
    """

    def build(self, artifacts: List[ExtractedArtifact]) -> DocumentGraph:
        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []

        # ---- create nodes ----
        for artifact in artifacts:
            artifact_id = self._artifact_id(artifact)
            nodes[artifact_id] = GraphNode(
                artifact_id=artifact_id,
                artifact=artifact,
            )

        # ---- group by page ----
        by_page: Dict[int, List[ExtractedArtifact]] = defaultdict(list)
        for artifact in artifacts:
            by_page[artifact.page_number].append(artifact)

        # ---- associate per page ----
        for page_number, page_artifacts in by_page.items():
            page_artifacts.sort(key=lambda a: a.order_index)

            texts = [a for a in page_artifacts if a.type == "text"]
            images = [a for a in page_artifacts if a.type == "image"]

            # text → page edges
            for text in texts:
                edges.append(
                    GraphEdge(
                        from_id=self._artifact_id(text),
                        to_id=self._page_id(text),
                        relation="text_to_page",
                    )
                )

            for image in images:
                image_id = self._artifact_id(image)

                # find nearest following text
                target_text = next(
                    (t for t in texts if t.order_index > image.order_index),
                    None,
                )

                if target_text:
                    edges.append(
                        GraphEdge(
                            from_id=image_id,
                            to_id=self._artifact_id(target_text),
                            relation="image_to_text",
                        )
                    )
                else:
                    # fallback: image → page
                    edges.append(
                        GraphEdge(
                            from_id=image_id,
                            to_id=self._page_id(image),
                            relation="image_to_page",
                        )
                    )

        return DocumentGraph(nodes=nodes, edges=edges)

    # ------------------------------------------------------------------

    @staticmethod
    def _artifact_id(artifact: ExtractedArtifact) -> str:
        return (
            f"{artifact.source_file}:"
            f"{artifact.page_number}:"
            f"{artifact.order_index}:"
            f"{artifact.type}"
        )

    @staticmethod
    def _page_id(artifact: ExtractedArtifact) -> str:
        return f"{artifact.source_file}:page:{artifact.page_number}"
