# Architecture

## Pipeline

```text
User
 ↓
Next.js Frontend (TypeScript, Tailwind, Recharts)
 ↓
FastAPI API (JWT auth + RBAC)
 ↓
Document Service (upload, validation, storage)
 ↓
Preprocessing (PyMuPDF / OpenCV — real-provider path)
 ↓
OCR Service (provider interface: demo | paddleocr)
 ↓
AI Extraction (provider interface: demo | LLM structured JSON)
 ↓
Confidence Engine (field + overall scoring, HIGH/REVIEW/VERIFY bands)
 ↓
Validation Engine (explainable rule-based checks)
 ↓
Anomaly Engine (0-100 "potential inconsistency" score)
 ↓
Human Verification (edit / approve / reject / mark unresolved)
 ↓
MongoDB (via Motor, async) — records embed their fields/validations/verification history as sub-documents
 ↓
Audit Trail + Dashboard
```

## Why this shape

The core product bet is not OCR accuracy — it's **trustworthy escalation**.
Every field carries its own confidence and evidence, so the system can
auto-pass what is reliable and route only what is uncertain to a human. This
is why the modular services (`ocr/`, `extraction/`, `confidence/`,
`validation/`, `anomaly/`, `verification/`, `audit/`) are kept independent
and swappable rather than fused into one big extraction step.

## Provider interfaces

Both OCR and AI extraction are behind small abstract interfaces
(`OCRProvider`, `ExtractionProvider`). The **demo providers** are fully
deterministic and require no external services or API keys — they replay
realistic OCR evidence for 5 synthetic scenarios. The **real providers**
(`PaddleOCRProvider`, `LLMExtractionProvider`) implement the same contract,
so swapping `OCR_PROVIDER=paddleocr` / `LLM_PROVIDER=anthropic` in `.env` is
the only change required — no code in `services/pipeline.py`, the
validation engine, or the frontend needs to change.

## Database schema

```text
users
documents
  └── land_records (1:1)
        ├── extracted_fields (1:N, one per schema field)
        ├── validation_results (1:N)
        ├── verification_actions (1:N — edit/approve/reject history)
        └── audit_logs (1:N)
reference_locations (for optional GIS / map lookups)
```

`Document → LandRecord → ExtractedField → ValidationResult → VerificationAction → AuditLog`
mirrors the product spec's relationship diagram exactly.

## Confidence bands

Configurable via `.env`:

```text
CONFIDENCE_HIGH_THRESHOLD=90     # HIGH:   score >= 90
CONFIDENCE_REVIEW_THRESHOLD=70   # REVIEW: 70 <= score < 90
                                  # VERIFY: score < 70 or missing value
```

A record only **auto-passes** when its overall confidence is >= 90 **and**
no validation rule returned WARNING/FAIL — otherwise it is routed to
`PENDING_REVIEW` for a human officer.

## Anomaly scoring

The anomaly engine is a simple, fully explainable weighted sum over
validation severities plus a penalty for low-confidence fields — deliberately
not a black-box fraud classifier. Output is always phrased as **"potential
inconsistency"**, never "fraud detected," per product policy.

## Frontend structure

```text
frontend/
  app/
    login/                     — public login page
    (app)/                     — authenticated shell (sidebar + topbar)
      dashboard/
      documents/  documents/upload/  documents/[id]/
      records/    records/[id]/      records/[id]/verify/   ← hero screen
      audit/
      settings/
  components/
    ui/                        — Button, Card, Badges, Form, States
    DocumentPreview.tsx         — SVG evidence viewer with bbox highlighting
    EvidencePanel.tsx           — field-level OCR/extraction evidence
  lib/
    api.ts, auth.tsx, types.ts, fields.ts
```

The verification screen (`records/[id]/verify`) is intentionally the most
detailed page in the app, per the product brief's "hero feature" directive.
