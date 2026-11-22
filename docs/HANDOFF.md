# Project progress and session handoff

Last updated: 2026-11-23. Maintained by the integration owner's Claude sessions; update at the end of each session.

## Team ownership
| Area | Owner |
|---|---|
| Integration, audit, hygiene, docs | Integration owner (with Claude) |
| Frontend (`neha_frontend`) | Neha |
| Backend + Document AI pipeline (`pakhi_backend`) | Pakhi |

Rules: never modify `main`, `neha_frontend` or `pakhi_backend` from cleanup work; no force-push; no automatic merges; nothing merged until the integration owner reviews it.

## Status
- Commit `e488251` on `cleanup/audit-security-hardening` (security hardening) is **awaiting review and merge into `dev`**. Do not assume it is merged.
- Document AI ingestion, chunking, embedding, retrieval, Q&A, contradiction and amendment logic: **not started, owned by Pakhi**. `docs/API_CONTRACT.md` defines the `/api/document-ai` surface; none of it exists in the backend yet.
- Existing land-record app (`/api/auth`, `/api/documents`, `/api/records`, `/api/dashboard`, `/api/search`, `/api/audit`) is the working baseline.

## Verified facts (2026-11-23)
- Backend tests on the hardening branch: 18 passed, 1 failed. The failure (`test_hindi_and_kannada_samples_extract_native_script`) is environmental (Kannada tessdata missing) and also fails on `dev`.
- Frontend `tsc --noEmit` passes. Lint and production build were not run.
- Docker was not run.

## Action required outside the repo
- **Rotate the Fast2SMS API key** that was committed in `backend/.env.example`. It remains in Git history (history was deliberately not rewritten).

## Open items in priority order
1. Review and merge `e488251` into `dev`.
2. Rotate the leaked Fast2SMS key (owner).
3. Fix Docker/compose defects below (frontend image build, CORS port, missing `.env`).
4. Pakhi: authorization and document ownership isolation (below).
5. Pakhi: Document AI pipeline per `docs/API_CONTRACT.md`.
6. Documentation fixes below.
7. Remove verified-unused dependencies below.
8. Neha: Document AI screens (library, ask, evidence, contradictions, amendments, claims).

## Configuration mismatches found
| # | Issue | Evidence | Suggested fix |
|---|---|---|---|
| 1 | Compose frontend published on 3004 but backend CORS allows only `http://localhost:3000`; browser calls from the Docker frontend are blocked | `docker-compose.yml` (`3004:3000`, `CORS_ORIGINS`), README says 3000 | Publish `3000:3000` or add the 3004 origin to `CORS_ORIGINS` |
| 2 | Frontend Dockerfile copies `/app/public`, but `frontend/public` is not in the repo; the image build fails at that step | `frontend/Dockerfile`, no `frontend/public` | Add `frontend/public/.gitkeep` or remove the COPY line |
| 3 | Compose `env_file: ./backend/.env` is mandatory; `docker compose up` fails on a fresh clone | `docker-compose.yml` | Mark it `required: false` or document `cp backend/.env.example backend/.env` |
| 4 | Compose hardcodes `DEMO_MODE: "true"`, so the JWT-secret check added in `e488251` never triggers under Docker and the default secret is accepted | `docker-compose.yml` | Make `DEMO_MODE` and `JWT_SECRET` come from the environment; drop the default secret |
| 5 | Frontend Dockerfile sets `NEXT_PUBLIC_API_BASE_URL` at build time to localhost and ignores the compose runtime value (Next inlines it at build) | `frontend/Dockerfile` | Pass it as a build arg |
| 6 | Frontend Dockerfile uses `npm install` from `package.json` only, ignoring `package-lock.json` | `frontend/Dockerfile` | Copy the lock file and use `npm ci` |
| 7 | `OCR_PROVIDER` defaults differ: code and compose use `tesseract`, root and backend `.env.example` say `demo` | `config.py`, `.env.example` | Align the examples with the real default |
| 8 | `next.config.js` has `eslint.ignoreDuringBuilds: true`, so lint errors never fail a build | `frontend/next.config.js` | Fix lint, then remove the flag (Neha) |
| 9 | Backend `requirements.txt` ships test packages (pytest, pytest-asyncio, httpx, mongomock-motor) in the runtime image | `backend/requirements.txt` | Split into `requirements-dev.txt` |

## Compatibility of `e488251` with the API contract and Docker
- Contract: `/api/documents/*` paths, methods and `DocumentOut` fields are unchanged. One value change: `file_type` is now normalized from the extension (`application/pdf`, `image/png`, `image/jpeg`) instead of the client-sent content type. The frontend only compares it to `application/pdf` and displays it, so it is compatible. A mismatched upload now returns 400, which fits the contract's error convention. Pakhi should know the contract's section 2.1 says not to change this schema silently; this is a value normalization, not a field change.
- Docker: compatible. `DEMO_MODE` is hardcoded true in compose, so startup is unchanged (see mismatch 4). The ignore rules do not affect the build contexts. Not tested by running Docker.

## Recommendation for Pakhi: authentication, authorization and ownership isolation
Current state (from code review):
- JWT carries `sub` and `role`; `get_current_user` reloads the user from the database on each request. Good: the role is taken from the database, not the token.
- `require_roles` is applied on uploads, process, field edit and verify. Read endpoints (`GET /api/documents`, `/{id}`, `/{id}/file`, `/api/records*`, `/api/search`, `/api/audit`, dashboard) use only `get_current_user`.
- `documents.uploaded_by` is stored but never used in any query. Any authenticated user can list, fetch and download every document and read every record and the full audit log.
- `/api/documents/{id}/process` has no ownership or state check beyond role.
- Token expiry is 8 hours; there is no revocation, and login has no rate limiting.
- `datetime.utcnow()` is deprecated (naive datetimes) in `auth.py`.

Recommended implementation (for the Document AI work, keep the land-record routes' behaviour unless a decision is made):
1. Decide the access model first and write it into the contract: is it per-user ownership, per-organisation workspace, or role-wide visibility for officers? The land-record flow currently needs officers to see operators' uploads, so a blanket owner-only filter would break it.
2. For new `/api/document-ai` resources, store `owner_id` (and `workspace_id` if used) on every document, chunk, index entry, answer, claim, contradiction and amendment record. Enforce it in the query filter, not after the fetch, so counts and search cannot leak.
3. Put the check in one shared dependency (for example `get_accessible_document(document_id, user)`) and return 404, not 403, for documents the user cannot see.
4. The vector and keyword index must be filtered by the same access scope at query time. Do not retrieve then filter, and never share a global index across users without a per-document access filter.
5. Gate `/file`, `/process`, re-verify and human-review routes with the same dependency. Human review of a claim should require a reviewer role and write an audit entry.
6. Treat uploaded document text as untrusted: pass it to the LLM only as quoted data, never as instructions, and verify every citation against stored page text before returning it.
7. Add tests: user B gets 404 on user A's document, file, answer and claim; index search never returns another user's chunks; role restrictions per route.
8. Smaller items: replace `utcnow()` with timezone-aware UTC, add login rate limiting, and consider a shorter token lifetime.

## Documentation consistency findings
- `docs/API.md` documents only the land-record routes. It omits `GET /api/records/officer-queue`, `/api/records/public-verify/{id}`, `/api/records/export.csv`, `/api/dashboard/user-activity` and the `/api/document-ai` contract pointer. Add them, and link to the contract as the source of truth for Document AI.
- `docs/API.md` examples use `sample_data/...`, but the files live in `backend/sample_data/`; also the `sample-data` folder at the root should be checked for duplication with it.
- Naming is inconsistent: product is "BhoomiTrust AI" in README, API and backend title, DB name `bhoomitrust_db`; the repository and the Document AI work are "Bhoomi_setu". Decide the product name before the README is rewritten.
- README still describes demo-first behaviour and has no mention of Document AI scope or this handoff file; ports must match the compose fix.
- `docs/ARCHITECTURE.md` and README section 2 both describe the pipeline; keep one and link from the other.
- Contract section 2.1 and the compatibility notes agree with the code for existing routes.

## Unused dependencies and dead code (not yet removed)
Verified by import search of `backend/app` and `frontend/{app,components,lib}`:
- `python-dotenv`: no import (pydantic-settings reads `.env` itself). Candidate for removal.
- `PyMuPDF` (`fitz`): no import in the app. Candidate, but Pakhi's PDF extraction may want it, so confirm with Pakhi before removing.
- `argon2-cffi` and `pymongo`: not imported directly; they are used indirectly (passlib scheme, motor dependency). Keep.
- Frontend: `framer-motion`, `recharts`, `qrcode.react`, `lucide-react` and `clsx` are all imported. No unused frontend dependency found.
- `paddleocr_provider.py` and `ocr/demo_provider.py` are selectable providers; `PaddleOCR` is not in requirements, so that provider fails if selected. Keep, document, or remove after a team decision.
- Not removed: nothing was deleted in this pass.
- Not checked: unused React components, unused CSS, unused exports.

## Next session should
1. Check whether `e488251` is merged into `dev`.
2. Re-run backend tests and frontend lint/build on `dev`.
3. Apply the Docker and docs fixes above on a branch off `dev` (not on Neha's or Pakhi's branches).
