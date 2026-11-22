"""
Real (non-demo) field extraction provider.

Takes real OCR line spans (English, Hindi, or Kannada), translates
non-English lines to English via the translation layer (keeping the
original-script text for the audit trail), then classifies each line into
one of the BhoomiTrust land-record schema fields using multilingual label
matching. Never invents a value: a line that doesn't match a known label is
simply not mapped to any field.
"""
import re
from typing import List, Optional

from ..ocr.base import OCRSpan
from ..translation.translator import translate_line
from .base import ExtractionProvider, ExtractedFieldResult

ALL_FIELDS = [
    "owner_name", "survey_number", "khasra_number", "khata_number",
    "plot_area", "village", "tehsil", "district", "land_classification",
    "ownership_details", "mutation_number", "mutation_date",
    "registration_number", "registration_date",
]

# Each field maps to label keywords as they may appear in the ORIGINAL
# script (English, Hindi, Kannada) — matched first, script-agnostic — with
# translated-English keywords as a second pass. Matching native-script
# labels directly (rather than depending on the translation API) is what
# lets this pipeline keep working even when outbound translation is
# unavailable (e.g. restricted government network).
FIELD_LABELS: dict[str, List[str]] = {
    "owner_name": [
        "owner", "owner name", "name of owner", "landowner", "pattadar",
        "स्वामी", "मालिक", "काश्तकार",
        "ಮಾಲೀಕರು", "ಮಾಲಿಕರು", "ಪಟ್ಟಾದಾರ",
    ],
    "survey_number": [
        "survey no", "survey number", "survey",
        "सर्वे नंबर", "सर्वे क्रमांक",
        "ಸರ್ವೆ ಸಂಖ್ಯೆ", "ಸರ್ವೆ ನಂ",
    ],
    "khasra_number": [
        "khasra no", "khasra number", "khasra",
        "खसरा नंबर", "खसरा क्रमांक",
    ],
    "khata_number": [
        "khata no", "khata number", "khata", "account no",
        "खाता नंबर", "खाता क्रमांक",
        "ಖಾತಾ ಸಂಖ್ಯೆ", "ಖಾತೆ ಸಂಖ್ಯೆ",
    ],
    "plot_area": [
        "area", "plot area", "land area", "extent",
        "क्षेत्रफल", "रकबा",
        "ವಿಸ್ತೀರ್ಣ", "ವಿಸ್ತಾರ",
    ],
    "village": ["village", "गांव", "ग्राम", "ಗ್ರಾಮ", "ಊರು"],
    "tehsil": ["tehsil", "taluk", "taluka", "mandal", "तहसील", "ತಾಲೂಕು"],
    "district": ["district", "जिला", "ಜಿಲ್ಲೆ"],
    "land_classification": [
        "classification", "land classification", "land type", "type of land",
        "वर्गीकरण", "भूमि वर्गीकरण",
        "ವರ್ಗೀಕರಣ",
    ],
    "ownership_details": [
        "ownership", "ownership details", "type of ownership", "possession",
        "स्वामित्व",
        "ಮಾಲೀಕತ್ವ",
    ],
    "mutation_number": [
        "mutation no", "mutation number",
        "म्यूटेशन नंबर", "स्यूटेशन नंबर", "दाखिल खारिज संख्या",
        "ಮ್ಯುಟೇಷನ್\u200c ಸಂಖ್ಯೆ", "ಮ್ಯುಟೇಷನ್ ಸಂಖ್ಯೆ",
    ],
    "mutation_date": [
        "mutation date", "म्यूटेशन तिथि", "ಮ್ಯುಟೇಷನ್ ದಿನಾಂಕ",
    ],
    "registration_number": [
        "registration no", "registration number", "reg no",
        "पंजीकरण नंबर", "रजिस्ट्रेशन नंबर",
        "ನೋಂದಣಿ ಸಂಖ್ಯೆ",
    ],
    "registration_date": [
        "registration date", "पंजीकरण तिथि", "ನೋಂದಣಿ ದಿನಾಂಕ",
    ],
}

_LABEL_SPLIT = re.compile(r"^(.*?)(?:no\.?|[:;।])\s*(.*)$", re.IGNORECASE)


def _match_field(label_text: str) -> Optional[str]:
    normalized = label_text.strip().lower()
    best_field, best_len = None, 0
    for field, keywords in FIELD_LABELS.items():
        for kw in keywords:
            if normalized.startswith(kw) and len(kw) > best_len:
                best_field, best_len = field, len(kw)
    return best_field


def _split_label_value(line: str) -> tuple[Optional[str], str]:
    m = _LABEL_SPLIT.match(line)
    if not m:
        return None, line.strip()
    label_part, value_part = m.group(1).strip(), m.group(2).strip(" :;।.-\u200c")
    if not value_part:
        return None, line.strip()
    field = _match_field(label_part)
    return field, value_part


class RegexExtractionProvider(ExtractionProvider):
    """Deterministic, explainable multilingual extraction — no LLM call, no
    hallucination risk. This is the default real-pipeline extractor; swap in
    LLMExtractionProvider for higher recall on unusual document layouts once
    an LLM_API_KEY is configured."""

    name = "regex"

    def extract_fields(
        self, ocr_spans: List[OCRSpan], scenario_tag: Optional[str] = None
    ) -> List[ExtractedFieldResult]:
        found: dict[str, ExtractedFieldResult] = {}

        for span in ocr_spans:
            raw_text = span["text"]
            translated = translate_line(raw_text)
            field = _match_field(translated["translated_text"])
            if field is None:
                # Try splitting on ':'/'No.' first, in case the label and
                # value were OCR'd as one continuous line.
                field, value = _split_label_value(translated["translated_text"])
            else:
                _, value = _split_label_value(translated["translated_text"])

            if field is None or field in found:
                continue  # unmapped line, or field already captured (first match wins)

            was_translated = translated["detected_lang"] not in (None, "en")
            extraction_confidence = span["confidence"] * (0.93 if was_translated else 0.98)

            found[field] = {
                "field_name": field,
                "value": value or None,
                "ocr_confidence": round(span["confidence"], 3),
                "extraction_confidence": round(max(0.0, min(1.0, extraction_confidence)), 3),
                "source_page": span["page"],
                "source_bbox": span["bbox"],
                # Audit trail always keeps the ORIGINAL regional-language text,
                # never just the translation, per product policy.
                "source_text": translated["original_text"],
                "review_reason": (
                    f"Translated from {translated['detected_lang']} for extraction; "
                    "original text preserved for audit." if was_translated else None
                ),
            }

        results: List[ExtractedFieldResult] = []
        for field in ALL_FIELDS:
            if field in found:
                results.append(found[field])
            else:
                results.append({
                    "field_name": field, "value": None, "ocr_confidence": 0.0,
                    "extraction_confidence": 0.0, "source_page": None, "source_bbox": None,
                    "source_text": None, "review_reason": "No matching label found in document.",
                })
        return results
