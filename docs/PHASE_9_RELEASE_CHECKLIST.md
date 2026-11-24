# Phase 9 — Regression, security and release readiness

Phase 9 adds repeatable CI checks and a release checklist. A green CI run is a
necessary gate, not proof that the application is production-ready.

## Automated checks

The workflow at `.github/workflows/ci.yml` runs on pushes and pull requests
to `dev` and `main`:

1. **Backend:** installs `backend/requirements-dev.txt` and runs the complete
   pytest suite. The test suite uses an isolated in-memory Mongo-compatible
   database; it does not touch a developer's local MongoDB volume or uploads.
2. **Frontend:** runs `npm ci`, `npm run lint`, and `npm run build`.
3. **Containers:** validates `docker-compose.yml` and builds the backend and
   frontend images.

Ollama is disabled in CI because it is an optional local drafting/embedding
service. Its absence must not prevent evidence-backed Q&A or the regression
suite from running.

## Security coverage already present in backend tests

- Document AI ownership isolation (foreign documents return not-found).
- Role restrictions for claim review.
- Invalid upload rejection and request validation.
- Evidence quote verification and citation re-verification.
- Unindexed-document rejection and indexing idempotency.
- Safe abstention and cross-document contradiction/amendment scenarios.

Keep these tests in the full suite; do not replace them with mocked success
responses. Add a regression test whenever a security or evidence-handling bug
is fixed.

## Document AI workspace reset behavior

The Reset action clears the active selection of source documents, question,
answer, citations, claims, contradiction/amendment results, transient errors,
indexing message and displayed calculation result. It does **not** delete
uploaded files, indexed page data, vector records, or indexing history.
Users can select the retained source documents again after resetting.

## Manual end-to-end release checklist

Run against a fresh local Docker build and a non-production test account:

- [ ] Sign in as a normal authorized user.
- [ ] Upload a native-text PDF and a scanned PDF; confirm upload errors are
      shown per file and successful files remain available.
- [ ] Index both files; confirm progress reaches a terminal state and a failed
      job exposes a safe error message.
- [ ] Ask a question with one source and with multiple sources.
- [ ] Verify every displayed citation has the correct filename, page and
      verbatim quote; verify unsupported questions abstain.
- [ ] Compare conflicting values and check that both source quotations appear.
- [ ] Check amendment/effective-date cases, including unresolved cases.
- [ ] Reset the workspace; confirm no source remains selected and the old
      question/results disappear, while uploaded files remain listed and can
      be selected again.
- [ ] Sign in as a second user and confirm the first user's documents, jobs
      and answers cannot be accessed.
- [ ] Confirm the legacy land-record upload, verification, audit and dashboard
      workflows still work.
- [ ] Check Hindi Q&A, table-heavy PDFs and multi-page clauses using
      representative fixtures.

## Local commands

From the repository root:

```bash
docker compose config --quiet
docker compose build backend frontend
cd backend
source venv/bin/activate
python -m pytest tests/ -q
cd ../frontend
npm ci
npm run lint
npm run build
```

Do not use `docker compose down -v` during validation: it deletes named
MongoDB/upload volumes. Do not test against production documents or secrets.

## Deployment gate

Before a real deployment:

- Set a strong unique `JWT_SECRET`; never use the demo default.
- Set `DEMO_MODE=false` and disable demo seeding.
- Restrict `CORS_ORIGINS` to the actual frontend origin.
- Keep MongoDB private; use authenticated network access and backups.
- Keep uploaded files and Ollama private; do not expose local model ports.
- Rotate any credentials previously committed to Git history.
- Confirm HTTPS, backup/restore, retention/deletion policy, monitoring and
  incident response for the target environment.
- Record the CI run URL, commit SHA, manual test evidence and deployment
  environment in the release notes.

A successful build alone is not a production-readiness certification.
