"""Printed-text OCR with optional handwriting fallback."""

import logging
from typing import List

from .base import OCRProvider, OCRSpan
from .tesseract_provider import TesseractOCRProvider

logger = logging.getLogger(__name__)


class HybridOCRProvider(OCRProvider):
    name = "hybrid"

    def __init__(self):
        self.printed = TesseractOCRProvider()

    def extract(self, file_path: str, scenario_tag: str | None = None) -> List[OCRSpan]:
        printed_spans = self.printed.extract(file_path, scenario_tag)

        if not printed_spans:
            return []

        confidences = [
            float(span.get("confidence", 0))
            for span in printed_spans
            if float(span.get("confidence", 0)) >= 0
        ]
        average = sum(confidences) / len(confidences) if confidences else 0
        low_ratio = (
            sum(value < 0.60 for value in confidences) / len(confidences)
            if confidences else 1
        )

        # Keep reliable printed OCR. Invoke HTR only when page OCR is weak.
        if average >= 0.60 and low_ratio < 0.25:
            for span in printed_spans:
                span["recognition_engine"] = "tesseract"
            return printed_spans

        try:
            from .trocr_provider import TrOCRHandwritingProvider

            handwriting_spans = TrOCRHandwritingProvider().extract(
                file_path, scenario_tag
            )
        except Exception as exc:
            logger.warning("TrOCR fallback unavailable; retaining Tesseract: %s", exc)
            for span in printed_spans:
                span["recognition_engine"] = "tesseract"
                span["review_required"] = float(span.get("confidence", 0)) < 0.60
            return printed_spans

        if not handwriting_spans:
            return printed_spans

        # TrOCR confidence is not calibrated; never present its output as verified.
        for span in handwriting_spans:
            span["confidence"] = min(
                0.59, float(span.get("confidence", 0))
            )
            span["review_required"] = True
            span["recognition_engine"] = "trocr_handwritten"

        return handwriting_spans
