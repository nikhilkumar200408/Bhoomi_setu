# Session handoff

Updated: 2026-11-23. Read this file, then `docs/PROJECT_STATE.md`, `docs/IMPLEMENTATION_PROGRESS.md`, and `docs/API_CONTRACT.md`.

## Verified repository state

- Integration branch: `dev`. Never push directly to `main`.
- The Document AI backend and ownership-isolation implementation are already committed on `dev`; do not apply the old `document-ai-backend.patch` or repeat that work.
- The previous handoff's references to local-only `feature/document-ai-backend`, an unpushed patch, and base commit `09fab17` are historical and stale.
- At the start of this implementation session, the known `dev` HEAD was `6f6af79`. Always re-check the live branch before writing.
- Changes in this handoff are repository state notes, not a claim that tests were run in the current session.

## Current capability snapshot

- Existing BhoomiTrust AI land-record workflows, authentication/RBAC, uploads, OCR/extraction, records, verification, audit, dashboard and search must remain intact.
- Document AI backend provides PDF text/OCR indexing jobs, BM25 lexical retrieval, extractive cross-document QA, page-level source quotes, quote verification, abstention, numeric/rule-based contradictions, basic amendment tracking, and Revenue Officer claim review.
- It does not yet integrate a local LLM or embeddings. There is no hybrid vector retrieval and no dedicated Document AI frontend.
- OCR for scanned PDFs, table extraction quality, Indic-language QA, frontend integration, and full end-to-end operation still require verification.
- Faithfulness is currently a verified-claim ratio, not a calibrated probability or semantic truth score.

## Next implementation sequence

1. Reconcile documentation with the code and current Git history.
2. Add explicit, disabled-by-default configuration for a local Ollama service; do not introduce cloud AI APIs or require API keys.
3. Verify current ingestion/OCR/indexing behavior with focused backend tests, including a scanned-PDF case.
4. Integrate Ollama chat using a configurable local model (initial candidate: `qwen3:4b`); fail safely when the service is unavailable.
5. Add local embeddings (initial candidate: `bge-m3`) and persist/rebuild vectors safely.
6. Add hybrid BM25 + dense retrieval and evaluate against a small, documented test set.
7. Generate only evidence-grounded candidate answers; verify every claim and citation; abstain on weak or conflicting evidence.
8. Improve contradiction and amendment handling with explicit scope, dates, and human review for unresolved relationships.
9. Build the Document AI frontend against `docs/API_CONTRACT.md`, with real APIs and no mock results.
10. Run regression, security, frontend, and end-to-end tests; update this handoff with actual commands and outcomes.

## Local model and runtime decisions

- No external inference API key or cloud inference dependency is allowed for Document AI.
- Start with local Ollama and a quantized Qwen3 4B model; benchmark before considering larger models.
- Candidate embedding model: BGE-M3. Measure memory, latency, storage, and retrieval quality before treating it as production-ready.
- If the backend runs in Docker on macOS, `localhost:11434` inside the container is not the host Ollama service. Use a configurable host URL (commonly `http://host.docker.internal:11434`) for local development.
- Keep Ollama bound to a trusted local interface; do not expose its port publicly.
- A locally running Mac is not automatically an inference host for a public deployment. Production hosting must be designed separately.
- Downloading model weights/dependencies requires internet initially; inference can run locally afterward.

## Verification rules

- Do not report a test as passed unless it was run in the current working environment and its output was checked.
- Record exact commands, environment assumptions, skipped tests, and failures.
- Never claim that a scanned-PDF, table, frontend, Docker, or deployment path works without a corresponding test.
- Preserve the existing land-record APIs and data. Document AI remains additive under `/api/document-ai`.
- Review `git diff`, secrets, accidental deletions, and branch state before every commit/push. Never force-push.

## Resume commands (user's Mac checkout)

```bash
cd "/Users/nikhilkumar/Downloads/BhoomiTrust-AI 7/Bhoomi_setu"
git status --short --branch
git fetch origin
git log -1 --oneline --decorate
```

Only pull/rebase when the working tree is clean and the remote branch has moved. Do not apply the historical patch.
