"""
Deterministic DEMO OCR provider.

Produces realistic OCR evidence (text + confidence + page + bbox) for each of
the 5 synthetic demo scenarios described in the product spec, WITHOUT calling
any external OCR engine. This lets judges run the full pipeline with zero
setup. Swap OCR_PROVIDER=paddleocr in .env to use the real PaddleOCR provider
once that dependency is installed (see services/ocr/paddleocr_provider.py stub).
"""
import random
from typing import List

from .base import OCRProvider, OCRSpan

# Scenario -> list of (field label text as it would appear on the scanned
# document, OCR confidence, page, bbox). This simulates what PaddleOCR would
# return after preprocessing a scanned land record.

SCENARIO_OCR: dict[str, List[OCRSpan]] = {
    "clean": [
        {"text": "Owner: Ramesh Kumar", "confidence": 0.97, "page": 1, "bbox": [80, 120, 420, 150]},
        {"text": "Survey No. 145/2A", "confidence": 0.98, "page": 1, "bbox": [80, 160, 380, 190]},
        {"text": "Khasra No. 145/2A", "confidence": 0.96, "page": 1, "bbox": [80, 200, 380, 230]},
        {"text": "Khata No. 88", "confidence": 0.95, "page": 1, "bbox": [80, 240, 300, 270]},
        {"text": "Area: 2.35 acres", "confidence": 0.94, "page": 1, "bbox": [80, 280, 340, 310]},
        {"text": "Village: Rampur", "confidence": 0.96, "page": 1, "bbox": [80, 320, 340, 350]},
        {"text": "Tehsil: Dewas", "confidence": 0.95, "page": 1, "bbox": [80, 360, 320, 390]},
        {"text": "District: Dewas", "confidence": 0.97, "page": 1, "bbox": [80, 400, 320, 430]},
        {"text": "Classification: Agricultural", "confidence": 0.93, "page": 1, "bbox": [80, 440, 420, 470]},
        {"text": "Ownership: Freehold, single owner", "confidence": 0.91, "page": 1, "bbox": [80, 480, 460, 510]},
        {"text": "Mutation No. 874", "confidence": 0.95, "page": 2, "bbox": [80, 100, 340, 130]},
        {"text": "Mutation Date: 12-04-2018", "confidence": 0.93, "page": 2, "bbox": [80, 140, 400, 170]},
        {"text": "Registration No. REG-2018-4471", "confidence": 0.92, "page": 2, "bbox": [80, 180, 460, 210]},
        {"text": "Registration Date: 15-04-2018", "confidence": 0.94, "page": 2, "bbox": [80, 220, 420, 250]},
    ],
    "poor_scan": [
        {"text": "Own_r: Ram-sh Kum_r", "confidence": 0.52, "page": 1, "bbox": [82, 121, 418, 149]},
        {"text": "Sur_ey No. 2C1/?", "confidence": 0.48, "page": 1, "bbox": [79, 161, 379, 189]},
        {"text": "Kha_ra No. 2C1/?", "confidence": 0.46, "page": 1, "bbox": [79, 201, 379, 229]},
        {"text": "Kh_ta No. 4_", "confidence": 0.51, "page": 1, "bbox": [80, 241, 300, 269]},
        {"text": "Are_: 1.?? acres", "confidence": 0.44, "page": 1, "bbox": [81, 281, 341, 309]},
        {"text": "Vill_ge: Sonka_da", "confidence": 0.55, "page": 1, "bbox": [80, 321, 340, 349]},
        {"text": "Teh_il: Dewas", "confidence": 0.61, "page": 1, "bbox": [80, 361, 320, 389]},
        {"text": "Distr_ct: Dewas", "confidence": 0.64, "page": 1, "bbox": [80, 401, 320, 429]},
        {"text": "Classif_cation: ?gricultural", "confidence": 0.4, "page": 1, "bbox": [80, 441, 420, 469]},
        {"text": "Owners_ip: illegible", "confidence": 0.3, "page": 1, "bbox": [80, 481, 460, 509]},
        {"text": "Mut_tion No. ?31", "confidence": 0.38, "page": 2, "bbox": [80, 101, 340, 129]},
        {"text": "Mutation D_te: ??-0?-2015", "confidence": 0.35, "page": 2, "bbox": [80, 141, 400, 169]},
        {"text": "Regis_ration No. illegible", "confidence": 0.28, "page": 2, "bbox": [80, 181, 460, 209]},
        {"text": "Registrat_on Date: illegible", "confidence": 0.27, "page": 2, "bbox": [80, 221, 420, 249]},
    ],
    "area_mismatch": [
        {"text": "Owner: Sunita Devi", "confidence": 0.95, "page": 1, "bbox": [80, 120, 420, 150]},
        {"text": "Survey No. 212/1B", "confidence": 0.97, "page": 1, "bbox": [80, 160, 380, 190]},
        {"text": "Khasra No. 212/1B", "confidence": 0.96, "page": 1, "bbox": [80, 200, 380, 230]},
        {"text": "Khata No. 55", "confidence": 0.94, "page": 1, "bbox": [80, 240, 300, 270]},
        {"text": "Area: 3.10 acres", "confidence": 0.91, "page": 1, "bbox": [80, 280, 340, 310]},
        {"text": "Village: Kannod", "confidence": 0.95, "page": 1, "bbox": [80, 320, 340, 350]},
        {"text": "Tehsil: Kannod", "confidence": 0.94, "page": 1, "bbox": [80, 360, 320, 390]},
        {"text": "District: Dewas", "confidence": 0.96, "page": 1, "bbox": [80, 400, 320, 430]},
        {"text": "Classification: Agricultural", "confidence": 0.9, "page": 1, "bbox": [80, 440, 420, 470]},
        {"text": "Ownership: Freehold, single owner", "confidence": 0.89, "page": 1, "bbox": [80, 480, 460, 510]},
        # Mutation record on page 2 shows a DIFFERENT area (2.40 acres) -> triggers
        # "area differs from related record" validation warning.
        {"text": "Mutation No. 631", "confidence": 0.9, "page": 2, "bbox": [80, 100, 340, 130]},
        {"text": "Mutation Date: 03-11-2019", "confidence": 0.88, "page": 2, "bbox": [80, 140, 400, 170]},
        {"text": "Mutation Area Recorded: 2.40 acres", "confidence": 0.85, "page": 2, "bbox": [80, 180, 460, 210]},
        {"text": "Registration No. REG-2019-1187", "confidence": 0.89, "page": 2, "bbox": [80, 220, 460, 250]},
        {"text": "Registration Date: 05-11-2019", "confidence": 0.9, "page": 2, "bbox": [80, 260, 420, 290]},
    ],
    "duplicate_survey": [
        {"text": "Owner: Anil Patidar", "confidence": 0.94, "page": 1, "bbox": [80, 120, 420, 150]},
        # Survey number intentionally collides with the "clean" scenario record
        {"text": "Survey No. 145/2A", "confidence": 0.93, "page": 1, "bbox": [80, 160, 380, 190]},
        {"text": "Khasra No. 145/2A", "confidence": 0.92, "page": 1, "bbox": [80, 200, 380, 230]},
        {"text": "Khata No. 91", "confidence": 0.9, "page": 1, "bbox": [80, 240, 300, 270]},
        {"text": "Area: 1.80 acres", "confidence": 0.89, "page": 1, "bbox": [80, 280, 340, 310]},
        {"text": "Village: Rampur", "confidence": 0.92, "page": 1, "bbox": [80, 320, 340, 350]},
        {"text": "Tehsil: Dewas", "confidence": 0.91, "page": 1, "bbox": [80, 360, 320, 390]},
        {"text": "District: Dewas", "confidence": 0.93, "page": 1, "bbox": [80, 400, 320, 430]},
        {"text": "Classification: Residential", "confidence": 0.88, "page": 1, "bbox": [80, 440, 420, 470]},
        {"text": "Ownership: Freehold, joint owners", "confidence": 0.86, "page": 1, "bbox": [80, 480, 460, 510]},
        {"text": "Mutation No. 902", "confidence": 0.88, "page": 2, "bbox": [80, 100, 340, 130]},
        {"text": "Mutation Date: 21-07-2021", "confidence": 0.87, "page": 2, "bbox": [80, 140, 400, 170]},
        {"text": "Registration No. REG-2021-3390", "confidence": 0.86, "page": 2, "bbox": [80, 180, 460, 210]},
        {"text": "Registration Date: 24-07-2021", "confidence": 0.88, "page": 2, "bbox": [80, 220, 420, 250]},
    ],
    "missing_mutation": [
        {"text": "Owner: Geeta Bai", "confidence": 0.95, "page": 1, "bbox": [80, 120, 420, 150]},
        {"text": "Survey No. 301/4", "confidence": 0.96, "page": 1, "bbox": [80, 160, 380, 190]},
        {"text": "Khasra No. 301/4", "confidence": 0.95, "page": 1, "bbox": [80, 200, 380, 230]},
        {"text": "Khata No. 12", "confidence": 0.93, "page": 1, "bbox": [80, 240, 300, 270]},
        {"text": "Area: 0.95 acres", "confidence": 0.92, "page": 1, "bbox": [80, 280, 340, 310]},
        {"text": "Village: Bagli", "confidence": 0.94, "page": 1, "bbox": [80, 320, 340, 350]},
        {"text": "Tehsil: Bagli", "confidence": 0.93, "page": 1, "bbox": [80, 360, 320, 390]},
        {"text": "District: Dewas", "confidence": 0.95, "page": 1, "bbox": [80, 400, 320, 430]},
        {"text": "Classification: Agricultural", "confidence": 0.9, "page": 1, "bbox": [80, 440, 420, 470]},
        {"text": "Ownership: Freehold, single owner", "confidence": 0.89, "page": 1, "bbox": [80, 480, 460, 510]},
        # NOTE: no Mutation No. / Mutation Date / Registration spans present on
        # this document at all -> fields will be extracted as null/missing.
        {"text": "Page 2: (mutation section blank in source document)", "confidence": 0.6, "page": 2, "bbox": [80, 100, 460, 130]},
    ],
}


class DemoOCRProvider(OCRProvider):
    name = "demo"

    def extract(self, file_path: str, scenario_tag: str | None = None) -> List[OCRSpan]:
        tag = scenario_tag or "clean"
        spans = SCENARIO_OCR.get(tag, SCENARIO_OCR["clean"])
        # Return a deep-ish copy so downstream mutation never corrupts the template
        return [dict(s) for s in spans]

    @staticmethod
    def available_scenarios() -> List[str]:
        return list(SCENARIO_OCR.keys())
