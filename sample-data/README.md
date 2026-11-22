# Sample / Synthetic Demo Data

`demo_scenarios.json` contains the exact synthetic OCR evidence and AI-extracted
fields used by the 5 demo scenarios described in the product spec. This is
what the backend's deterministic **demo OCR** and **demo extraction**
providers return — there is no real OCR engine or LLM call involved, so the
full pipeline runs offline, with zero API keys, in Demo Mode.

## Scenarios

| Tag                | Description                                                              | Expected pipeline outcome                     |
|---------------------|---------------------------------------------------------------------------|------------------------------------------------|
| `clean`             | High-confidence, clean scan, all fields present and consistent            | Auto-passed (no human review required)         |
| `poor_scan`         | Badly degraded scan, low OCR confidence throughout                        | Routed to human verification (low confidence)  |
| `area_mismatch`     | Plot area conflicts with the area recorded in the mutation register (**default demo scenario**) | Validation warning: consistency_area_mismatch |
| `duplicate_survey`  | Survey/khasra number collides with another record already in the system   | Validation warning: consistency_duplicate_survey |
| `missing_mutation`  | Mutation number & date are absent from the source document                | Validation warning: consistency_missing_mutation |

## Important

> **SYNTHETIC DEMO DATA — NOT A REAL GOVERNMENT RECORD.**
> All names, survey numbers, and locations in these scenarios are entirely
> fictional and were authored for demonstration purposes only. No real
> citizens' personal information is used anywhere in this project.

## Regenerating this file

```bash
cd backend
source venv/bin/activate   # or your virtualenv
python - <<'PY'
import json
from app.services.ocr.demo_provider import SCENARIO_OCR
from app.services.extraction.demo_provider import DemoExtractionProvider

provider = DemoExtractionProvider()
out = {tag: {"ocr_spans": spans, "extracted_fields": provider.extract_fields(spans, tag)}
       for tag, spans in SCENARIO_OCR.items()}

with open("../sample-data/demo_scenarios.json", "w") as f:
    json.dump(out, f, indent=2)
PY
```
