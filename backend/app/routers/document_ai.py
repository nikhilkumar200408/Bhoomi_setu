"""Document AI routes (additive module; see docs/API_CONTRACT.md). Every route is ownership-scoped."""
from typing import List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .. import models
from ..config import settings
from ..database import (audit_collection, docai_answers_collection, docai_jobs_collection, docai_pages_collection,
                        docai_vectors_collection, documents_collection)
from ..deps import accessible_document_ids, document_scope, get_current_user, is_privileged
from ..services.audit.service import log_audit
from ..services.docai import facts as F
from ..services.docai import qa
from ..services.docai.calculations import calculate_financial_value
from ..services.docai.errors import DocAIError
from ..services.docai.text import extract_pages
from ..services.docai.structure import build_document_structure
from ..services.docai.ollama import OllamaError, generate_evidence_draft, translate_query_to_english
from ..services.docai.embeddings import EmbeddingError, embed_texts, cosine_similarity
from ..services.docai.web_source import WebImportError, fetch_public_page

router = APIRouter(prefix="/api/document-ai", tags=["document-ai"])
MAX_QUESTION_CHARS = 2000


def _iso(dt=None) -> str:
    return (dt or models.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_found(what: str, **details) -> DocAIError:
    return DocAIError(404, "RESOURCE_NOT_FOUND", f"The requested {what} was not found.", details or None)


async def _own_documents(ids: List[str], user: dict) -> List[dict]:
    docs = []
    for i in dict.fromkeys(ids):
        d = await documents_collection.find_one({"_id": i, **document_scope(user)})
        if not d:
            raise _not_found("document", document_id=i)  # same answer for missing and not-yours
        docs.append(d)
    return docs


async def _indexed_pages(docs: List[dict]) -> List[dict]:
    not_indexed = [d["_id"] for d in docs if d.get("docai_status") != "INDEXED"]
    if not_indexed:
        raise DocAIError(409, "RESOURCE_CONFLICT", "Some selected documents are not indexed yet.",
                         {"document_ids": not_indexed})
    cursor = docai_pages_collection.find({"document_id": {"$in": [d["_id"] for d in docs]}}).sort(
        [("document_id", 1), ("page", 1)])
    return [{**{k: p[k] for k in ("document_id", "filename", "page", "text", "source_type")},
             "source_url": p.get("source_url")} async for p in cursor]


# ----------------------------------------------------------------------------- indexing
class IndexRequest(BaseModel):
    force_reindex: bool = False
    language_hint: str = "auto"


def _job_out(j: dict) -> dict:
    return {"job_id": j["_id"], "document_id": j["document_id"], "status": j["status"],
            "pages_total": j.get("pages_total"), "pages_processed": j.get("pages_processed", 0),
            "chunks_created": j.get("chunks_created", 0), "vectors_created": j.get("vectors_created", 0),
            "retrieval_mode": j.get("retrieval_mode", "BM25"), "embedding_warning": j.get("embedding_warning"),
            "error": j.get("error"),
            "created_at": _iso(j["created_at"]), "completed_at": _iso(j["completed_at"]) if j.get("completed_at") else None,
            "structure": j.get("structure")}


async def _run_index(job_id: str, document: dict) -> None:
    await docai_jobs_collection.update_one({"_id": job_id}, {"$set": {"status": "PROCESSING"}})
    await documents_collection.update_one({"_id": document["_id"]}, {"$set": {"docai_status": "PROCESSING"}})
    try:
        pages = await run_in_threadpool(extract_pages, document["stored_path"])
        if not any(p["text"] for p in pages):
            raise DocAIError(422, "UNPROCESSABLE_DOCUMENT", "No readable text could be extracted from this document.")
        structure = await run_in_threadpool(build_document_structure, pages)
        await docai_pages_collection.delete_many({"document_id": document["_id"]})
        await docai_vectors_collection.delete_many({"document_id": document["_id"]})
        enriched_pages = [{**p, "document_id": document["_id"], "filename": document["filename"],
                           "source_url": document.get("source_url")} for p in pages]
        chunks = [chunk for page in enriched_pages for chunk in qa.build_chunks([page])]
        vectors_created, embedding_warning = 0, None
        if settings.OLLAMA_EMBEDDINGS_ENABLED and chunks:
            try:
                for offset in range(0, len(chunks), 32):
                    batch = chunks[offset:offset + 32]
                    texts = [chunk["page"]["text"][chunk["start"]:chunk["end"]] for chunk in batch]
                    vectors = await run_in_threadpool(embed_texts, texts)
                    records = []
                    for chunk, vector in zip(batch, vectors):
                        page = chunk["page"]
                        key = f'{document["_id"]}:{page["page"]}:{chunk["start"]}:{chunk["end"]}'
                        records.append({"_id": key, "document_id": document["_id"], "filename": document["filename"],
                                        "page": page["page"], "start": chunk["start"], "end": chunk["end"],
                                        "vector": vector, "model": settings.OLLAMA_EMBEDDING_MODEL})
                    if records:
                        await docai_vectors_collection.insert_many(records)
                        vectors_created += len(records)
            except EmbeddingError:
                await docai_vectors_collection.delete_many({"document_id": document["_id"]})
                vectors_created, embedding_warning = 0, "Local embeddings unavailable; lexical indexing completed."
        for p in enriched_pages:
            await docai_pages_collection.insert_one({"_id": models.gen_uuid(), **p})
        await docai_jobs_collection.update_one({"_id": job_id}, {"$set": {
            "status": "COMPLETED", "pages_total": len(pages), "pages_processed": len(pages),
            "chunks_created": len(chunks), "vectors_created": vectors_created,
            "retrieval_mode": "HYBRID_BM25_VECTOR" if vectors_created else "BM25",
            "embedding_warning": embedding_warning, "structure": structure, "completed_at": models.utcnow()}})
        await documents_collection.update_one({"_id": document["_id"]}, {"$set": {"docai_status": "INDEXED"}})
    except DocAIError as e:
        err = {"code": e.code, "message": e.message}
    except Exception:  # noqa: BLE001 - never leak raw exception text to clients
        err = {"code": "INTERNAL_ERROR", "message": "Indexing failed."}
    else:
        return
    await docai_jobs_collection.update_one({"_id": job_id}, {"$set": {"status": "FAILED", "error": err, "completed_at": models.utcnow()}})
    await documents_collection.update_one({"_id": document["_id"]}, {"$set": {"docai_status": "FAILED"}})


@router.post("/documents/{document_id}/index", status_code=202)
async def index_document(document_id: str, background: BackgroundTasks, payload: Optional[IndexRequest] = None,
                         user: dict = Depends(get_current_user)):
    payload = payload or IndexRequest()
    (document,) = await _own_documents([document_id], user)
    if not payload.force_reindex:
        existing = await docai_jobs_collection.find_one(
            {"document_id": document_id, "status": {"$in": ["QUEUED", "PROCESSING", "COMPLETED"]}}, sort=[("created_at", -1)])
        if existing:
            return {"document_id": document_id, "indexing_job_id": existing["_id"], "status": existing["status"],
                    "message": "Document is already indexed or being indexed."}
    job = {"_id": "job_" + models.gen_uuid()[:12], "document_id": document_id, "status": "QUEUED",
           "created_by": user["_id"], "created_at": models.utcnow(), "error": None}
    await docai_jobs_collection.insert_one(job)
    await documents_collection.update_one({"_id": document_id}, {"$set": {"docai_status": "PROCESSING"}})
    await log_audit(action="DOCAI_INDEX", document_id=document_id, user_id=user["_id"])
    background.add_task(_run_index, job["_id"], document)
    return {"document_id": document_id, "indexing_job_id": job["_id"], "status": "QUEUED",
            "message": "Document accepted for indexing."}


@router.get("/indexing-jobs/{job_id}")
async def indexing_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await docai_jobs_collection.find_one({"_id": job_id})
    if not job:
        raise _not_found("indexing job")
    await _own_documents([job["document_id"]], user)
    return _job_out(job)


# ----------------------------------------------------------------------------- domain-independent upload
@router.post("/documents/upload")
async def upload_document_ai_files(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    """Upload source files directly to the Document AI workspace without running the legacy land-record pipeline."""
    from .documents import _save_one

    if not files:
        raise DocAIError(400, "INVALID_REQUEST", "Select at least one file to upload.")
    uploaded = []
    errors = []
    for file in files:
        try:
            document = await _save_one(file, user)
            uploaded.append({
                "id": document["_id"],
                "filename": document["filename"],
                "file_size_bytes": document["file_size_bytes"],
                "status": document["status"],
                "docai_status": document.get("docai_status"),
                "uploaded_at": _iso(document["uploaded_at"]),
            })
        except Exception as exc:
            errors.append({"filename": file.filename or "unnamed file", "message": str(getattr(exc, "detail", "Upload failed."))})
    if not uploaded:
        raise DocAIError(400, "UPLOAD_FAILED", "No files could be uploaded.", {"files": errors})
    return {"items": uploaded, "errors": errors}


class WebpageImportRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)


@router.post("/sources/webpage/import")
async def import_public_webpage(payload: WebpageImportRequest, user: dict = Depends(get_current_user)):
    """Fetch one allowlisted public webpage and register it as a traceable text source."""
    if not settings.WEB_IMPORT_ALLOWED_DOMAINS.strip():
        raise DocAIError(403, "WEB_IMPORT_DISABLED", "Webpage import is disabled until an administrator configures WEB_IMPORT_ALLOWED_DOMAINS.")
    try:
        source = await run_in_threadpool(fetch_public_page, payload.url, settings.WEB_IMPORT_ALLOWED_DOMAINS)
    except WebImportError as exc:
        raise DocAIError(400, "WEB_IMPORT_REJECTED", str(exc)) from exc

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    host = re.sub(r"[^a-zA-Z0-9.-]", "-", payload.url.split("/")[2])[:100]
    filename = f"web-{host}-{uuid.uuid4().hex[:8]}.txt"
    stored_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4().hex}_{filename}")
    with open(stored_path, "w", encoding="utf-8") as output:
        output.write(f"Source title: {source['title']}\nSource URL: {source['source_url']}\nFetched at: {source['fetched_at']}\n\n{source['text']}")
    document = {
        "_id": models.gen_uuid(), "filename": filename, "stored_path": stored_path,
        "file_type": "text/plain", "file_size_bytes": os.path.getsize(stored_path),
        "status": models.DocumentStatus.UPLOADED.value, "uploaded_by": user["_id"],
        "uploaded_at": models.utcnow(), "processed_at": None, "error_message": None,
        "docai_status": None, "source_url": source["source_url"],
        "source_title": source["title"], "source_fetched_at": source["fetched_at"],
        "docai_source_type": "PUBLIC_WEBPAGE",
    }
    await documents_collection.insert_one(document)
    await log_audit(action="DOCAI_WEB_IMPORT", document_id=document["_id"], user_id=user["_id"],
                    metadata={"source_url": source["source_url"], "source_title": source["title"]})
    return {"id": document["_id"], "filename": filename, "docai_status": None,
            "source_url": source["source_url"], "source_title": source["title"],
            "source_fetched_at": source["fetched_at"], "message": "Webpage imported. Index it to search its extracted text."}


# ----------------------------------------------------------------------------- QA
class CalculationRequest(BaseModel):
    calculation_type: Literal["simple_interest", "compound_interest", "emi"]
    principal: float = Field(gt=0, le=1_000_000_000_000)
    annual_rate_percent: float = Field(ge=0, le=100)
    duration_value: float = Field(gt=0, le=1200)
    duration_unit: Literal["months", "years"] = "years"
    compounding_frequency: int = Field(default=12, ge=1, le=365)


@router.post("/calculate")
async def calculate_document_values(payload: CalculationRequest, user: dict = Depends(get_current_user)):
    try:
        result = calculate_financial_value(
            payload.calculation_type, payload.principal, payload.annual_rate_percent,
            payload.duration_value, payload.duration_unit, payload.compounding_frequency,
        )
    except ValueError as exc:
        raise DocAIError(400, "INVALID_CALCULATION", str(exc)) from exc
    await log_audit(
        action="DOCAI_CALCULATE", user_id=user["_id"],
        metadata={"calculation_type": payload.calculation_type, "input_source": "USER_PROVIDED"},
    )
    return result


class AskRequest(BaseModel):
    question: str
    document_ids: List[str] = Field(min_length=1)
    language: Literal["en", "hi"] = "en"
    include_superseded_documents: bool = True
    max_evidence_per_claim: int = 5


def _public_answer(a: dict) -> dict:
    return {k: v for k, v in a.items() if k not in ("_id", "user_id", "document_ids", "include_superseded")}


@router.post("/qa/ask")
async def ask(payload: AskRequest, user: dict = Depends(get_current_user)):
    if not payload.question.strip() or len(payload.question) > MAX_QUESTION_CHARS:
        raise DocAIError(400, "INVALID_REQUEST", "question must be non-empty text of reasonable length.")
    docs = await _own_documents(payload.document_ids, user)
    pages = await _indexed_pages(docs)
    vector_scores = {}
    if settings.OLLAMA_EMBEDDINGS_ENABLED:
        try:
            query_vector = (await run_in_threadpool(embed_texts, [payload.question.strip()]))[0]
            async for item in docai_vectors_collection.find({"document_id": {"$in": [d["_id"] for d in docs]}}):
                key = (item["document_id"], item["page"], item["start"], item["end"])
                vector_scores[key] = cosine_similarity(query_vector, item.get("vector", []))
        except EmbeddingError:
            vector_scores = {}  # Ollama downtime safely falls back to BM25.
    retrieval_question = payload.question.strip()
    language_notice = None
    if payload.language == "hi":
        if settings.OLLAMA_ENABLED:
            try:
                retrieval_question = await run_in_threadpool(translate_query_to_english, payload.question.strip())
            except OllamaError:
                language_notice = "स्थानीय Hindi query translation उपलब्ध नहीं है; मूल प्रश्न से खोज की गई। बेहतर Hindi retrieval के लिए Ollama और llama3.2 चालू करें।"
        else:
            language_notice = "Hindi उत्तर/खोज के लिए local Ollama चालू करें। अभी मूल Hindi प्रश्न से खोज की गई है।"

    result = qa.answer_question(retrieval_question, pages, [d["_id"] for d in docs],
                                payload.include_superseded_documents,
                                max(1, min(payload.max_evidence_per_claim, 10)),
                                vector_scores=vector_scores)
    result["question"] = payload.question.strip()
    result["retrieval_query_translated"] = retrieval_question != payload.question.strip()
    result["language_notice"] = language_notice
    result["response_language"] = payload.language

    # Ollama is optional drafting assistance only. It never changes source-backed claims,
    # citations, contradictions, abstention, or the backend-computed faithfulness score.
    if not settings.OLLAMA_ENABLED:
        result["llm_assistance"] = {"status": "DISABLED", "draft": None, "model": None}
    elif not result.get("evidence"):
        result["llm_assistance"] = {"status": "SKIPPED_NO_EVIDENCE", "draft": None, "model": settings.OLLAMA_CHAT_MODEL,
                                    "notice": "No source passages were retrieved, so the model was not asked to guess."}
    else:
        try:
            result["llm_assistance"] = await run_in_threadpool(
                generate_evidence_draft, payload.question.strip(), result["claims"], result["evidence"], payload.language)
        except OllamaError:
            # Local model downtime must never break evidence-backed Q&A.
            result["llm_assistance"] = {
                "status": "UNAVAILABLE", "draft": None, "model": settings.OLLAMA_CHAT_MODEL,
                "notice": "Local drafting is unavailable; the source-backed answer is unchanged.",
            }

    stored = {**result, "_id": result["answer_id"], "user_id": user["_id"],
              "document_ids": [d["_id"] for d in docs], "include_superseded": payload.include_superseded_documents}
    await docai_answers_collection.insert_one(stored)
    await log_audit(action="DOCAI_ASK", user_id=user["_id"], metadata={"answer_id": result["answer_id"], "abstained": result["abstained"]})
    return _public_answer(result)


async def _get_answer(answer_id: str, user: dict) -> dict:
    a = await docai_answers_collection.find_one({"_id": answer_id})
    if not a or not (is_privileged(user) or a["user_id"] == user["_id"]):
        raise _not_found("answer", answer_id=answer_id)
    return a


@router.get("/answers/{answer_id}")
async def get_answer(answer_id: str, user: dict = Depends(get_current_user)):
    return _public_answer(await _get_answer(answer_id, user))


class VerifyRequest(BaseModel):
    verify_quotes: bool = True
    recheck_claims: bool = True


@router.post("/answers/{answer_id}/verify")
async def verify_answer(answer_id: str, payload: Optional[VerifyRequest] = None, user: dict = Depends(get_current_user)):
    payload = payload or VerifyRequest()
    a = await _get_answer(answer_id, user)
    pages = {}
    async for p in docai_pages_collection.find({"document_id": {"$in": a["document_ids"]}}):
        pages[(p["document_id"], p["page"])] = p
    result = qa.reverify(a, pages, payload.verify_quotes, payload.recheck_claims)
    await docai_answers_collection.replace_one({"_id": answer_id}, a)
    return result


class ReviewRequest(BaseModel):
    decision: str
    reason: str = ""


@router.post("/claims/{claim_id}/review")
async def review_claim(claim_id: str, payload: ReviewRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "REVENUE_OFFICER":
        raise DocAIError(403, "FORBIDDEN", "Only a Revenue Officer may review claims.")
    if payload.decision not in ("ACCEPT", "REJECT", "MARK_UNRESOLVED"):
        raise DocAIError(400, "INVALID_REQUEST", "decision must be ACCEPT, REJECT or MARK_UNRESOLVED.")
    if payload.decision in ("REJECT", "MARK_UNRESOLVED") and not payload.reason.strip():
        raise DocAIError(400, "INVALID_REQUEST", "A reason is required for this decision.")
    a = await docai_answers_collection.find_one({"claims.claim_id": claim_id})
    if not a:
        raise _not_found("claim", claim_id=claim_id)
    await _get_answer(a["_id"], user)
    claim = next(c for c in a["claims"] if c["claim_id"] == claim_id)
    review = {"decision": payload.decision, "reason": payload.reason.strip(), "reviewed_by": user["_id"], "reviewed_at": _iso()}
    claim["review"] = review  # original status and evidence are deliberately left untouched
    claim["requires_human_review"] = payload.decision == "MARK_UNRESOLVED"
    await docai_answers_collection.replace_one({"_id": a["_id"]}, a)
    await log_audit(action="DOCAI_CLAIM_REVIEW", user_id=user["_id"], new_value=payload.decision,
                    metadata={"claim_id": claim_id, "answer_id": a["_id"], "reason": review["reason"]})
    return {"claim_id": claim_id, "review_status": payload.decision, "reviewed_by": user["_id"], "reviewed_at": review["reviewed_at"]}


class CorrectClaimRequest(BaseModel):
    corrected_text: str = Field(min_length=3, max_length=4000)
    reason: str = Field(min_length=5, max_length=1000)


@router.post("/claims/{claim_id}/correct")
async def correct_claim(claim_id: str, payload: CorrectClaimRequest, user: dict = Depends(get_current_user)):
    """Store a reviewer correction separately; never mutate the source quote or original claim."""
    if user["role"] != "REVENUE_OFFICER":
        raise DocAIError(403, "FORBIDDEN", "Only a Revenue Officer may correct claims.")
    a = await docai_answers_collection.find_one({"claims.claim_id": claim_id})
    if not a:
        raise _not_found("claim", claim_id=claim_id)
    await _get_answer(a["_id"], user)
    claim = next(c for c in a["claims"] if c["claim_id"] == claim_id)
    old_text = claim.get("correction", {}).get("corrected_text") or claim["text"]
    correction = {
        "corrected_text": payload.corrected_text.strip(),
        "reason": payload.reason.strip(),
        "original_text": claim["text"],
        "corrected_by": user["_id"],
        "corrected_at": _iso(),
    }
    claim["correction"] = correction
    a["faithfulness_score"] = qa.faithfulness(a.get("claims", []), a.get("evidence", []))
    await docai_answers_collection.replace_one({"_id": a["_id"]}, a)
    await log_audit(
        action="DOCAI_CLAIM_CORRECTION", user_id=user["_id"],
        old_value=old_text, new_value=correction["corrected_text"],
        metadata={"claim_id": claim_id, "answer_id": a["_id"], "reason": correction["reason"]},
    )
    return {"claim_id": claim_id, "correction": correction, "source_evidence_unchanged": True}


@router.get("/answers/{answer_id}/audit")
async def answer_audit(answer_id: str, user: dict = Depends(get_current_user)):
    """Return audit history for an answer after enforcing the same ownership check as answer reads."""
    await _get_answer(answer_id, user)
    cursor = audit_collection.find({"log_metadata.answer_id": answer_id}).sort("timestamp", -1).limit(100)
    events = []
    async for item in cursor:
        events.append({
            "action": item.get("action"), "old_value": item.get("old_value"),
            "new_value": item.get("new_value"), "metadata": item.get("log_metadata", {}),
            "timestamp": _iso(item.get("timestamp")), "user_id": item.get("user_id"),
        })
    return {"answer_id": answer_id, "items": events}


# ----------------------------------------------------------------------------- contradictions / amendments
def _page_params(limit: str, cursor: Optional[str]):
    try:
        lim, off = int(limit), int(cursor or 0)
        if not 1 <= lim <= 200 or off < 0:
            raise ValueError
    except ValueError:
        raise DocAIError(400, "INVALID_REQUEST", "limit must be 1-200 and cursor must be a value returned by this API.")
    return lim, off


def _paginate(items: list, lim: int, off: int) -> dict:
    page = items[off: off + lim]
    return {"items": page, "next_cursor": str(off + lim) if off + lim < len(items) else None}


async def _analysis(doc_ids: Optional[List[str]], user: dict) -> dict:
    if doc_ids:
        docs = await _own_documents(doc_ids, user)
    else:
        docs = [d async for d in documents_collection.find({**document_scope(user), "docai_status": "INDEXED"})]
    pages = await _indexed_pages(docs) if docs else []
    return F.analyse(pages)


def _clean(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "_doc_ids"}


@router.get("/contradictions")
async def contradictions(document_ids: str = Query(...), status: Optional[str] = None, limit: str = "50",
                         cursor: Optional[str] = None, user: dict = Depends(get_current_user)):
    lim, off = _page_params(limit, cursor)
    ids = [i for i in document_ids.split(",") if i.strip()]
    if not ids:
        raise DocAIError(400, "INVALID_REQUEST", "document_ids is required.")
    if status and status not in ("OPEN", "RESOLVED_BY_AMENDMENT", "UNRESOLVED", "NEEDS_HUMAN_REVIEW"):
        raise DocAIError(400, "INVALID_REQUEST", "Unknown status filter.")
    items = [_clean(c) for c in (await _analysis(ids, user))["contradictions"] if not status or c["status"] == status]
    return _paginate(items, lim, off)


@router.get("/amendments")
async def amendments(document_ids: Optional[str] = None, topic: Optional[str] = None, status: Optional[str] = None,
                     limit: str = "50", cursor: Optional[str] = None, user: dict = Depends(get_current_user)):
    lim, off = _page_params(limit, cursor)
    if status and status not in ("ACTIVE", "SUPERSEDED", "PENDING_EFFECTIVE_DATE", "REVIEW_REQUIRED"):
        raise DocAIError(400, "INVALID_REQUEST", "Unknown status filter.")
    ids = [i for i in (document_ids or "").split(",") if i.strip()]
    items = [_clean(a) for a in (await _analysis(ids, user))["amendments"]
             if (not topic or topic.lower() in a["topic"].lower()) and (not status or a["status"] == status)]
    return _paginate(items, lim, off)


@router.get("/amendments/{amendment_id}")
async def amendment_detail(amendment_id: str, user: dict = Depends(get_current_user)):
    result = await _analysis(None, user)
    amd = next((a for a in result["amendments"] if a["amendment_id"] == amendment_id), None)
    if not amd:
        raise _not_found("amendment", amendment_id=amendment_id)
    evid = {e["evidence_id"]: e for c in result["contradictions"] for e in c["evidence"]}
    docs = {d["_id"]: d async for d in documents_collection.find({"_id": {"$in": amd["_doc_ids"]}})}
    meta = lambda i: {"document_id": i, "filename": docs[i]["filename"]}  # noqa: E731
    return {**_clean(amd), "base_document": meta(amd["base_document_id"]), "amending_document": meta(amd["amending_document_id"]),
            "evidence": [evid[i] for i in amd["evidence_ids"] if i in evid],
            "prior_amendment_ids": [a["amendment_id"] for a in result["amendments"] if a["amending_document_id"] == amd["base_document_id"]],
            "successor_amendment_ids": [a["amendment_id"] for a in result["amendments"] if a["base_document_id"] == amd["amending_document_id"]],
            "effective_date_interpretation": ("Effective date is stated explicitly by the amending document; the change is not assumed to be retroactive."
                                              if amd["effective_from"] else "No effective date was found; human review required.")}
