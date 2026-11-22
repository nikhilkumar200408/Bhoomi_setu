"""Page-level text extraction with provenance (PDF text layer first, OCR for scanned pages/images)."""
import os
import tempfile
from typing import List, TypedDict

from .errors import DocAIError

MIN_TEXT_CHARS = 25  # a PDF page with less text than this is treated as scanned and sent to OCR


class Page(TypedDict):
    page: int          # 1-based
    text: str          # normalized: whitespace collapsed
    source_type: str   # PDF_TEXT | OCR_TEXT


def normalize(text: str) -> str:
    return " ".join(text.split())


def _ocr_image(path: str) -> str:
    try:
        from ..ocr.tesseract_provider import TesseractOCRProvider
        spans = TesseractOCRProvider().extract(path)
    except Exception as e:  # noqa: BLE001 - tesseract/poppler missing etc.
        raise DocAIError(503, "DEPENDENCY_UNAVAILABLE", "OCR is not available on this server.") from e
    return normalize(" ".join(s["text"] for s in spans))


def extract_pages(path: str) -> List[Page]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        import fitz

        pages: List[Page] = []
        with fitz.open(path) as pdf:
            for i, pg in enumerate(pdf, start=1):
                text = normalize(pg.get_text())
                source = "PDF_TEXT"
                if len(text) < MIN_TEXT_CHARS:
                    with tempfile.TemporaryDirectory() as tmp:
                        png = os.path.join(tmp, "page.png")
                        pg.get_pixmap(dpi=300).save(png)
                        text, source = _ocr_image(png), "OCR_TEXT"
                pages.append({"page": i, "text": text, "source_type": source})
        return pages
    return [{"page": 1, "text": _ocr_image(path), "source_type": "OCR_TEXT"}]
