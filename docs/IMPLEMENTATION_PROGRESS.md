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
| BM25 lexical retrieval | Done in code | No dense vectors yet |
| Cross-document Q&A | Partial | Extractive source passages, not LLM-generated answers |
| Page citations and quote verification | Done in code | Quotes are checked against stored page text |
| Abstention | Partial | Lexical key-term coverage heuristic; requires evaluation |
| Claim status and faithfulness | Partial | Verified-claim ratio; not a calibrated truth probability |
| Contradiction detection | Partial | Rule-based numeric facts (percent, INR, area, duration) |
| Amendment tracking | Partial | Basic explicit-cue/base-reference/effective-date rules |
| Human review | Done in code | Revenue Officer only; source evidence remains unchanged |
| Document AI frontend | Not started | Must use the documented API contract |
| Local Ollama LLM | Partial | Optional local Llama 3.2 draft integration added; output is marked unverified and cannot replace evidence-backed answers |
| BGE-M3 embeddings / vector retrieval | Not started | Requires storage design, indexing and evaluation |

## Access control

| Item | Status | Notes |
|---|---|---|
| Existing app ownership isolation | Done in code | Prior code includes an operator-isolation integration test |
| Document AI document/job/answer access checks | Done in code | Re-run tests in the current environment |
| Revenue Officer claim review authorization | Done in code | Verify audit event and role rejection paths |

## Infrastructure and documentation

| Item | Status | Notes |
|---|---|---|
| Docker Compose and frontend/backend configuration | Present in repository | Rebuild/retest before release |
| Runtime/dev Python requirements split | Present in repository | Development dependencies live in requirements-dev.txt |
| API contract | Present | Keep synchronized with actual implementation |
| Session handoff | Corrected | Historical patch instructions removed |
| Project state | Corrected | Domain-independent scope documented |
| README cleanup | Not verified | Do not mark complete without reviewing requested sections |
| Secret rotation | Outstanding | Rotate any previously committed credentials still active; never copy secrets into tracked files |

## Test evidence and limitations

Current user-reported focused test run on 2026-11-23: `15 passed` for `tests/test_docai_ollama.py` and `tests/test_document_ai.py`. This run predates the Universal Ingestion Engine changes below.

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
3. **BGE-M3 embeddings and hybrid retrieval:** combine lexical BM25 and vector retrieval; evaluate against multi-domain test packs.
4. **Zero-guessing verification:** sentence/claim-level evidence mapping, exact quote verification, conservative abstention, and calibrated reporting.
5. **Document intelligence:** improve cross-document contradictions, amendment chains, effective dates, and current-version reasoning with multi-domain fixtures.
6. **Document AI frontend:** independent upload/indexing, evidence viewer, Q&A, contradiction/amendment views, PDF passage highlighting, and review workflow.
7. **Regression, security and end-to-end validation:** preserve existing platform workflows and test banking, insurance, contracts, policies, scanned PDFs, tables, and multilingual cases.

Do not call the system "complete" or "production-ready" until outstanding items have been tested.
