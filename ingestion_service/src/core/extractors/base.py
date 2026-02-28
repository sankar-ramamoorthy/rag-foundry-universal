# ingestion_service/src/core/extractors/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

# ---------------------------------------------------------------------------
# Artifact model
# ---------------------------------------------------------------------------

ArtifactType = Literal["text", "image"]


@dataclass(frozen=True)
class ExtractedArtifact:
    """
    Internal representation of a document artifact extracted from a source file.

    This model is:
    - internal-only (not persisted, not exposed via API)
    - immutable (safe to pass between pipeline stages)
    - provenance-aware (page number, order index)
    """

    # artifact classification
    type: ArtifactType

    # provenance
    source_file: str
    page_number: int
    order_index: int

    # content (one of these must be populated depending on type)
    text: Optional[str] = None
    image_bytes: Optional[bytes] = None

    # NEW: OCR text for images
    ocr_text: Optional[str] = None

    # layout metadata (optional, for future use)
    bbox: Optional[Tuple[float, float, float, float]] = None


# ---------------------------------------------------------------------------
# Extractor interface
# ---------------------------------------------------------------------------


class DocumentExtractor(ABC):
    """
    Base interface for document extractors.

    Implementations are responsible for extracting ordered document artifacts
    (text blocks, images, etc.) from raw file bytes.

    Design constraints:
    - Stateless
    - Deterministic
    - No side effects
    - No database access
    - No OCR invocation (handled elsewhere)
    """

    @abstractmethod
    def extract(self, file_bytes: bytes, source_name: str) -> List[ExtractedArtifact]:
        """
        Extract ordered document artifacts from the given file.

        Args:
            file_bytes: Raw bytes of the source file.
            source_name: Original filename or logical source identifier.

        Returns:
            A list of ExtractedArtifact objects, ordered as they appear
            in the source document.

        Raises:
            ValueError: If the file cannot be parsed or is unsupported.
        """
        raise NotImplementedError
