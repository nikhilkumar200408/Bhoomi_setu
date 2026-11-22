# Document AI API Contract

**Project:** Bhoomi_setu — Zero-Guessing & Contradiction-Checking Document AI  
**Contract version:** 1.0.0  
**Target branch:** `dev`  
**Status:** Proposed interface for the new cross-document intelligence module. These endpoints are **not implemented yet** unless explicitly marked “existing” below.

This contract is the shared agreement between frontend and backend contributors. Implement the request and response shapes as written. If a change is necessary, discuss it first and update this file in the same pull request.

---

## 1. API conventions and common types

### Base URL and authentication

- Local backend base URL: `http://localhost:8000`
- New Document AI routes use the `/api/document-ai` prefix.
- Send the existing JWT on protected routes:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

- Upload routes use `multipart/form-data`; do not manually set the multipart Content-Type header in browser clients.
- JSON field names use `snake_case`.
- Timestamps use ISO 8601 UTC strings, for example `2026-11-23T10:30:00Z`.
- Page numbers are **1-based**, matching the page number shown in a PDF viewer.
- IDs are opaque strings. Clients must not assume they are UUIDs or derive meaning from them.
- Unknown response fields should be ignored by clients for forward compatibility.

### Common enums

| Type | Allowed values |
|---|---|
| `DocumentStatus` | `UPLOADED`, `PROCESSING`, `INDEXED`, `FAILED` |
| `IndexingStatus` | `QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `ClaimStatus` | `SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE`, `UNVERIFIED` |
| `EvidenceRelation` | `SUPPORTS`, `CONTRADICTS`, `CONTEXT_ONLY` |
| `ContradictionStatus` | `OPEN`, `RESOLVED_BY_AMENDMENT`, `UNRESOLVED`, `NEEDS_HUMAN_REVIEW` |
| `AmendmentStatus` | `ACTIVE`, `SUPERSEDED`, `PENDING_EFFECTIVE_DATE`, `REVIEW_REQUIRED` |
| `ReviewDecision` | `ACCEPT`, `REJECT`, `MARK_UNRESOLVED` |

### Common error response

All API errors should use this shape (FastAPI validation errors may additionally include the standard `detail` array):

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "The requested document was not found.",
    "details": {
      "document_id": "doc_123"
    },
    "request_id": "req_abc123"
  }
}
```

`details` may be `null` or omitted when there is no safe, useful detail. Never return stack traces, local file paths, secrets, model prompts, or raw exception messages to clients.

---

## 2. Document upload and processing

### 2.1 Existing upload endpoints — keep backward compatible

These routes already exist in `backend/app/routers/documents.py`. Do not rename or repurpose them as part of the Document AI work.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/documents/upload` | Upload one document |
| POST | `/api/documents/upload-batch` | Upload multiple documents |
| GET | `/api/documents` | List uploaded documents |
| GET | `/api/documents/{document_id}` | Get document metadata |
| GET | `/api/documents/{document_id}/file` | Retrieve original file |
| POST | `/api/documents/{document_id}/process` | Existing land-record extraction pipeline |

The existing upload request is multipart form data with `file` (single) or `files` (batch). The existing response is the current `DocumentOut` schema; do not silently change its fields.

### 2.2 New indexing endpoint

**POST** `/api/document-ai/documents/{document_id}/index`

Indexes an already-uploaded document for cross-document search and question answering. This is separate from the existing land-record `/process` pipeline.

Request:

```json
{
  "force_reindex": false,
  "language_hint": "auto"
}
```

Response — `202 Accepted`:

```json
{
  "document_id": "doc_123",
  "indexing_job_id": "job_456",
  "status": "QUEUED",
  "message": "Document accepted for indexing."
}
```

The backend indexing pipeline should preserve document ID, filename, page number, extracted text, extraction method, and source offsets for every indexed chunk. Repeated requests should be idempotent unless `force_reindex` is true.

### 2.3 Indexing job status

**GET** `/api/document-ai/indexing-jobs/{job_id}`

Response:

```json
{
  "job_id": "job_456",
  "document_id": "doc_123",
  "status": "COMPLETED",
  "pages_total": 12,
  "pages_processed": 12,
  "chunks_created": 48,
  "error": null,
  "created_at": "2026-11-23T10:30:00Z",
  "completed_at": "2026-11-23T10:31:12Z"
}
```

Use `error: null` unless the job failed. A failed job must have a safe, user-readable error code/message.

---

## 3. Multi-document question answering

### Ask a question

**POST** `/api/document-ai/qa/ask`

Request:

```json
{
  "question": "What is the currently applicable interest rate?",
  "document_ids": ["doc_123", "doc_456", "doc_789"],
  "language": "en",
  "include_superseded_documents": true,
  "max_evidence_per_claim": 5
}
```

Rules:
- `question` is required and must contain non-whitespace text.
- `document_ids` is required and must contain at least one accessible document.
- `language` is a BCP-47 language tag where possible (for example `en`, `hi`, `mr`); default is `en`.
- `include_superseded_documents` defaults to `true` so the system can explain amendment history. Superseded text must not be presented as currently effective without qualification.
- `max_evidence_per_claim` defaults to 5 and is bounded by the backend.

Response — `200 OK`:

```json
{
  "answer_id": "ans_001",
  "question": "What is the currently applicable interest rate?",
  "answer": "The latest indexed amendment states 10%, effective 1 January 2026.",
  "abstained": false,
  "faithfulness_score": 0.92,
  "faithfulness_method": "verified_claim_ratio",
  "claims": [
    {
      "claim_id": "claim_001",
      "text": "The applicable interest rate is 10%.",
      "status": "SUPPORTED",
      "confidence": 0.96,
      "evidence_ids": ["ev_001"],
      "explanation": "The amendment explicitly states the revised rate."
    }
  ],
  "missing_evidence": [],
  "conflicts": [],
  "created_at": "2026-11-23T10:35:00Z"
}
```

If the retrieved documents do not contain enough reliable evidence, return a clear abstention instead of guessing:

```json
{
  "answer_id": "ans_002",
  "question": "What is the applicable rate?",
  "answer": "I cannot determine the applicable rate from the selected documents.",
  "abstained": true,
  "faithfulness_score": 0.0,
  "faithfulness_method": "verified_claim_ratio",
  "claims": [],
  "missing_evidence": [
    {
      "description": "No clause specifying the rate was found.",
      "searched_document_ids": ["doc_123"]
    }
  ],
  "conflicts": [],
  "created_at": "2026-11-23T10:35:00Z"
}
```

**Zero-guessing rule:** do not fabricate facts, page numbers, quotes, dates, clause numbers, amendment relationships, or citations. If a claim cannot be grounded in retrieved source text, mark it `INSUFFICIENT_EVIDENCE` or abstain.

### Retrieve a saved answer

**GET** `/api/document-ai/answers/{answer_id}`

Returns the same answer resource, including claims, evidence, conflicts, and faithfulness metadata. Unknown or unauthorized IDs return the common error response.

---

## 4. Exact page-level citations and evidence

Every evidence item must point to the original uploaded document and a real page. Page numbers are 1-based.

Canonical evidence object:

```json
{
  "evidence_id": "ev_001",
  "document_id": "doc_456",
  "filename": "Policy_Amendment.pdf",
  "page_number": 3,
  "section": "Clause 4.2 — Revised Interest",
  "quote": "The rate of interest shall be ten percent per annum...",
  "start_char": 1240,
  "end_char": 1302,
  "relation": "SUPPORTS",
  "source_type": "PDF_TEXT",
  "verification": {
    "quote_found_in_source": true,
    "page_verified": true
  }
}
```

Rules:
- `quote` must be an exact contiguous excerpt from text extracted from that source page (whitespace normalization may be applied consistently, but wording must not be rewritten).
- `start_char` and `end_char` are optional offsets within the normalized page text; if supplied, they must identify the quoted span.
- `source_type` may be `PDF_TEXT`, `OCR_TEXT`, or `TABLE_CELL`.
- The backend, not the language model, is responsible for validating that the quote exists on the cited page.
- If exact page verification fails, do not emit the citation as verified. Return it as unavailable/invalid evidence internally and downgrade the claim or abstain.
- The frontend must render the filename, page number, section (when known), exact quote, and verification state. Clicking a citation should open the original document at the cited page when the viewer supports it.

The `claims[].evidence_ids` array references evidence objects returned with the answer. Evidence must never be silently detached from its document/page identity.

---

## 5. Contradiction detection

**GET** `/api/document-ai/contradictions`

Query parameters:
- `document_ids`: comma-separated document IDs; required for scoped analysis.
- `status`: optional `OPEN`, `RESOLVED_BY_AMENDMENT`, `UNRESOLVED`, or `NEEDS_HUMAN_REVIEW`.
- `limit`: optional integer, default 50, maximum 200.
- `cursor`: optional pagination cursor.

Response:

```json
{
  "items": [
    {
      "contradiction_id": "con_001",
      "topic": "Annual interest rate",
      "status": "RESOLVED_BY_AMENDMENT",
      "severity": "HIGH",
      "explanation": "The later amendment changes the rate from 8% to 10%.",
      "evidence": [
        {
          "evidence_id": "ev_old",
          "document_id": "doc_123",
          "filename": "Policy_Original.pdf",
          "page_number": 2,
          "section": "Clause 4",
          "quote": "Interest shall be eight percent per annum...",
          "relation": "CONTRADICTS",
          "source_type": "PDF_TEXT",
          "verification": {
            "quote_found_in_source": true,
            "page_verified": true
          }
        },
        {
          "evidence_id": "ev_new",
          "document_id": "doc_456",
          "filename": "Policy_Amendment.pdf",
          "page_number": 1,
          "section": "Amended Clause 4",
          "quote": "The revised rate shall be ten percent per annum...",
          "relation": "SUPPORTS",
          "source_type": "PDF_TEXT",
          "verification": {
            "quote_found_in_source": true,
            "page_verified": true
          }
        }
      ],
      "resolution": {
        "rule": "LATER_EFFECTIVE_AMENDMENT",
        "controlling_document_id": "doc_456",
        "effective_from": "2026-01-01",
        "requires_human_review": false
      },
      "detected_at": "2026-11-23T10:40:00Z"
    }
  ],
  "next_cursor": null
}
```

Contradictions must be evaluated in context: subject, jurisdiction, document scope, clause/topic, effective dates, and amendment relationships. Different values are not automatically contradictions if they apply to different entities, periods, or conditions. If precedence cannot be established safely, use `NEEDS_HUMAN_REVIEW`; do not choose a winner based only on upload time.

---

## 6. Amendment tracking

### List amendment relationships

**GET** `/api/document-ai/amendments`

Query parameters:
- `document_ids`: optional comma-separated IDs to scope the chain.
- `topic`: optional topic/clause filter.
- `status`: optional `AmendmentStatus`.
- `limit`: optional integer, default 50, maximum 200.
- `cursor`: optional pagination cursor.

Response:

```json
{
  "items": [
    {
      "amendment_id": "amd_002",
      "base_document_id": "doc_123",
      "amending_document_id": "doc_456",
      "topic": "Annual interest rate",
      "change_summary": "Rate changed from 8% to 10%.",
      "old_value": "8%",
      "new_value": "10%",
      "announced_on": "2025-12-15",
      "effective_from": "2026-01-01",
      "status": "ACTIVE",
      "evidence_ids": ["ev_old", "ev_new"],
      "relationship_confidence": 0.94,
      "requires_human_review": false
    }
  ],
  "next_cursor": null
}
```

### Get amendment detail

**GET** `/api/document-ai/amendments/{amendment_id}`

Returns the selected amendment plus its base/amending document metadata, linked evidence, prior/successor amendments where known, and effective-date interpretation.

Rules:
- Distinguish announcement/publication date from effective date.
- Do not assume an amendment applies retroactively unless the source explicitly says so.
- Preserve the chain; do not overwrite the original clause/value.
- If the source does not clearly identify the document being amended, set `REVIEW_REQUIRED` and `requires_human_review: true`.
- Amendment relationships must not form cycles.

---

## 7. Claim verification and faithfulness score

### Claim-level status

Each answer claim must have:
- `claim_id`
- `text`
- `status` from `ClaimStatus`
- `confidence` in the inclusive range 0.0–1.0
- `evidence_ids`
- `explanation`

A claim is `SUPPORTED` only when one or more valid source excerpts directly support it. Use `PARTIALLY_SUPPORTED` when only part of the claim is evidenced; `CONTRADICTED` when verified evidence conflicts with it; `INSUFFICIENT_EVIDENCE` when sources do not establish it; and `UNVERIFIED` before verification is complete.

### Re-verify an answer

**POST** `/api/document-ai/answers/{answer_id}/verify`

Request:

```json
{
  "verify_quotes": true,
  "recheck_claims": true
}
```

Response:

```json
{
  "answer_id": "ans_001",
  "verification_status": "COMPLETED",
  "faithfulness_score": 0.92,
  "faithfulness_method": "verified_claim_ratio",
  "claims_checked": 1,
  "claims_supported": 1,
  "claims_partially_supported": 0,
  "claims_contradicted": 0,
  "claims_insufficient_evidence": 0,
  "invalid_citation_count": 0,
  "verified_at": "2026-11-23T10:45:00Z"
}
```

### Faithfulness score definition

For the initial contract, use a transparent **verified-claim ratio**:

`faithfulness_score = supported_claim_count / total_answer_claim_count`

- Score is a decimal from 0.0 to 1.0; frontend may display it as a percentage.
- An answer with zero factual claims must not be assigned 1.0 by default; return `null` and explain that no claims were scored, or abstain.
- A partially supported, contradicted, insufficient, or unverified claim is not counted as supported.
- Do not increase the score by deleting unsupported claims after generation without retaining an audit record of the original candidate claims.
- Return the method name with every score. This score is an evidence-coverage metric, not a probability that the answer is true.

### Human review of a claim

**POST** `/api/document-ai/claims/{claim_id}/review`

Request:

```json
{
  "decision": "MARK_UNRESOLVED",
  "reason": "The cited scan is unclear; manual inspection is required."
}
```

Response:

```json
{
  "claim_id": "claim_001",
  "review_status": "MARK_UNRESOLVED",
  "reviewed_by": "user_123",
  "reviewed_at": "2026-11-23T10:50:00Z"
}
```

This is a human-review action and must require authentication and an authorized reviewer role. Store reviewer, decision, reason, and timestamp in the audit trail. A human decision must not rewrite or delete the original source evidence.

---

## 8. Error handling and status codes

| HTTP status | Meaning | Example error code |
|---|---|---|
| 400 | Invalid request or unsupported upload | `INVALID_REQUEST` |
| 401 | Missing/invalid authentication | `UNAUTHORIZED` |
| 403 | Authenticated user lacks permission | `FORBIDDEN` |
| 404 | Document, answer, job, claim, or amendment not found | `RESOURCE_NOT_FOUND` |
| 409 | Conflicting state or duplicate operation that cannot be reused | `RESOURCE_CONFLICT` |
| 413 | Upload exceeds configured size limit | `FILE_TOO_LARGE` |
| 415 | Unsupported media type | `UNSUPPORTED_FILE_TYPE` |
| 422 | Valid JSON/form shape but invalid semantic input or unprocessable document | `UNPROCESSABLE_DOCUMENT` |
| 429 | Rate limit exceeded | `RATE_LIMITED` |
| 500 | Unexpected server error | `INTERNAL_ERROR` |
| 503 | Required local model, database, or indexing service unavailable | `DEPENDENCY_UNAVAILABLE` |

Additional rules:
- Use `202 Accepted` for queued indexing jobs.
- Use `200 OK` for successful reads and completed synchronous operations.
- Use `201 Created` when a new persistent resource is created synchronously.
- Use `400` for malformed filters and invalid pagination; use `422` for semantically invalid content.
- A model timeout/dependency outage must not return a fabricated answer. Return a safe error or a persisted job state of `FAILED`.
- Do not expose secrets, local paths, internal prompts, raw model traces, or stack traces.

---

## 9. Frontend/backend implementation agreement

### Backend responsibilities

1. Implement and validate the request/response schemas.
2. Enforce authentication, document-level access checks, and reviewer permissions.
3. Extract text with page identity and preserve source provenance.
4. Validate every citation against the original page text before returning it.
5. Resolve amendment precedence using scope and effective dates, not upload order alone.
6. Calculate faithfulness deterministically using the documented formula.
7. Persist answers, claims, evidence, indexing jobs, contradictions, amendments, and review/audit events.
8. Return the common error shape and appropriate HTTP status codes.

### Frontend responsibilities

1. Use the paths and JSON shapes in this contract; do not invent local response fields.
2. Show indexing progress and failed states.
3. Display each claim with its verification status and linked evidence.
4. Open the original document at the cited page and show the exact excerpt.
5. Visually distinguish open contradictions, amendment-resolved conflicts, and items needing human review.
6. Display faithfulness as a percentage only after checking that the score is not `null`; show its method/meaning in supporting text.
7. Handle loading, empty, error, abstained, and partial-result states.

### Compatibility with the existing land-record application

The repository currently implements the land-record workflow under `/api/documents`, `/api/records`, and related routers. The new Document AI API is an additive module under `/api/document-ai`. Keep the existing upload, land-record processing, records, authentication, and audit routes working. Do not reinterpret the existing land-record `overall_confidence` as the new answer `faithfulness_score`; they measure different things.

---

## 10. Minimum integration test cases

Before merging the feature into `dev`, backend and frontend contributors must test:

1. Upload one PDF and a batch of PDFs; unsupported and oversized files return safe errors.
2. Index a document and poll its job until `COMPLETED` or `FAILED`.
3. Ask a question over multiple selected documents and receive claims with page-level evidence.
4. Verify that every returned quote actually occurs on the cited page.
5. Ask a question whose answer is absent; the system abstains and does not invent a citation.
6. Detect two conflicting values with their respective source pages.
7. Resolve a conflict only when scope and effective-date evidence establish an amendment; otherwise require human review.
8. Return an amendment chain without cycles and distinguish publication date from effective date.
9. Recalculate the faithfulness score using the documented formula, including partially supported and contradicted claims.
10. Reject unauthorized access to documents and human-review actions.
11. Keep existing land-record upload, process, verification, and dashboard flows working.

---

## Change policy

- Any endpoint, field, enum, or scoring change requires an update to this file.
- Backend and frontend changes that alter this contract must be coordinated in one reviewed pull request to `dev`.
- Do not merge unimplemented/fake API responses as if they were real AI results.
- This contract defines the target interface; it does not claim that these new endpoints already exist.
