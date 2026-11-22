# Project state

**Bhoomi_setu** is the platform; **BhoomiTrust AI** is the existing land-record module inside it. Goal: a Document AI layer (multi-document upload, OCR, cited question answering, quote/claim verification, contradiction and amendment tracking, human review) on top of the land-record app, without breaking it.

- Stack: Next.js 14 + TypeScript + Tailwind (`frontend/`), FastAPI + Motor (`backend/`), MongoDB, Docker Compose (3000 / 8000 / 27017).
- Backend layout: `routers/` (auth, documents, records, dashboard, search, audit, **document_ai**), `services/` (pipeline, ocr, extraction, validation, confidence, anomaly, verification, audit, **docai**), `deps.py` (auth + ownership helpers).
- Branches: `dev` is the integration target, never push to `main`. Feature branches: `neha_frontend` (Neha), `pakhi_backend` (Pakhi), `cleanup/audit-security-hardening`, `docs/handoff-audit-findings`, `infra/docker-docs-fixes` (the last three are already contained in `dev` at `09fab17`).
- API contract: `docs/API_CONTRACT.md` (implementation notes at the bottom). Existing API: `docs/API.md`.
- Env: Python 3.12, Tesseract (+ `hin`, `kan` data for the Indic OCR test), poppler, Node for the frontend. Install backend with `requirements-dev.txt`.

## Security decisions
- Ownership policy: ADMIN and REVENUE_OFFICER see everything (reviewers); a DATA_ENTRY_OPERATOR only sees documents they uploaded plus the records, audit rows, search hits, stats and CSV derived from them. Another user's resource answers 404 (no existence leak). Helpers live in `backend/app/deps.py`.
- `/api/search` escapes the query (`re.escape`) instead of passing it to Mongo as a regex.
- `GET /api/records/public-verify/{id}` stays public on purpose (QR certificate check, exposes only hash + status).
- The Fast2SMS key that was committed earlier is still in Git history: rotate it.
