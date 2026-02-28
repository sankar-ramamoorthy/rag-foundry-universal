# ingestion_service/src/core/ocr/ocr.py

from abc import ABC, abstractmethod


class OCRExtractor(ABC):
    """Base interface for OCR engines."""

    name: str = "base"

    @abstractmethod
    def extract_text(self, image_bytes: bytes) -> str:
        """Return extracted text from image bytes. Empty string if nothing found."""
        pass
