# Implementation progress

Status key: Done, Partial, Not started, Blocked. Updated 2026-11-23 (second update).

## Existing land-record application
| Area | Status | Notes |
|---|---|---|
| Auth (JWT, bcrypt/argon2, roles) | Done | Ownership isolation not implemented; assigned to Pakhi |
| Upload, batch upload, process pipeline (OpenCV, Tesseract eng/hin/kan, regex extraction) | Done | Kannada OCR test needs tessdata installed |
| Records, verification with signature, audit log, dashboard, search | Done | |
| Frontend for the above | Done | 3 lint warnings remain |

## Document AI (`docs/API_CONTRACT.md`)
| Area | Status | Notes |
|---|---|---|
| Ingestion/indexing (PDF text, OCR for scans/images), jobs, idempotent re-index | Done (backend) | Lexical BM25 retrieval; no embeddings, no LLM |
| Question answering with page-level citations, backend quote verification, abstention | Done (backend) | Extractive only |
| Claim statuses, faithfulness (verified-claim ratio), re-verify endpoint, human review | Done (backend) | Review is REVENUE_OFFICER only, audited |
| Contradiction detection, amendment tracking, effective dates, cycle check | Done (backend) | Rule-based: numeric facts (percent, rupees, area, duration) only |
| Document AI frontend screens | Not started | Neha |
| Pagination cursor, `UNRESOLVED`/`SUPERSEDED` states, non-numeric clause comparison, Hindi/Kannada question terms | Not done | Known limitations |

## Security
| Item | Status |
|---|---|
| Ownership isolation (documents, file download, records, edit, audit, search, dashboard, CSV) | Done, 1 integration test (`test_documents_records_audit_are_isolated_between_operators`) |
| Document AI access checks (index, ask, answers, contradictions, amendments, review) | Done, tested |

## Infrastructure and documentation (this branch)
| Item | Status | Verification |
|---|---|---|
| Frontend/backend port and CORS alignment | Done | `docker compose config` only; not run |
| Frontend Dockerfile (`public`, `npm ci`, runtime API URL arg) | Done | Not built (no Docker daemon); `npm ci` and `npm run build` pass locally |
| Compose works without `backend/.env` | Done | `docker compose config` passes with the file absent |
| `.dockerignore` files | Done | Not built |
| ESLint enforced in build | Done | `next lint`: 0 errors, 3 warnings; `npm run build` passes |
| Runtime vs dev Python requirements | Done | `import app.main` works with runtime file only; 17 tests pass with dev file |
| README/API docs corrections | Done | Manual review against code |
| README sections 4, 9, 12, 14 rewrite | Not started | |
| Security hardening (`e488251`) | Pushed, not merged | 18 tests pass on that branch |
| Audit handoff (`098aa22`) | Pushed, not merged | |

## Test results (latest)
- `pytest -q` in `backend` (Python 3.12, Tesseract eng only): 28 passed, 1 deselected (`test_hindi_and_kannada_samples_extract_native_script`, needs `hin`/`kan` tessdata). 11 of the 28 are new (`tests/test_document_ai.py`).
- Not run in this session: frontend lint/build, Docker build/up (no Docker daemon, no frontend changes made).

## Test results (infra branch, earlier)
- `pytest -q` in `backend`: 17 passed, 1 failed (Kannada OCR, environmental, also fails on `dev`).
- `next lint`: 0 errors, 3 warnings. `npm run build`: passed.
- `docker compose config -q`: passed. Docker builds: not run.
