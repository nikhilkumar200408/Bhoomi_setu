# Implementation progress

Status key: Done, Partial, Not started, Not verified. Updated 2026-11-23 after reviewing the current `dev` source.

## Existing platform workflows (separate from domain-independent Document AI)

| Area | Status | Notes |
|---|---|---|
| Auth (JWT, password hashing, roles) | Done in code | Regression tests still required after Document AI changes |
| Upload and batch upload | Done in code | Validate size/type and ownership in tests |
| OCR and extraction pipeline | Done in code | Scanned-PDF path and Indic language data need explicit verification |
| Records, verification/signature, audit, dashboard, search | Done in code | Preserve existing behavior |
| Existing frontend | Done in code | Prior handoff reports three lint warnings; re-run lint/build before release |

## Document AI backend

| Area | Status | Notes |
|---|---|---|
| PDF text extraction/OCR indexing jobs | Partial | Implemented; scanned PDF and table quality not fully verified |
| BM25 lexical retrieval | Done in code | No dense vectors yet |
| Cross-document Q&A | Partial | Extractive source passages, not LLM-generated answers |
| Page citations and quote verification | Done in code | Quotes are checked against stored page text |
| Abstention | Partial | Lexical key-term coverage heuristic; requires evaluation |
| Claim status and faithfulness | Partial | Verified-claim ratio; not a calibrated truth probability |
| Contradiction detection | Partial | Rule-based numeric facts (percent, INR, area, duration) |
| Amendment tracking | Partial | Basic explicit-cue/base-reference/effective-date rules |
| Human review | Done in code | Revenue Officer only; source evidence remains unchanged |
| Document AI frontend | Not started | Must use the documented API contract |
| Local Ollama LLM | Partial | Optional local Llama 3.2 draft integration added; output is marked unverified and cannot replace evidence-backed answers. Runtime and regression tests pending |
| BGE-M3 embeddings / vector retrieval | Not started | Requires storage design, indexing and evaluation |
| Semantic clause comparison | Not started | Do not label lexical/rule-based matches as semantic AI |

## Access control

| Item | Status | Notes |
|---|---|---|
| Existing app ownership isolation | Done in code | Prior code includes an operator-isolation integration test |
| Document AI document/job/answer access checks | Done in code | Re-run tests in the current environment |
| Revenue Officer claim review authorization | Done in code | Verify audit event and role rejection paths |

## Infrastructure and documentation

| Item | Status | Notes |
|---|---|---|
| Docker Compose and frontend/backend configuration | Present in repository | Prior handoff reported config validation; rebuild/retest before release |
| Runtime/dev Python requirements split | Present in repository | Recheck dependency installation in clean environment |
| API contract | Present | Keep synchronized with actual implementation |
| Session handoff | Corrected | Historical patch instructions removed |
| Project state | Corrected | Branch/history references must match live repository |
| README cleanup | Not verified | Do not mark complete without reviewing requested sections |
| Secret rotation | Outstanding | A previously committed Fast2SMS key was reported; rotate it and remove active use. History cleanup requires separate careful review. |

## Test evidence and limitations

The previous handoff recorded a backend test run of 28 passed and 1 deselected under Python 3.12 with English Tesseract data, but this result has not been re-run in the current implementation session. Treat it as historical evidence only.

Not yet verified in the current session:
- Backend full test suite and regression suite.
- Scanned-PDF OCR with a representative scan.
- Table extraction accuracy.
- Hindi/Marathi/Kannada OCR and question answering.
- Frontend lint/build for the current branch.
- Docker image build and full compose round trip.
- Ollama model loading, inference latency, and memory use.
- Dense embedding persistence and hybrid retrieval quality.
- End-to-end Document AI user workflow.

## Next phases

1. **Local LLM foundation — code added, runtime validation pending:** Ollama client, timeout handling, opt-in switch, Llama 3.2 selection, and safe unverified-draft response. Existing deterministic QA remains authoritative.
2. **Universal document ingestion:** normalize varied PDF layouts, scanned pages, tables, and multi-page sections while retaining page-level source coordinates and extraction confidence.
3. **BGE-M3 embeddings and hybrid retrieval:** combine lexical BM25 and vector retrieval; evaluate retrieval against multi-domain test packs.
4. **Zero-guessing verification:** sentence/claim-level evidence mapping, exact quote verification, conservative abstention, and calibrated reporting (never label heuristic scores as truth probabilities).
5. **Document intelligence:** improve cross-document contradictions, amendment chains, effective dates, and current-version reasoning with multi-domain fixtures.
6. **Document AI frontend:** independent upload/indexing, evidence viewer, Q&A, contradiction/amendment views, PDF passage highlighting, and review workflow.
7. **Regression, security and end-to-end validation:** preserve existing platform workflows and test banking, insurance, contracts, policies, scanned PDFs, tables, and multilingual cases.

Do not call the system "complete" or "production-ready" until the outstanding items above have been tested.
