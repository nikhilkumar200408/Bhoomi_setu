# Implementation progress

Status key: Done, Partial, Not started, Not verified. Updated 2026-11-23 after the first Universal Ingestion Engine implementation.

## Existing platform workflows (separate from domain-independent Document AI)

| Area | Status | Notes |
|---|---|---|
| Auth (JWT, password hashing, roles) | Done in code | Regression tests still required after Document AI changes |
| Upload and batch upload | Done in code | Validate size/type and ownership in tests |
| OCR and extraction pipeline | Done in code | Existing workflow preserved; scanned-PDF path and Indic language data need explicit verification |
| Records, verification/signature, audit, dashboard, search | Done in code | Preserve existing behavior |
| Existing frontend | Done in code | Prior handoff reports three lint warnings; re-run lint/build before release |

## Document AI backend

| Area | Status | Notes |
|---|---|---|
| Universal page extraction foundation | Partial | Native PDF text plus layout blocks and PDF-point bounding boxes; low-text pages fall back to Tesseract OCR with line boxes and confidence metadata |
| Table extraction | Partial | Native PDF table detection plus conservative adjacent-page table continuation when exact non-empty headers match; OCR table reconstruction and real-document fixtures remain pending |
| Multi-page documents | Partial | Clause-like sections are grouped across pages with page-level source spans; grouping is heuristic and does not rewrite source-page text |
| Extraction quality metadata | Partial | Text/OCR method, character/word counts, OCR confidence, quality flags and warnings are stored with indexed pages; confidence is not a truth score |
| BM25 lexical retrieval | Done in code | Kept as a first retrieval channel in hybrid mode |
| Cross-document Q&A | Partial | Extractive source passages, not LLM-generated answers |
| Page citations and quote verification | Done in code | Quotes are checked against stored page text |
| Abstention | Partial | Lexical key-term coverage heuristic; requires evaluation |
| Claim status and faithfulness | Partial | Verified-claim ratio; not a calibrated truth probability |
| Contradiction detection | Partial | Rule-based numeric facts (percent, INR, area, duration) |
| Amendment tracking | Partial | Basic explicit-cue/base-reference/effective-date rules |
| Human review | Done in code | Revenue Officer only; source evidence remains unchanged |
| Document AI frontend | Partial | Upload/indexing, source selection, Q&A, evidence, contradictions, amendments, calculator and workspace Reset are implemented; PDF passage highlighting and in-app claim review remain outstanding |
| Local Ollama LLM | Partial | Optional local Llama 3.2 draft integration added; output is marked unverified and cannot replace evidence-backed answers |
| BGE-M3 embeddings / vector retrieval | Partial | Opt-in Ollama embeddings, MongoDB chunk-vector storage, batch indexing, query embeddings, cosine ranking and RRF fusion implemented. Semantic-only matches are downgraded to PARTIALLY_SUPPORTED and require human review. Real-model evaluation and threshold tuning remain |

## Access control

| Item | Status | Notes |
|---|---|---|
| Existing app ownership isolation | Done in code | Prior code includes an operator-isolation integration test |
| Document AI document/job/answer access checks | Done in code | Re-run tests in the current environment |
| Revenue Officer claim review authorization | Done in code | Verify audit event and role rejection paths |

## Infrastructure and documentation

| Item | Status | Notes |
|---|---|---|
| Docker Compose and frontend/backend configuration | Present in repository | Phase 9 CI validates Compose and builds both images; local runtime round trip remains required |
| Runtime/dev Python requirements split | Present in repository | Development dependencies live in requirements-dev.txt |
| API contract | Present | Keep synchronized with actual implementation |\n| CI regression workflow | Added | `.github/workflows/ci.yml` runs backend pytest, frontend lint/build, and Docker image builds on dev/main pushes and pull requests |\n| Phase 9 release checklist | Added | `docs/PHASE_9_RELEASE_CHECKLIST.md`; manual end-to-end, security and deployment checks still need execution |
| Session handoff | Corrected | Historical patch instructions removed |
| Project state | Corrected | Domain-independent scope documented |
| README cleanup | Not verified | Do not mark complete without reviewing requested sections |
| Secret rotation | Outstanding | Rotate any previously committed credentials still active; never copy secrets into tracked files |

## Test evidence and limitations

Current user-reported focused test run on 2026-11-23: `9 passed` for `tests/test_docai_embeddings.py` and `tests/test_docai_ollama.py`. Hybrid retrieval integration has been committed but awaits local regression tests.

Still not verified:
- New ingestion tests and full backend suite after these changes.
- Representative scanned-PDF OCR and extraction quality.
- Table extraction accuracy on native and scanned PDFs.
- Hindi/Marathi/Kannada OCR and question answering.
- Frontend lint/build.
- Docker build and full compose round trip.
- Ollama inference latency and memory use.
- Dense embedding retrieval quality.
- End-to-end multi-domain Document AI workflow.

## Next phases

1. **Local LLM foundation:** optional Ollama client and safe unverified-draft response; source-backed QA remains authoritative. Focused tests passed before ingestion changes.
2. **Universal document ingestion:** foundation implemented partially (native layout blocks, page coordinates, OCR line provenance, metadata and optional native table detection). Next: OCR table reconstruction, table/section evaluation on representative banking, insurance and contract PDFs, and stronger reading-order validation.
3. **BGE-M3 embeddings and hybrid retrieval:** initial opt-in BM25 + vector pipeline is implemented; next install the local BGE-M3 model, run end-to-end indexing/Q&A tests, benchmark retrieval quality and tune thresholds.
4. **Zero-guessing verification:** sentence/claim-level evidence mapping, exact quote verification, conservative abstention, and calibrated reporting.
5. **Document intelligence:** improve cross-document contradictions, amendment chains, effective dates, and current-version reasoning with multi-domain fixtures.
6. **Document AI frontend:** independent upload/indexing, evidence viewer, Q&A, contradiction/amendment views, PDF passage highlighting, and review workflow.
7. **Regression, security and end-to-end validation:** preserve existing platform workflows and test banking, insurance, contracts, policies, scanned PDFs, tables, and multilingual cases.

Do not call the system "complete" or "production-ready" until outstanding items have been tested.


## Phase 9 execution status (2026-11-23)

- **Implemented in repository:** GitHub Actions CI for backend regression tests,
  frontend lint/production build, Docker Compose validation and backend/frontend
  image builds.
- **Implemented in UI:** Document AI Reset clears selected source documents
  and active Q&A/evidence state without deleting uploaded files or indexed data.
- **Documented:** manual end-to-end, security and deployment gates in
  `docs/PHASE_9_RELEASE_CHECKLIST.md`.
- **Not yet verified:** first remote CI run after these commits, fresh full local
  test/build run, manual reset interaction, representative real-document
  validation, and a secured non-demo deployment. Do not mark Phase 9 complete
  until those checks pass and evidence is recorded.


## Phase 10 — evidence review, explainability and source expansion (2026-11-23)

| Feature | Status | Notes |
|---|---|---|
| Faithfulness recalibration | Implemented in code | Score counts only fully SUPPORTED claims with verified quotes; partial, contradicted, unsupported and manually corrected claims do not count. Separate question-term coverage metric avoids confusing groundedness with retrieval coverage. |
| Reset visibility | Implemented in code | Always-visible Reset workspace action moved to the page header; manual viewport verification still required. |
| Citation and important-point highlighting | Implemented in code | Source quotes and key terms/numbers receive amber highlighting in the answer and evidence panel. |
| Analytics | Implemented in code | Claim-status distribution and evidence-per-document charts added alongside indexing and quality charts. |
| LLM one-line summary | Implemented in UI | Model draft is presented as a concise first-sentence summary and remains explicitly unverified. |
| Human audit and correction | Implemented in code | Revenue Officer correction endpoint stores corrected wording separately, keeps source evidence immutable, and exposes answer audit history. Tests added; CI/manual verification pending. |
| Hindi query support | Implemented in code | Hindi-selected queries use local Ollama translation for English-source retrieval; OCR provider already tries eng/hin/kan. Requires Ollama enabled and Tesseract language packs; Hindi end-to-end tests remain pending. |
| Public web-page ingestion | Implemented in code | HTTPS-only, exact-host allowlist, public-IP validation, redirects blocked, robots.txt checked, response/time/size bounded; extracted page text is indexed as a traceable source. Only approved public pages; JS/login/paywall bypass is not supported. Security tests and operator configuration remain pending. |
| PDF source highlight | Planned | Link citations to page viewer with exact text-span highlighting. |

Do not report Phase 10 complete until backend tests, frontend lint/build, security tests, and manual Hindi/reset/citation workflows pass.


## Phase 10 implementation update (2026-11-23)

- Implemented: supported-claim faithfulness ratio, visible workspace Reset, highlighted source citations/key facts, claim-status and evidence-source charts, concise LLM summary presentation.
- Implemented: Revenue Officer claim correction with immutable original text/evidence and answer-scoped audit history.
- Implemented: local Ollama Hindi query translation and UI fallback notice; OCR engine supports English/Hindi/Kannada language passes when the corresponding traineddata is installed.
- Implemented: allowlisted public webpage import with HTTPS-only URLs, exact-host allowlist, public IP validation, redirects disabled, robots.txt check, bounded fetch and provenance metadata. Configure WEB_IMPORT_ALLOWED_DOMAINS as a comma-separated list of exact hostnames. JavaScript-rendered, login-only and paywalled pages are intentionally unsupported.
- Not verified: latest full CI, frontend production build, manual reviewer correction, Hindi retrieval against representative Hindi PDFs, webpage import security tests, and actual browser reset visibility.
