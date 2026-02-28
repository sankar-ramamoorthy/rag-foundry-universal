# src/ingestion_service/core/headless_ingest_pdf.py
from __future__ import annotations
from typing import List
from src.core.extractors.pdf import PDFExtractor
from src.core.document_graph.builder import DocumentGraphBuilder
from src.core.chunk_assembly.pdf_chunk_assembler import PDFChunkAssembler
from src.core.pipeline import IngestionPipeline
from shared.chunks import Chunk
from src.core.extractors.base import ExtractedArtifact


class HeadlessPDFIngestor:
    """
    Headless ingestion of PDFs using PDFExtractor.

    - Extracts text blocks and images from PDF bytes
    - Builds a deterministic document graph
    - Chunks text artifacts
    - Persists embeddings to vector store
    """

    def __init__(self, pipeline: IngestionPipeline, ocr_provider: str = "default"):
        self.pipeline = pipeline
        self.ocr_provider = ocr_provider

    def _run_ocr_and_expand_artifacts(
        self, artifacts: List[ExtractedArtifact]
    ) -> List[ExtractedArtifact]:
        """
        Given a list of artifacts, run OCR on image artifacts.
        If OCR produced text, create a new text artifact for OCR text,
        preserving order and provenance deterministically.
        """
        enriched: List[ExtractedArtifact] = []

        for artifact in artifacts:
            enriched.append(artifact)

            if artifact.type == "image" and artifact.image_bytes:
                # Run OCR on image
                from src.core.ocr.utils import enrich_image_with_ocr

                image_with_ocr = enrich_image_with_ocr(artifact, self.ocr_provider)

                if image_with_ocr.ocr_text:
                    # Create a synthetic text artifact representing the OCR text
                    # Keep the same page but a slightly greater order_index
                    ocr_artifact = ExtractedArtifact(
                        type="text",
                        source_file=image_with_ocr.source_file,
                        page_number=image_with_ocr.page_number,
                        order_index=artifact.order_index
                        + 1,  # deterministic after image
                        text=image_with_ocr.ocr_text,
                        image_bytes=None,
                    )
                    enriched.append(ocr_artifact)

        return enriched

    def ingest_pdf(
        self, file_bytes: bytes, source_name: str, ingestion_id: str
    ) -> List[Chunk]:
        # 1️⃣ Extract artifacts from PDF bytes
        extractor = PDFExtractor()
        artifacts = extractor.extract(file_bytes, source_name)

        # NEW: integrate OCR text as new text artifacts
        artifacts = self._run_ocr_and_expand_artifacts(artifacts)

        # 2️⃣ Build document graph
        graph_builder = DocumentGraphBuilder()
        doc_graph = graph_builder.build(artifacts)

        # 3️⃣ Assemble text chunks
        assembler = PDFChunkAssembler()
        chunks = assembler.assemble(doc_graph)

        # 4️⃣ Embed & persist chunks
        embeddings = self.pipeline._embed(chunks)
        self.pipeline._vector_store.persist(
            chunks=chunks, embeddings=embeddings, ingestion_id=ingestion_id
        )

        return chunks
