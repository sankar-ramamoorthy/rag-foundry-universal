# ingestion_service/src/core/ocr/ocr_factory.py

import os
from typing import Dict

from src.core.ocr.ocr import OCRExtractor
from src.core.ocr.tesseract_ocr import TesseractOCR
# from src.core.ocr.paddle_ocr import PaddleOCRExtractor

# Create single instances (heavy models) and reuse
tesseract_ocr = TesseractOCR()
# paddle_ocr = PaddleOCRExtractor()

OCR_ENGINES: Dict[str, OCRExtractor] = {
    TesseractOCR.name: tesseract_ocr,  # "tesseract"
    # PaddleOCRExtractor.name: paddle_ocr,  # "paddle"
}
OCR_ENGINES["default"] = tesseract_ocr


def get_ocr_engine(name: str = "tesseract") -> OCRExtractor:
    """
    Return an OCR engine instance by name.
    Defaults to environment variable OCR_PROVIDER or 'tesseract'.
    """
    ocr_name = (name or os.getenv("OCR_PROVIDER", "tesseract")).lower()
    engine = OCR_ENGINES.get(ocr_name)
    if not engine:
        raise ValueError(f"OCR engine '{ocr_name}' is not registered")
    return engine
