# ingestion_service/src/core/converters/docling_converter.py
# Docling universal document pre-processor (ADR-047)
"""
DoclingConverter

Single-responsibility component: converts file bytes → Markdown string.

Supports:
    PDF    — layout, reading order, table structure (superior to PyMuPDF)
    DOCX   — Word documents
    PPTX   — PowerPoint presentations
    XLSX   — Excel spreadsheets
    HTML   — web pages
    EPUB   — eBooks
    CSV    — tabular data

Design constraints (consistent with existing extractors):
    - Stateless
    - No DB access
    - No side effects
    - Raises ValueError on unsupported or unreadable input
"""
from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Supported extensions → Docling InputFormat
DOCLING_SUPPORTED = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".epub", ".csv"
}


class DoclingConverter:
    """
    Converts supported file formats to Markdown via Docling.

    Usage:
        converter = DoclingConverter()
        markdown = converter.convert(file_bytes, filename="report.pdf")
    """

    def __init__(self):
        # IS3: lazy import — Docling is heavy, only import when needed
        # Initialise converter once per instance — pipeline cache reused across calls
        self._converter = self._build_converter()

    def _build_converter(self):
        """
        Build and return a configured DocumentConverter.
        CPU-only — no GPU acceleration configured.
        Tesseract used for OCR (already installed in Docker image).
        """
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TableStructureOptions,
        )
        from docling.models.tesseract_ocr_cli_model import TesseractCliOcrOptions

        # IS3: PDF pipeline — table structure + Tesseract OCR (CPU-safe)
        pdf_pipeline_options = PdfPipelineOptions()
        pdf_pipeline_options.do_ocr = True
        pdf_pipeline_options.do_table_structure = True
        pdf_pipeline_options.table_structure_options = TableStructureOptions(
            do_cell_matching=True
        )
        pdf_pipeline_options.ocr_options = TesseractCliOcrOptions()

        converter = DocumentConverter(
            allowed_formats=[
                InputFormat.PDF,
                InputFormat.DOCX,
                InputFormat.PPTX,
                InputFormat.XLSX,
                InputFormat.HTML,
                InputFormat.CSV,
            ],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pdf_pipeline_options,
                ),
            },
        )

        logger.debug("IS3: DoclingConverter initialised (CPU mode)")
        return converter

    def convert(self, file_bytes: bytes, filename: str) -> str:
        """
        Convert file bytes to Markdown string.

        Args:
            file_bytes: Raw bytes of the source file
            filename:   Original filename including extension (used for format detection)

        Returns:
            Markdown string of the document content

        Raises:
            ValueError: If the file format is unsupported or conversion fails
        """
        from docling.datamodel.document import DocumentStream

        suffix = self._get_suffix(filename)
        if suffix not in DOCLING_SUPPORTED:
            raise ValueError(
                f"IS3: Unsupported format for DoclingConverter: {suffix}. "
                f"Supported: {DOCLING_SUPPORTED}"
            )

        logger.debug("IS3: Converting %s (%d bytes) via Docling", filename, len(file_bytes))

        try:
            stream = DocumentStream(
                name=filename,
                stream=io.BytesIO(file_bytes),
            )
            result = self._converter.convert(stream)

            if result is None or result.document is None:
                raise ValueError(f"IS3: Docling returned empty result for {filename}")

            markdown = result.document.export_to_markdown()

            if not markdown or not markdown.strip():
                raise ValueError(f"IS3: Docling produced empty Markdown for {filename}")

            logger.info(
                "IS3: Converted %s → %d chars Markdown",
                filename, len(markdown)
            )
            return markdown

        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(
                f"IS3: Docling conversion failed for {filename}: {exc}"
            ) from exc

    @staticmethod
    def _get_suffix(filename: str) -> str:
        """Extract lowercase extension from filename."""
        parts = filename.rsplit(".", 1)
        if len(parts) < 2:
            return ""
        return f".{parts[-1].lower()}"

    @staticmethod
    def is_supported(filename: str) -> bool:
        """Check if a filename's extension is supported by DoclingConverter."""
        suffix = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
        return suffix in DOCLING_SUPPORTED
    
# At bottom of docling_converter.py

def is_docling_supported(filename: str) -> bool:
    """Module-level convenience — check without instantiating converter."""
    suffix = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
    return suffix in DOCLING_SUPPORTED