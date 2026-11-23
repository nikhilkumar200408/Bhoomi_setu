"""Universal page-level extraction with source provenance and layout metadata.

Native PDF text is preferred. Low-text pages are rasterized and sent through the
existing Tesseract provider. The legacy page/text/source_type keys remain stable
for the current retrieval and citation pipeline.
"""
import os
import tempfile
from statistics import mean
from typing import Any, Dict, List, TypedDict

from .errors import DocAIError

MIN_TEXT_CHARS = 25
OCR_DPI = 300


class Page(TypedDict, total=False):
    page: int
    text: str
    source_type: str
    layout_blocks: List[dict]
    tables: List[dict]
    extraction_metadata: dict


def normalize(text: str) -> str:
    return " ".join(text.split())


def _ocr_image_details(path: str, page_number: int = 1, coordinate_scale: float = 1.0) -> dict:
    """Return OCR text and word/line provenance from the configured Tesseract provider."""
    try:
        from ..ocr.tesseract_provider import TesseractOCRProvider
        spans = TesseractOCRProvider().extract(path)
    except Exception as e:  # noqa: BLE001 - dependency and OCR failures are normalized
        raise DocAIError(503, "DEPENDENCY_UNAVAILABLE", "OCR is not available on this server.") from e

    blocks = []
    for span in spans:
        bbox = span.get("bbox") or []
        if len(bbox) == 4:
            bbox = [round(float(value) / coordinate_scale, 2) for value in bbox]
        blocks.append({
            "text": span["text"],
            "bbox": bbox,
            "confidence": float(span.get("confidence", 0.0)),
            "block_type": "OCR_LINE",
        })
    text = normalize(" ".join(block["text"] for block in blocks))
    confidences = [b["confidence"] for b in blocks if b["confidence"] >= 0]
    return {
        "text": text,
        "layout_blocks": blocks,
        "ocr_confidence_avg": round(mean(confidences), 3) if confidences else None,
    }


def _pdf_layout_blocks(page) -> List[dict]:
    """Extract text blocks with PDF-point bounding boxes without changing page text."""
    result = []
    try:
        raw = page.get_text("dict")
        for block_index, block in enumerate(raw.get("blocks", [])):
            if block.get("type", 0) != 0:
                continue
            lines = []
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                if line_text.strip():
                    lines.append(line_text.strip())
            block_text = normalize(" ".join(lines))
            if block_text:
                result.append({
                    "block_index": block_index,
                    "text": block_text,
                    "bbox": [round(float(v), 2) for v in block.get("bbox", [])],
                    "block_type": "TEXT",
                })
    except Exception:  # noqa: BLE001 - preserve the page text if layout parsing fails
        return []
    return result


def _pdf_tables(page) -> tuple[List[dict], str, List[str]]:
    """Use PyMuPDF table detection when available; never infer cells from plain text."""
    warnings: List[str] = []
    if not hasattr(page, "find_tables"):
        return [], "UNAVAILABLE", ["TABLE_DETECTION_UNAVAILABLE"]
    try:
        found = page.find_tables()
        tables = []
        for index, table in enumerate(getattr(found, "tables", []) or []):
            rows = table.extract() or []
            normalized_rows = [[normalize(str(cell or "")) for cell in row] for row in rows]
            if any(any(cell for cell in row) for row in normalized_rows):
                tables.append({
                    "table_index": index,
                    "bbox": [round(float(v), 2) for v in getattr(table, "bbox", [])],
                    "rows": normalized_rows,
                })
        return tables, "COMPLETED", warnings
    except Exception:  # noqa: BLE001 - table parsing must not discard readable page text
        return [], "FAILED", ["TABLE_DETECTION_FAILED"]


def _metadata(text: str, source_type: str, layout_blocks: List[dict],
              tables: List[dict], table_status: str, ocr_confidence_avg=None,
              extra_warnings=None) -> dict:
    warnings = list(extra_warnings or [])
    if not text:
        quality = "EMPTY"
        warnings.append("NO_READABLE_TEXT")
    elif source_type == "OCR_TEXT":
        if ocr_confidence_avg is None:
            quality = "UNKNOWN"
            warnings.append("OCR_CONFIDENCE_UNAVAILABLE")
        elif ocr_confidence_avg >= 0.80:
            quality = "HIGH"
        elif ocr_confidence_avg >= 0.60:
            quality = "REVIEW"
            warnings.append("LOW_OCR_CONFIDENCE")
        else:
            quality = "LOW"
            warnings.append("VERY_LOW_OCR_CONFIDENCE")
    else:
        # A text layer is not a calibrated measure of semantic correctness.
        quality = "TEXT_LAYER_PRESENT"

    return {
        "extraction_method": "TESSERACT_OCR" if source_type == "OCR_TEXT" else "PDF_TEXT_LAYER",
        "text_char_count": len(text),
        "text_word_count": len(text.split()),
        "layout_block_count": len(layout_blocks),
        "table_count": len(tables),
        "table_detection_status": table_status,
        "ocr_confidence_avg": ocr_confidence_avg,
        "quality_status": quality,
        "warnings": list(dict.fromkeys(warnings)),
    }


def extract_pages(path: str) -> List[Page]:
    """Extract page text, layout blocks, tables and traceable quality metadata."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        try:
            with open(path, "r", encoding="utf-8") as source:
                text = normalize(source.read())
        except (OSError, UnicodeError) as exc:
            raise DocAIError(422, "UNPROCESSABLE_DOCUMENT", "The text source could not be read.") from exc
        if not text:
            raise DocAIError(422, "UNPROCESSABLE_DOCUMENT", "The text source is empty.")
        return [{
            "page": 1, "text": text, "source_type": "WEB_TEXT",
            "layout_blocks": [{"text": text, "bbox": [], "block_type": "WEB_TEXT"}],
            "tables": [],
            "extraction_metadata": _metadata(text, "WEB_TEXT", [{"text": text}], [], "NOT_APPLICABLE"),
        }]

    if ext == ".pdf":
        import fitz

        pages: List[Page] = []
        with fitz.open(path) as pdf:
            for page_number, pdf_page in enumerate(pdf, start=1):
                text = normalize(pdf_page.get_text())
                source = "PDF_TEXT"
                warnings: List[str] = []
                ocr_confidence_avg = None

                if len(text) < MIN_TEXT_CHARS:
                    with tempfile.TemporaryDirectory() as tmp:
                        image_path = os.path.join(tmp, "page.png")
                        pdf_page.get_pixmap(dpi=OCR_DPI).save(image_path)
                        ocr = _ocr_image_details(image_path, page_number, OCR_DPI / 72.0)
                    text = ocr["text"]
                    layout_blocks = ocr["layout_blocks"]
                    ocr_confidence_avg = ocr["ocr_confidence_avg"]
                    source = "OCR_TEXT"
                    tables: List[dict] = []
                    table_status = "OCR_TABLE_STRUCTURE_NOT_RECONSTRUCTED"
                    if text:
                        warnings.append("OCR_TEXT_REQUIRES_SOURCE_REVIEW")
                else:
                    layout_blocks = _pdf_layout_blocks(pdf_page)
                    tables, table_status, table_warnings = _pdf_tables(pdf_page)
                    warnings.extend(table_warnings)

                metadata = _metadata(text, source, layout_blocks, tables, table_status,
                                     ocr_confidence_avg, warnings)
                metadata["page_width_pt"] = round(float(pdf_page.rect.width), 2)
                metadata["page_height_pt"] = round(float(pdf_page.rect.height), 2)
                pages.append({
                    "page": page_number,
                    "text": text,
                    "source_type": source,
                    "layout_blocks": layout_blocks,
                    "tables": tables,
                    "extraction_metadata": metadata,
                })
        return pages

    # Single-page image input: retain OCR line geometry in image-pixel coordinates.
    try:
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
    except Exception as e:  # noqa: BLE001
        raise DocAIError(422, "UNPROCESSABLE_DOCUMENT", "The image could not be opened.") from e
    ocr = _ocr_image_details(path)
    metadata = _metadata(ocr["text"], "OCR_TEXT", ocr["layout_blocks"], [],
                         "OCR_TABLE_STRUCTURE_NOT_RECONSTRUCTED", ocr["ocr_confidence_avg"])
    metadata["page_width_px"] = width
    metadata["page_height_px"] = height
    return [{
        "page": 1,
        "text": ocr["text"],
        "source_type": "OCR_TEXT",
        "layout_blocks": ocr["layout_blocks"],
        "tables": [],
        "extraction_metadata": metadata,
    }]
