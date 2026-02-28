# ingestion_service/src/core/extractors/pdf.py
from __future__ import annotations
from typing import List, Tuple
import fitz  # PyMuPDF

from src.core.extractors.base import DocumentExtractor, ExtractedArtifact


class PDFExtractor(DocumentExtractor):
    def extract(self, file_bytes: bytes, source_name: str) -> List[ExtractedArtifact]:
        """
        Extracts text blocks and images from a PDF.

        Args:
            file_bytes: The PDF file content as bytes.
            source_name: The filename or source identifier.

        Returns:
            List of ExtractedArtifact objects.
        """
        artifacts: List[ExtractedArtifact] = []
        order_index = 0

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError("Invalid or unreadable PDF") from exc

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_number = page_idx + 1

            # ---- TEXT BLOCKS ----
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text, *_ = block
                if not text or not text.strip():
                    continue

                # Ensure bbox values are floats
                bbox: Tuple[float, float, float, float] = (
                    float(x0),
                    float(y0),
                    float(x1),
                    float(y1),
                )

                artifacts.append(
                    ExtractedArtifact(
                        type="text",
                        source_file=source_name,
                        page_number=page_number,
                        order_index=order_index,
                        text=str(text).strip(),
                        bbox=bbox,
                    )
                )
                order_index += 1

            # ---- IMAGES ----
            for img in page.get_images(full=True):
                xref = img[0]
                image_dict = doc.extract_image(xref)
                image_bytes = image_dict.get("image")
                if not image_bytes:
                    continue

                artifacts.append(
                    ExtractedArtifact(
                        type="image",
                        source_file=source_name,
                        page_number=page_number,
                        order_index=order_index,
                        image_bytes=image_bytes,
                    )
                )
                order_index += 1

        return artifacts
