"""Phase 1 TrustLens intelligence APIs. All reads are scoped to accessible documents."""
from typing import Optional
from fastapi import APIRouter, Depends, Query

from ..database import documents_collection, docai_pages_collection
from ..deps import get_current_user, document_scope
from ..services.docai.intelligence import extract_entities, search_pages
from ..services.docai.errors import DocAIError

router = APIRouter(prefix="/api/intelligence", tags=["trustlens-intelligence"])


async def _pages(user: dict, document_ids: Optional[str] = None):
    scope = document_scope(user)
    if document_ids:
        ids = list(dict.fromkeys(x.strip() for x in document_ids.split(",") if x.strip()))
        if not ids:
            return []
        docs = [d async for d in documents_collection.find({"_id": {"$in": ids}, **scope, "docai_status": "INDEXED"}, {"_id": 1})]
        if len(docs) != len(ids):
            raise DocAIError(404, "RESOURCE_NOT_FOUND", "One or more selected indexed documents were not found.")
        allowed = [d["_id"] for d in docs]
    else:
        allowed = [d["_id"] async for d in documents_collection.find({**scope, "docai_status": "INDEXED"}, {"_id": 1})]
    if not allowed:
        return []
    return [p async for p in docai_pages_collection.find({"document_id": {"$in": allowed}}).sort([("document_id", 1), ("page", 1)])]


@router.get("/overview")
async def intelligence_overview(document_ids: Optional[str] = None, user: dict = Depends(get_current_user)):
    pages = await _pages(user, document_ids)
    result = extract_entities(pages)
    return {
        "indexed_document_count": len(result["documents"]),
        "page_count": len(pages),
        "entity_count": sum(1 for n in result["nodes"] if n["type"] != "DOCUMENT"),
        "relationship_count": len(result["edges"]),
        "nodes": result["nodes"], "edges": result["edges"],
        "fields": result["fields"], "visual_review": result["visual_review"],
        "documents": result["documents"], "notice": result["notice"],
    }


@router.get("/graph")
async def relationship_graph(document_ids: Optional[str] = None, user: dict = Depends(get_current_user)):
    result = extract_entities(await _pages(user, document_ids))
    return {"nodes": result["nodes"], "edges": result["edges"], "documents": result["documents"], "notice": result["notice"]}


@router.get("/confidence")
async def confidence_review(document_ids: Optional[str] = None, status: Optional[str] = None,
                            user: dict = Depends(get_current_user)):
    fields = extract_entities(await _pages(user, document_ids))["fields"]
    if status:
        allowed = {"VERIFIED", "NEEDS_REVIEW", "UNCERTAIN"}
        if status not in allowed:
            raise DocAIError(400, "INVALID_REQUEST", "status must be VERIFIED, NEEDS_REVIEW or UNCERTAIN.")
        fields = [f for f in fields if f["status"] == status]
    return {"items": fields, "summary": {
        "total": len(fields),
        "verified": sum(f["status"] == "VERIFIED" for f in fields),
        "needs_review": sum(f["status"] == "NEEDS_REVIEW" for f in fields),
        "uncertain": sum(f["status"] == "UNCERTAIN" for f in fields),
    }, "notice": "Confidence estimates extraction reliability only. VERIFIED means the extracted value is present in the source with a high extraction signal; it does not establish legal correctness."}


@router.get("/visual-review")
async def visual_review(document_ids: Optional[str] = None, user: dict = Depends(get_current_user)):
    result = extract_entities(await _pages(user, document_ids))
    return {"items": result["visual_review"], "notice": "This is a review-candidate locator based on OCR confidence and extracted wording. It does not visually authenticate handwriting, signatures, stamps or seals."}


@router.get("/search")
async def natural_language_search(q: str = Query(..., min_length=2, max_length=500),
                                  document_ids: Optional[str] = None, limit: int = Query(20, ge=1, le=50),
                                  user: dict = Depends(get_current_user)):
    pages = await _pages(user, document_ids)
    items = search_pages(q, pages, limit)
    return {"query": q, "items": items, "total": len(items), "retrieval": "BM25 lexical ranking",
            "notice": "Search results are source passages, not legal conclusions. Open the cited document page to verify context."}
