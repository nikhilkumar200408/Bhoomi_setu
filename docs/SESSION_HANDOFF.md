# Session handoff

Updated: 2026-11-23. Read this first, then `docs/PROJECT_STATE.md` and `docs/IMPLEMENTATION_PROGRESS.md`.

## State
- Base: `dev` at `09fab17` (already contains the security hardening, audit handoff and infra/docs branches).
- This session (done in a fresh clone, no Docker, no push credentials): backend ownership isolation + the whole Document AI backend + tests + docs. All of it is on local branch `feature/document-ai-backend`, delivered as a patch, **not pushed**.
- The previous session's uncommitted local work on Nikhil's Mac was not visible from here. Check `git status` / `git stash list` there before applying the patch and resolve any overlap by hand (likely files: `deps.py`, `documents.py`, `records.py`, `main.py`).

## Next task (in order)
1. Apply the patch on the Mac checkout of `dev`, run `cd backend && pip install -r requirements-dev.txt && pytest -q`, then push (see "Resume").
2. Neha: Document AI frontend per `docs/API_CONTRACT.md` (upload -> index status -> ask with cited evidence -> contradictions/amendments -> claim review). Also the branding strings and 3 lint warnings.
3. `docker compose up --build` on a machine with Docker; confirm login and a Document AI round trip.
4. Rotate the leaked Fast2SMS key; README sections 4, 9, 12, 14 rewrite.

## Decisions not to redo
- Ownership: reviewers (ADMIN, REVENUE_OFFICER) see all; operators only their own uploads. 404 for foreign resources.
- No LLM or embeddings in Document AI; extractive answers, backend-verified quotes, abstain when under 50% key-term coverage.
- Precedence between conflicting documents only via amendment language + base reference + reached effective date, never upload order.

## Not verified
Frontend build, Docker build/run, Indic OCR (tessdata missing here), Hindi/Marathi question answering, scanned-PDF OCR path (only the image OCR code path is shared with existing tests; no scanned-PDF test yet).

## Resume
```
git checkout dev && git pull
git apply --3way /path/to/document-ai-backend.patch   # or: git am document-ai-backend.mbox
cd backend && pytest -q
git push origin HEAD:dev   # only after tests pass and you have reviewed the diff
```
