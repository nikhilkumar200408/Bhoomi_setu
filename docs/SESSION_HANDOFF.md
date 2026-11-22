# Session handoff

Updated: 2026-11-23. Read this first, then `docs/IMPLEMENTATION_PROGRESS.md`.

## Branch state (do not assume anything is merged)
| Branch | Content | State |
|---|---|---|
| `cleanup/audit-security-hardening` | `e488251` security hardening (leaked SMS key removed from env example, upload magic-byte check, JWT secret check outside demo mode, `.gitignore`) | pushed, awaiting review/merge into `dev` |
| `docs/handoff-audit-findings` | `098aa22` `docs/HANDOFF.md` with the full audit findings and the authorization recommendation for Pakhi | pushed, awaiting review/merge |
| `infra/docker-docs-fixes` | Docker, lint, requirements split and documentation fixes (this session) | pushed, awaiting review/merge |
| `main`, `neha_frontend`, `pakhi_backend` | untouched | do not modify |

All three branches are based on `dev` at `557f92f`. They are independent but overlap in a few files; expect small conflicts in `.gitignore`-adjacent and `.env.example` areas only if merged out of order (none observed in file lists: this branch does not touch `.gitignore`, `.env.example`, `config.py`, `documents.py`).

## Done this session (infra/docs only)
- Docker: frontend published on 3000 (matches CORS and README); `backend/.env` is optional; `DEMO_MODE`, `JWT_SECRET` and `CORS_ORIGINS` read from the root `.env`; frontend API URL passed as a build argument; frontend image installs with `npm ci` from `package-lock.json`; `frontend/public/` added so the `/app/public` copy works; `.dockerignore` files added so local `.env`, `node_modules` and `venv` never enter images.
- ESLint: added `frontend/.eslintrc.json` (`next/core-web-vitals`), fixed the one lint error (unescaped apostrophe), removed `eslint.ignoreDuringBuilds`. Lint now passes with 3 warnings; the production build passes with lint enforced.
- Python deps: test-only packages moved to `backend/requirements-dev.txt` (includes runtime file). `httpx` stays in runtime because the notifier uses it. `PyMuPDF` kept as instructed. `setup.sh` now installs the dev file.
- `setup.sh` and the README referenced a non-existent `python -m app.seed`; both now use `python -m app.seed_real_data`.
- Docs: product naming (Bhoomi_setu is the platform; BhoomiTrust AI is the existing land-record module), ports, seeded credentials (operator / revenue_officer), sample-data paths, missing routes in `docs/API.md`, contract title.

## Not verified
- `docker compose build` / `up`: no Docker daemon here. Only `docker compose config` was validated (passes with no `backend/.env` present). All Docker changes are untested at build and runtime.
- Backend test `test_hindi_and_kannada_samples_extract_native_script` fails here because Kannada tessdata is missing; it fails the same on `dev`.
- No CI exists in the repo (no `.github/`). The only development workflows found are `setup.sh` and the README test steps, both updated to `requirements-dev.txt`. If the team has CI outside the repo, it must install `requirements-dev.txt`.

## Still open (priority order)
1. Review and merge the three branches above; rotate the leaked Fast2SMS key (key remains in Git history).
2. Run `docker compose up --build` on a machine with Docker and confirm login from the browser works.
3. Pakhi: authorization and document ownership isolation (see `docs/HANDOFF.md` on `docs/handoff-audit-findings`), then the Document AI pipeline per `docs/API_CONTRACT.md`.
4. README rewrite of sections 4, 9, 12, 14 (still describe the old demo-scenario design and Officer/Reviewer roles); `sample-data/README.md` and `demo_scenarios.json` describe a demo provider that is no longer the default.
5. Neha: frontend branding strings still say "BhoomiTrust AI" (`frontend/app/layout.tsx`, certificate pages); 3 lint warnings (two `useEffect` dependencies, one `<img>`); Document AI screens.
6. Dev-only code to review with the team: `ocr/demo_provider.py`, `extraction/demo_provider.py`, `paddleocr_provider.py` (PaddleOCR is not in requirements).
