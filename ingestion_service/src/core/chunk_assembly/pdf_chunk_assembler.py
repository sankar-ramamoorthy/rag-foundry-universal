# src/ingestion_service/core/chunk_assembly/pdf_chunk_assembler.py
from __future__ import annotations

from typing import Dict, List, Set

from shared.chunks import Chunk
from src.core.document_graph.models import DocumentGraph
from shared.chunkers.selector import ChunkerFactory


class PDFChunkAssembler:
    """
    Converts a DocumentGraph into chunks using real chunkers.

    Rules:
    - Native text OR OCR text are chunked
    - Chunking is delegated to ChunkerFactory
    - Chunk IDs are deterministic
    - Image → text associations are preserved in metadata
    """

    def assemble(self, graph: DocumentGraph) -> List[Chunk]:
        chunks: List[Chunk] = []

        # ---------------------------------------------------------
        # Map image → text edges for associated_image_ids
        # ---------------------------------------------------------
        images_by_text: Dict[str, Set[str]] = {}
        for edge in graph.edges:
            if edge.relation == "image_to_text":
                images_by_text.setdefault(edge.to_id, set()).add(edge.from_id)

        # ---------------------------------------------------------
        # Create chunks from text or OCR text
        # ---------------------------------------------------------
        for node in graph.nodes.values():
            artifact = node.artifact

            # Decide which text to use:
            # - Prefer native text if present
            # - Otherwise use OCR text (if any)
            content_to_chunk: str | None = None
            if artifact.text:
                content_to_chunk = artifact.text
            elif artifact.ocr_text:
                content_to_chunk = artifact.ocr_text

            if not content_to_chunk:
                continue

            # Choose chunker dynamically
            chunker, chunker_params = ChunkerFactory.choose_strategy(content_to_chunk)
            chunk_strategy = getattr(chunker, "chunk_strategy", "unknown")
            chunker_name = getattr(chunker, "name", chunker.__class__.__name__)

            produced_chunks = chunker.chunk(content_to_chunk, **chunker_params)

            for idx, produced_chunk in enumerate(produced_chunks):
                produced_chunk.chunk_id = f"{node.artifact_id}:chunk:{idx}"

                associated_image_ids = list(images_by_text.get(node.artifact_id, []))
                produced_chunk.metadata.update(
                    {
                        "source_file": artifact.source_file,
                        "page_numbers": [artifact.page_number],
                        "artifact_ids": [node.artifact_id],
                        "associated_image_ids": associated_image_ids,
                        "chunk_strategy": chunk_strategy,
                        "chunker_name": chunker_name,
                        "chunker_params": dict(chunker_params),
                        # Optional: expose OCR text if this chunk came from OCR
                        "ocr_text": artifact.ocr_text if artifact.ocr_text else None,
                    }
                )

                chunks.append(produced_chunk)

        return chunks
