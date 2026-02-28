# ingestion_service/src/core/ocr/utils.py
import logging

from src.core.extractors.base import ExtractedArtifact
from src.core.ocr.ocr_factory import get_ocr_engine

logger = logging.getLogger(__name__)


def enrich_image_with_ocr(
    artifact: ExtractedArtifact,
    ocr_provider: str = "tesseract",
) -> ExtractedArtifact:
    """
    Runs OCR on an image artifact and returns a new artifact
    with ocr_text field populated if any text was recognized.

    OCR failures are logged and swallowed; ingestion continues.
    """
    if not artifact.image_bytes:
        return artifact

    ocr_text: str | None = None
    try:
        ocr_engine = get_ocr_engine(ocr_provider)
        ocr_text = ocr_engine.extract_text(artifact.image_bytes) or None
    except Exception as exc:
        logger.warning(
            "OCR failed for image artifact %s (page %s, order %s): %s",
            artifact.source_file,
            artifact.page_number,
            artifact.order_index,
            exc,
        )

    # Return a new artifact with the same fields but OCR text added
    return ExtractedArtifact(
        type=artifact.type,
        source_file=artifact.source_file,
        page_number=artifact.page_number,
        order_index=artifact.order_index,
        text=artifact.text,
        image_bytes=artifact.image_bytes,
        ocr_text=ocr_text,
        bbox=artifact.bbox,
    )
