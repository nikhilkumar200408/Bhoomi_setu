from ...config import settings
from .base import OCRProvider, OCRSpan
from .demo_provider import DemoOCRProvider


def get_ocr_provider() -> OCRProvider:
    if settings.OCR_PROVIDER == "tesseract":
        from .tesseract_provider import TesseractOCRProvider

        return TesseractOCRProvider()
    if settings.OCR_PROVIDER == "paddleocr":
        from .paddleocr_provider import PaddleOCRProvider

        return PaddleOCRProvider()
    if settings.OCR_PROVIDER == "trocr_handwritten":
        from .trocr_provider import TrOCRHandwritingProvider

        return TrOCRHandwritingProvider()
    if settings.OCR_PROVIDER == "hybrid":
        from .hybrid_provider import HybridOCRProvider

        return HybridOCRProvider()
    return DemoOCRProvider()
