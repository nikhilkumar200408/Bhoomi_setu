# Project state

**Bhoomi_setu** is the platform repository. Its existing BhoomiTrust workflows are maintained as a separate application area. The **Document AI module is domain-independent**: it is designed to process general business and institutional documents such as banking and loan agreements, insurance policies, vendor/legal contracts, regulatory circulars, public policies, and other supported PDFs. It must not assume that uploaded documents are land records. The goal is to add multi-document ingestion, OCR, cited Q&A, quote/claim verification, contradiction and amendment analysis, and human review without breaking existing platform workflows.

## Repository and architecture

- Integration branch: `dev`. Never push directly to `main`.
- Frontend: Next.js 14, TypeScript, Tailwind in `frontend/`.
- Backend: FastAPI + Motor in `backend/`; MongoDB; Docker Compose services use ports 3000 / 8000 / 27017.
- Backend routers include auth, documents, records, dashboard, search, audit and `document_ai`.
- Services include the existing OCR/extraction/validation/verification pipeline and `services/docai`.
- Document AI API contract: `docs/API_CONTRACT.md`; existing API documentation: `docs/API.md`.

## Current Document AI implementation (code-level snapshot)

- Indexing jobs and PDF text/OCR extraction exist.
- Retrieval combines BM25 with optional local Ollama embeddings (configured for BGE-M3) and reciprocal-rank fusion; lexical-only fallback remains available.
- Q&A is evidence-first and extractive; optional local Ollama drafting is marked unverified and cannot replace claims, citations, abstention or faithfulness.
- Page-level evidence and backend quote verification exist.
- Abstention uses adaptive lexical coverage heuristics; it is conservative but is not a semantic guarantee.
- Faithfulness is a verified-claim ratio, not a calibrated probability of truth.
- Contradiction detection is rule-based and focuses on structured facts such as percentages, INR amounts, area and duration.
- Amendment handling uses explicit amendment cues, base-document references and effective-date checks; unresolved cases need human review.
- Claim review is restricted to Revenue Officers and audited.
- The dedicated Document AI frontend supports upload/indexing, source selection, Q&A, citations, contradictions, amendments, and a financial calculator. PDF passage highlighting and a complete in-app review experience remain outstanding.

See `docs/IMPLEMENTATION_PROGRESS.md` for the detailed status and unverified test matrix. Do not treat historical test output as a fresh test run.

## Security and access decisions

- ADMIN and REVENUE_OFFICER are privileged reviewer roles.
- DATA_ENTRY_OPERATOR access is scoped to resources they own/upload, according to the backend ownership helpers.
- Foreign resources should return 404 to avoid leaking their existence.
- `/api/search` must escape user search input before regex use.
- `GET /api/records/public-verify/{id}` is intentionally public for QR certificate verification and must expose only the intended verification fields.
- Keep Document AI additive under `/api/document-ai`; do not reinterpret land-record `overall_confidence` as Document AI `faithfulness_score`.

## Local inference direction

- Document AI must not require external AI inference APIs or cloud API keys.
- Local runtime: Ollama. The first chat integration targets the already-installed `llama3.2` model; BGE-M3 remains the planned embedding model.
- Ollama drafting is opt-in, runs locally, and returns a clearly marked unverified draft only. It does not replace backend claims, citations, contradiction results, abstention, or faithfulness scoring. Runtime inference and safety tests still need to be run.
- For a backend running in Docker on macOS, configure the Ollama host explicitly (often `http://host.docker.internal:11434`); container `localhost` is not the Mac host.
- Do not expose the Ollama service publicly. A public deployment needs a separately secured inference host.
- Model downloads require internet initially; local inference can operate offline after weights are available.

## Environment and maintenance

- Backend development baseline: Python 3.12; Tesseract and Poppler are used by document processing. Install development dependencies from `backend/requirements-dev.txt`.
- OCR languages require the corresponding Tesseract traineddata files.
- A previously committed Fast2SMS credential was reported in Git history. Rotate it immediately if still active; never copy secrets into tracked files. History rewriting is a separate coordinated operation.
- Phase 9 CI now runs backend tests, frontend lint/build, and Docker Compose validation/image builds on dev/main pushes and pull requests. The manual end-to-end checklist remains required; record exact results before release.
