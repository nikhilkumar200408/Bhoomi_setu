# Bhoomi_setu

### AI-Powered Land Record Digitization & Validation System
**SIH 2026 · PS 26018 — Intelligent Land Record Digitization and Validation System**

> **Extract → Validate → Score → Verify → Trust**
> Not just OCR — a Trust & Validation Layer for digitized land records.
> AI extraction and validation do not constitute legal ownership determination.

---

> **Note:** sections 4, 9, 12 and 14 still describe an earlier demo-scenario design (demo OCR/extraction scenarios, Officer/Reviewer roles). The implemented pipeline uses real OCR and the roles in section 8. Those sections need a rewrite; see `docs/SESSION_HANDOFF.md`.

## 1. Overview

Bhoomi_setu is evolving into a zero-guessing, contradiction-checking Document AI platform (API contract: `docs/API_CONTRACT.md`). Its existing, working module is **BhoomiTrust AI**, the land-record workflow described below, which converts legacy land documents (scanned PDFs, images, handwritten
records) into structured digital land records, then validates the extracted
information, assigns field-level confidence, detects inconsistencies, and
routes uncertain information to an authorized human for verification.

The hero feature is the **Human Verification workflow**: a two-column review
screen showing the original document evidence next to the AI-extracted
record, with per-field confidence, click-to-inspect evidence, inline
editing, and Approve / Reject / Mark Unresolved actions — all captured in a
full audit trail.

**Default demo scenario: Area Mismatch** (`area_mismatch`) — it exercises the
complete pipeline end to end, including a validation warning.

---

## 2. Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full diagram and
rationale. Short version:

```text
Next.js Frontend → FastAPI API → Document Service → Preprocessing → OCR
→ AI Extraction → Confidence Engine → Validation Engine → Anomaly Engine
→ Human Verification → MongoDB (Motor) → Audit Trail + Dashboard
```

## 3. Tech stack

| Layer      | Technology                                                        |
|------------|---------------------------------------------------------------------|
| Frontend   | Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts, lucide-react |
| Backend    | Python, FastAPI, Pydantic, Motor (async MongoDB driver)             |
| Database   | MongoDB (Docker Compose, or a local mongod for zero-config dev)     |
| Document processing | PyMuPDF, OpenCV (real-provider path)                       |
| OCR        | Provider interface — deterministic Demo provider (default) or PaddleOCR |
| AI extraction | Provider interface — deterministic Demo provider (default) or LLM (Claude) structured JSON |
| Auth       | JWT + Role-Based Access Control (ADMIN / OFFICER / REVIEWER)        |
| Deployment | Docker, docker-compose                                             |

---

## 4. What is real vs. simulated (read this first)

- **Real, working code:** the entire pipeline (upload → preprocess placeholder
  → OCR → extraction → confidence → validation → anomaly → verification →
  audit → dashboard), the database schema, JWT auth, RBAC, all API endpoints,
  and the full Next.js UI are real and functional — not mocked screens.
- **Demo Mode (default):** OCR and AI extraction use deterministic, offline
  **demo providers** instead of a real OCR engine / LLM API, so the whole
  system runs immediately with **zero external API keys**. These providers
  replay realistic OCR evidence (text, confidence, page, bounding box) for 5
  synthetic scenarios, and the confidence/validation/anomaly engines run for
  real on top of that evidence.
- **Real-provider path (ready, not exercised by default):** `PaddleOCRProvider`
  and `LLMExtractionProvider` implement the same interfaces as the demo
  providers. Set `OCR_PROVIDER=paddleocr` and `LLM_PROVIDER=anthropic` (with
  `LLM_API_KEY`) in `.env` to use them — no application code changes needed.
- **Synthetic data only:** every name, survey number, and document in this
  repository is fictional. No real citizens' personal information is used
  anywhere.

---

## 5. Prerequisites

- Docker + Docker Compose (recommended, easiest path), **or**
- Python 3.11+ and Node.js 20+ for local development without Docker

---

## 6. Quick start (Docker — recommended)

```bash
cp .env.example .env          # optional: only needed to override defaults (JWT_SECRET, providers)
docker compose up --build
# Optional extras (SMTP/SMS): cp backend/.env.example backend/.env
```

- Frontend: http://localhost:3000
- Backend API + Swagger docs: http://localhost:8000/docs
- The backend container seeds demo users and three sample scans through the
  real pipeline on every boot (see `backend/Dockerfile` CMD).
- For anything beyond a local demo, set `DEMO_MODE=false` and a strong
  `JWT_SECRET` (`openssl rand -hex 32`) in the root `.env`; the backend refuses
  to start with the default secret when demo mode is off.

---

## 7. Local development (without Docker)

### One-command start (recommended)

After running `./setup.sh` once (installs backend venv + frontend node_modules
and seeds MongoDB), start both servers in a single terminal with unified
logs:

```bash
./start_all.sh
```

This checks MongoDB connectivity, then runs `uvicorn` and `next dev`
side-by-side as background jobs of one process, prefixing each line of
output with `[backend]` / `[frontend]`. Ctrl+C stops both cleanly.

### Backend (manual, two-terminal style)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt   # runtime + test deps (use requirements.txt for runtime only)
cp .env.example .env            # defaults to mongodb://localhost:27017 — needs a local mongod
python -m app.seed_real_data    # creates demo users + 3 sample scans (English/Hindi/Kannada)
uvicorn app.main:app --reload --port 8000
```

Backend is now running at http://localhost:8000 (Swagger UI at `/docs`).

### Frontend (manual)

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend is now running at http://localhost:3000.

---

## 8. Demo credentials

Seeded by `python -m app.seed_real_data` (and on every Docker boot):

| Role     | Username   | Password      | Can do                                    |
|----------|------------|---------------|---------------------------------------------|
| Admin            | `admin`           | `Admin@123`    | Read-only oversight, user activity          |
| Data Entry Operator | `operator`     | `Operator@123` | Upload & process documents                  |
| Revenue Officer  | `revenue_officer` | `Officer@123`  | Edit fields, verify/approve/reject records  |

Credentials are provisioned out of band (seed script / admin) — the login
page itself no longer displays or autofills them.

---

## 9. Demo Mode & sample data

- A **"Demo Mode"** badge is always visible in the app header.
- `/documents/upload` → "Demo Scenario" tab lets you pick any of the 5
  synthetic scenarios described below without needing a real file.
- `sample-data/demo_scenarios.json` — the exact OCR evidence + extracted
  fields used by each scenario (for judges who want to inspect the raw data).
- `sample-data/*.png` and `backend/sample_data/*.png` — synthetic English, Hindi
  and Kannada land-record scans used by the seed script and the tests.

| Scenario            | What it demonstrates                                             |
|----------------------|--------------------------------------------------------------------|
| `clean`              | High confidence, no issues → **auto-passes**                      |
| `poor_scan`          | Low OCR confidence throughout → routed to **human review**        |
| `area_mismatch` (default) | Plot area conflicts with the mutation register → **validation warning** |
| `duplicate_survey`   | Survey/khasra number collides with an existing record → **anomaly warning** |
| `missing_mutation`   | Mutation number/date absent from source → **review required**     |

---

## 10. OCR & LLM configuration (switching to real providers)

In `backend/.env`:

```env
OCR_PROVIDER=demo        # or: paddleocr
LLM_PROVIDER=demo        # or: anthropic
LLM_API_KEY=             # required if LLM_PROVIDER != demo
```

- `OCR_PROVIDER=paddleocr` requires `pip install paddlepaddle paddleocr`
  (not included by default — it's a large dependency).
- `LLM_PROVIDER=anthropic` calls the Claude API with a strict JSON schema
  prompt (see `backend/app/services/extraction/llm_provider.py`) that
  explicitly forbids inventing values and requires per-field confidence.

---

## 11. API documentation

Interactive Swagger/OpenAPI UI: http://localhost:8000/docs
Written summary: [`docs/API.md`](docs/API.md)

---

## 12. The 3-minute judge demo flow

1. Open **Dashboard**.
2. Click **Upload**.
3. Select the **Area Mismatch** demo scenario (pre-selected by default).
4. Click **Start AI Digitization** — watch the pipeline steps run.
5. See extracted fields with per-field confidence badges.
6. See the **area/mutation inconsistency** validation warning.
7. Click the `plot_area` field to open its **evidence panel** (OCR text,
   confidences, source page/region highlighted on the document preview).
8. Go to **Human Verification**.
9. Edit the uncertain `plot_area` field.
10. Click **Approve**.
11. See **VERIFIED DIGITAL LAND RECORD**.
12. Open **Audit Trail** — see the full UPLOAD → OCR → EXTRACTION →
    VALIDATION → EDIT → APPROVE history.
13. Return to **Dashboard** — see updated stats.

---

## 13. Testing

```bash
cd backend
source venv/bin/activate
python -m pytest tests/ -v   # needs requirements-dev.txt
```

Covers: confidence engine, validation engine (including the area-mismatch
and required-field rules), anomaly scoring, and a full end-to-end API test
(upload → process → extract → validate → edit → approve → audit →
dashboard → search), plus an RBAC test confirming OFFICER accounts cannot
verify records.

---

## 14. Known limitations (P0/P1 shipped, P2 intentionally out of scope)

**Implemented now (P0/P1):**
Upload, preprocessing hook, OCR (demo + real-provider interface), AI
extraction (demo + real-provider interface), confidence engine, validation
engine, anomaly engine, human verification (edit/approve/reject/unresolved),
evidence traceability, audit trail, dashboard, search, JWT auth + RBAC,
Docker Compose, Swagger docs.

**Future / P2 (not implemented):**
- Advanced ML-based anomaly detection (current engine is transparent
  rule-weighted, by design — not a black box).
- Additional Indian languages in the OCR layer beyond the architecture hook
  (`OCR_PROVIDER` is pluggable; only English demo evidence is included).
- Full GIS / cadastral map extraction (a simple approximate-location map was
  explicitly marked P2/optional in the spec).
- External government system integration (e.g. live land registry APIs).
- Continuous learning / model fine-tuning loop.
- Alembic migration history (the demo uses `Base.metadata.create_all` for
  zero-config startup; a `database/schema.sql` reference is included for
  teams that want to hand-author Alembic revisions for production).

---

## 15. Project structure

```text
Bhoomi_setu/
├── frontend/            Next.js app (TypeScript, Tailwind, Recharts)
├── backend/              FastAPI app (services/, routers/, models, tests/)
├── database/             Schema reference notes
├── sample-data/          Synthetic demo scenarios (JSON) + sample scans
├── docs/                 API.md, API_CONTRACT.md, ARCHITECTURE.md
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## 16. Security notes

- File type + size validation, filename sanitization on upload.
- JWT auth on every route except `/api/auth/login` and `/api/health`.
- RBAC enforced server-side (ADMIN / OFFICER / REVIEWER) — not just hidden
  in the UI.
- No secrets committed to source; `.env.example` files use placeholders only.
- Uploaded files are never executed; stored under `backend/uploads/` with a
  randomized filename.
- CORS restricted to `CORS_ORIGINS` in `.env`.

---

## 17. Disclaimer

BhoomiTrust AI is a hackathon MVP built for demonstration purposes on
entirely synthetic data. It does not connect to any real government land
registry. AI-generated confidence scores, validation warnings, and anomaly
scores are decision-support signals for an authorized human reviewer — they
are **not** a legal determination of ownership and **not** a fraud
detection verdict.
