# ingestion_service/src/core/ocr/tesseract_ocr.py

from PIL import Image
import pytesseract
import io

from src.core.ocr.ocr import OCRExtractor


class TesseractOCR(OCRExtractor):
    name = "tesseract"

    def extract_text(self, image_bytes: bytes) -> str:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            return text or ""
        except Exception:
            return ""
