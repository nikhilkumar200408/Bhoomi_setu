# Implementation progress

Status key: Done, Partial, Not started, Blocked. Updated 2026-11-23.

## Existing land-record application
| Area | Status | Notes |
|---|---|---|
| Auth (JWT, bcrypt/argon2, roles) | Done | Ownership isolation not implemented; assigned to Pakhi |
| Upload, batch upload, process pipeline (OpenCV, Tesseract eng/hin/kan, regex extraction) | Done | Kannada OCR test needs tessdata installed |
| Records, verification with signature, audit log, dashboard, search | Done | |
| Frontend for the above | Done | 3 lint warnings remain |

## Document AI (`docs/API_CONTRACT.md`)
| Area | Status | Owner |
|---|---|---|
| Ingestion, chunking, embeddings, indexing, retrieval | Not started | Pakhi |
| Question answering with page-level citations, quote verification | Not started | Pakhi |
| Claim verification, faithfulness score, human review | Not started | Pakhi |
| Contradiction detection, amendment tracking | Not started | Pakhi |
| Document AI frontend screens | Not started | Neha |

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

## Test results (this branch)
- `pytest -q` in `backend`: 17 passed, 1 failed (Kannada OCR, environmental, also fails on `dev`).
- `next lint`: 0 errors, 3 warnings. `npm run build`: passed.
- `docker compose config -q`: passed. Docker builds: not run.
