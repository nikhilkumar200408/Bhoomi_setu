"""Phase 2 verification and compliance workflow.

All generated findings retain source document/page evidence. Rule outcomes and
checklist statuses are review aids, never legal conclusions.
"""
import difflib
import re
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import (
    documents_collection, docai_pages_collection,
    compliance_checklists_collection, compliance_rules_collection,
    compliance_reviews_collection, compliance_events_collection,
)
from ..deps import get_current_user, document_scope
from ..services.docai.errors import DocAIError

router = APIRouter(prefix="/api/compliance", tags=["verification-compliance"])
CHECKLIST_STATUSES = {"FOUND", "MISSING", "NEEDS_VERIFICATION"}
RULE_OPERATORS = {"contains", "not_contains", "regex", "date_present", "min_pages"}


def _now():
    return datetime.utcnow()


def _id():
    return str(uuid.uuid4())


def _clean(value: str) -> str:
    return " ".join((value or "").split())


class RequirementInput(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    keywords: list[str] = Field(min_length=1, max_length=12)


class ChecklistCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    document_ids: list[str] = Field(min_length=1, max_length=50)
    requirements: list[RequirementInput] = Field(min_length=1, max_length=40)


class VersionCompareRequest(BaseModel):
    old_document_id: str
    new_document_id: str


class RuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    operator: Literal["contains", "not_contains", "regex", "date_present", "min_pages"]
    expected_value: str = Field(default="", max_length=300)
    severity: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class RuleRunRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=50)


class EvidenceInput(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)
    filename: Optional[str] = None


class ReviewCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    source_type: Literal["CHECKLIST", "VERSION", "RULE", "MANUAL"]
    document_ids: list[str] = Field(min_length=1, max_length=50)
    evidence: list[EvidenceInput] = Field(min_length=1, max_length=30)
    source_id: Optional[str] = None


class ReviewUpdate(BaseModel):
    action: Literal["ACCEPT", "REJECT", "CORRECT", "MARK_FOR_REVIEW"]
    comment: str = Field(default="", max_length=2000)
    corrected_value: Optional[str] = Field(default=None, max_length=1000)


async def _load_indexed_documents(user: dict, ids: list[str]) -> list[dict]:
    ids = list(dict.fromkeys(x.strip() for x in ids if x and x.strip()))
    if not ids:
        raise HTTPException(400, "Select at least one indexed document.")
    docs = [d async for d in documents_collection.find(
        {"_id": {"$in": ids}, **document_scope(user), "docai_status": "INDEXED"}
    )]
    if len(docs) != len(ids):
        raise HTTPException(404, "One or more selected indexed documents were not found.")
    return docs


async def _load_pages(ids: list[str]) -> list[dict]:
    return [p async for p in docai_pages_collection.find(
        {"document_id": {"$in": ids}}
    ).sort([("document_id", 1), ("page", 1)])]


def _page_evidence(page: dict, quote: str) -> dict:
    return {
        "document_id": page["document_id"],
        "filename": page.get("filename", "Document"),
        "page": int(page.get("page", 1)),
        "quote": _clean(quote)[:2000],
        "source_type": page.get("source_type"),
    }


def _snippet(text: str, needle: str, radius: int = 180) -> str:
    pos = text.casefold().find(needle.casefold()) if needle else -1
    if pos < 0:
        return _clean(text[:radius * 2])
    return _clean(text[max(0, pos-radius):min(len(text), pos+len(needle)+radius)])


@router.get("/overview")
async def compliance_overview(user: dict = Depends(get_current_user)):
    docs = [d async for d in documents_collection.find(
        {**document_scope(user), "docai_status": "INDEXED"},
        {"_id": 1, "filename": 1, "uploaded_at": 1, "docai_status": 1}
    ).sort("uploaded_at", -1)]
    uid = user["_id"]
    checklist_count = await compliance_checklists_collection.count_documents({"user_id": uid})
    rule_count = await compliance_rules_collection.count_documents({"user_id": uid})
    pending_count = await compliance_reviews_collection.count_documents({
        "document_ids": {"$in": [d["_id"] for d in docs]}, "status": "PENDING"
    }) if docs else 0
    return {
        "documents": [{"id": d["_id"], "filename": d.get("filename", "Document")} for d in docs],
        "indexed_document_count": len(docs),
        "checklist_count": checklist_count,
        "rule_count": rule_count,
        "pending_review_count": pending_count,
        "notice": "Checklist and rule results are deterministic screening signals. They do not establish legal validity or authenticity."
    }


@router.post("/checklists")
async def create_checklist(payload: ChecklistCreate, user: dict = Depends(get_current_user)):
    docs = await _load_indexed_documents(user, payload.document_ids)
    ids = [d["_id"] for d in docs]
    pages = await _load_pages(ids)
    results = []
    for requirement in payload.requirements:
        exact = []
        partial = []
        for page in pages:
            text = page.get("text", "")
            lower = text.casefold()
            for keyword in requirement.keywords:
                keyword = _clean(keyword)
                if not keyword:
                    continue
                if keyword.casefold() in lower:
                    exact.append(_page_evidence(page, _snippet(text, keyword)))
                    break
                words = [w for w in re.findall(r"[\w-]+", keyword.casefold()) if len(w) > 2]
                overlap = sum(w in lower for w in words) / max(len(words), 1)
                if overlap >= 0.6:
                    partial.append(_page_evidence(page, _snippet(text, words[0] if words else "")))
                    break
        status = "FOUND" if exact else "NEEDS_VERIFICATION" if partial else "MISSING"
        # For a missing requirement, retain actual pages that were searched.
        # These excerpts document the review scope; they do not prove absence.
        evidence = exact[:5] if exact else partial[:5]
        if not evidence:
            evidence = [
                _page_evidence(page, _clean(page.get("text", ""))[:500])
                for page in pages[:3] if _clean(page.get("text", ""))
            ]
        results.append({
            "id": _id(), "label": requirement.label, "keywords": requirement.keywords,
            "status": status, "evidence": evidence,
            "message": (
                "Matching source text found." if exact else
                "Related wording found; reviewer confirmation is required." if partial else
                "No matching wording was found in the selected indexed documents; sampled pages show the search scope."
            )
        })
    checklist_id = _id()
    record = {
        "_id": checklist_id, "user_id": user["_id"], "name": payload.name,
        "document_ids": ids, "document_names": [d.get("filename", "Document") for d in docs],
        "requirements": results, "created_at": _now(), "updated_at": _now()
    }
    await compliance_checklists_collection.insert_one(record)
    # Exceptions enter the human review queue with their searched source pages.
    for item in results:
        if item["status"] != "FOUND" and item["evidence"]:
            await compliance_reviews_collection.insert_one({
                "_id": _id(), "user_id": user["_id"],
                "title": "Checklist exception: " + item["label"],
                "description": item["message"], "source_type": "CHECKLIST",
                "source_id": checklist_id, "document_ids": ids,
                "evidence": item["evidence"], "status": "PENDING",
                "history": [], "created_at": _now(), "updated_at": _now()
            })
    return record


@router.get("/checklists")
async def list_checklists(user: dict = Depends(get_current_user)):
    return {"items": [x async for x in compliance_checklists_collection.find(
        {"user_id": user["_id"]}).sort("created_at", -1).limit(100)]}


@router.get("/checklists/{checklist_id}")
async def get_checklist(checklist_id: str, user: dict = Depends(get_current_user)):
    record = await compliance_checklists_collection.find_one({"_id": checklist_id, "user_id": user["_id"]})
    if not record:
        raise HTTPException(404, "Checklist not found.")
    await _load_indexed_documents(user, record["document_ids"])
    return record


def _document_lines(pages: list[dict]) -> list[dict]:
    lines = []
    for page in pages:
        for line in (page.get("text") or "").splitlines():
            line = _clean(line)
            if line:
                lines.append({"text": line, "page": int(page.get("page", 1)),
                              "document_id": page["document_id"],
                              "filename": page.get("filename", "Document")})
    return lines


@router.post("/versions/compare")
async def compare_versions(payload: VersionCompareRequest, user: dict = Depends(get_current_user)):
    if payload.old_document_id == payload.new_document_id:
        raise HTTPException(400, "Choose two different document versions.")
    docs = await _load_indexed_documents(user, [payload.old_document_id, payload.new_document_id])
    pages = await _load_pages([payload.old_document_id, payload.new_document_id])
    old_lines = _document_lines([p for p in pages if p["document_id"] == payload.old_document_id])
    new_lines = _document_lines([p for p in pages if p["document_id"] == payload.new_document_id])
    matcher = difflib.SequenceMatcher(
        a=[x["text"].casefold() for x in old_lines],
        b=[x["text"].casefold() for x in new_lines],
        autojunk=False,
    )
    added, removed, modified = [], [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old_chunk, new_chunk = old_lines[i1:i2], new_lines[j1:j2]
        if tag == "replace":
            paired = min(len(old_chunk), len(new_chunk))
            for i in range(paired):
                modified.append({
                    "old": _page_evidence({"document_id": payload.old_document_id, **old_chunk[i]}, old_chunk[i]["text"]),
                    "new": _page_evidence({"document_id": payload.new_document_id, **new_chunk[i]}, new_chunk[i]["text"]),
                    "change": "MODIFIED"
                })
            old_chunk, new_chunk = old_chunk[paired:], new_chunk[paired:]
        removed.extend(_page_evidence({"document_id": payload.old_document_id, **x}, x["text"]) for x in old_chunk)
        added.extend(_page_evidence({"document_id": payload.new_document_id, **x}, x["text"]) for x in new_chunk)
    by_id = {d["_id"]: d for d in docs}
    return {
        "old_document": {"id": payload.old_document_id, "filename": by_id[payload.old_document_id].get("filename", "Old version")},
        "new_document": {"id": payload.new_document_id, "filename": by_id[payload.new_document_id].get("filename", "New version")},
        "summary": {"added": len(added), "removed": len(removed), "modified": len(modified)},
        "added": added[:200], "removed": removed[:200], "modified": modified[:200],
        "notice": "Text-level comparison only. Layout, signatures, seals and legal effect are not assessed."
    }


@router.post("/rules")
async def create_rule(payload: RuleCreate, user: dict = Depends(get_current_user)):
    if payload.operator in {"contains", "not_contains", "regex"} and not payload.expected_value.strip():
        raise HTTPException(400, "This rule operator requires an expected value.")
    if payload.operator == "regex":
        if len(payload.expected_value) > 160:
            raise HTTPException(400, "Regex is too long.")
        try:
            re.compile(payload.expected_value)
        except re.error as exc:
            raise HTTPException(400, f"Invalid regex: {exc}") from exc
    record = {
        "_id": _id(), "user_id": user["_id"], "name": payload.name,
        "description": payload.description, "operator": payload.operator,
        "expected_value": payload.expected_value, "severity": payload.severity,
        "created_at": _now()
    }
    await compliance_rules_collection.insert_one(record)
    return record


@router.get("/rules")
async def list_rules(user: dict = Depends(get_current_user)):
    return {"items": [x async for x in compliance_rules_collection.find(
        {"user_id": user["_id"]}).sort("created_at", -1).limit(100)]}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, user: dict = Depends(get_current_user)):
    result = await compliance_rules_collection.delete_one({"_id": rule_id, "user_id": user["_id"]})
    if not result.deleted_count:
        raise HTTPException(404, "Review rule not found.")
    return {"deleted": True, "id": rule_id}


@router.post("/rules/{rule_id}/run")
async def run_rule(rule_id: str, payload: RuleRunRequest, user: dict = Depends(get_current_user)):
    rule = await compliance_rules_collection.find_one({"_id": rule_id, "user_id": user["_id"]})
    if not rule:
        raise HTTPException(404, "Review rule not found.")
    docs = await _load_indexed_documents(user, payload.document_ids)
    ids = [d["_id"] for d in docs]
    pages = await _load_pages(ids)
    by_doc = {d["_id"]: d for d in docs}
    outcomes = []
    for did in ids:
        doc_pages = [p for p in pages if p["document_id"] == did]
        full_text = "\n".join(p.get("text", "") for p in doc_pages)
        op, expected = rule["operator"], rule.get("expected_value", "")
        evidence_page = None
        if op == "contains":
            passed = expected.casefold() in full_text.casefold()
            evidence_page = next((p for p in doc_pages if expected.casefold() in p.get("text", "").casefold()), None)
        elif op == "not_contains":
            passed = expected.casefold() not in full_text.casefold()
            evidence_page = next((p for p in doc_pages if expected.casefold() in p.get("text", "").casefold()), None)
        elif op == "regex":
            match = re.search(expected, full_text, re.I | re.M)
            passed = bool(match)
            evidence_page = next((p for p in doc_pages if match and match.group(0).casefold() in p.get("text", "").casefold()), None)
        elif op == "date_present":
            match = re.search(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", full_text)
            passed = bool(match)
            evidence_page = next((p for p in doc_pages if match and match.group(0) in p.get("text", "")), None)
        else:
            try:
                minimum = max(1, int(expected))
            except (TypeError, ValueError):
                raise HTTPException(400, "min_pages requires an integer expected value.")
            passed = len(doc_pages) >= minimum
            evidence_page = doc_pages[0] if doc_pages else None
        status = "PASS" if passed else "FAIL"
        evidence = []
        if evidence_page is None and not passed and doc_pages:
            # A failed presence rule is supported by the page(s) inspected,
            # even though the missing phrase itself cannot be quoted.
            evidence_page = doc_pages[0]
        if evidence_page:
            quote = _snippet(evidence_page.get("text", ""), expected if op in {"contains", "not_contains", "regex"} else "")
            evidence = [_page_evidence(evidence_page, quote or "Page-count check; inspect indexed source page.")]
        outcome = {
            "document_id": did, "filename": by_doc[did].get("filename", "Document"),
            "status": status, "severity": rule["severity"], "evidence": evidence,
        }
        outcomes.append(outcome)
        if not passed:
            review = {
                "_id": _id(), "user_id": user["_id"], "title": f"Rule failed: {rule['name']}",
                "description": rule.get("description", ""), "source_type": "RULE",
                "source_id": rule_id, "document_ids": [did], "evidence": evidence,
                "status": "PENDING", "history": [], "created_at": _now(), "updated_at": _now()
            }
            await compliance_reviews_collection.insert_one(review)
    return {"rule": rule, "items": outcomes, "summary": {
        "total": len(outcomes), "passed": sum(x["status"] == "PASS" for x in outcomes),
        "failed": sum(x["status"] == "FAIL" for x in outcomes)
    }}


@router.post("/reviews")
async def create_review(payload: ReviewCreate, user: dict = Depends(get_current_user)):
    await _load_indexed_documents(user, payload.document_ids)
    if any(item.document_id not in payload.document_ids for item in payload.evidence):
        raise HTTPException(400, "Evidence must reference a selected document.")
    record = {
        "_id": _id(), "user_id": user["_id"], "title": payload.title,
        "description": payload.description, "source_type": payload.source_type,
        "source_id": payload.source_id, "document_ids": list(dict.fromkeys(payload.document_ids)),
        "evidence": [item.model_dump() for item in payload.evidence],
        "status": "PENDING", "history": [], "created_at": _now(), "updated_at": _now()
    }
    await compliance_reviews_collection.insert_one(record)
    return record


@router.get("/reviews")
async def list_reviews(status: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    if status and status not in {"PENDING", "ACCEPTED", "REJECTED", "CORRECTED", "NEEDS_FURTHER_REVIEW"}:
        raise HTTPException(400, "Invalid review status.")
    accessible = await _load_all_accessible_ids(user)
    query: dict[str, Any] = {"document_ids": {"$in": accessible}}
    if status:
        query["status"] = status
    return {"items": [x async for x in compliance_reviews_collection.find(query).sort("updated_at", -1).limit(200)]}


async def _load_all_accessible_ids(user: dict) -> list[str]:
    docs = [d async for d in documents_collection.find(document_scope(user), {"_id": 1})]
    return [d["_id"] for d in docs]


@router.patch("/reviews/{review_id}")
async def update_review(review_id: str, payload: ReviewUpdate, user: dict = Depends(get_current_user)):
    record = await compliance_reviews_collection.find_one({"_id": review_id})
    if not record:
        raise HTTPException(404, "Review item not found.")
    await _load_indexed_documents(user, record["document_ids"])
    if payload.action == "CORRECT" and not (payload.corrected_value or "").strip():
        raise HTTPException(400, "Provide corrected_value when choosing CORRECT.")
    status_map = {
        "ACCEPT": "ACCEPTED", "REJECT": "REJECTED",
        "CORRECT": "CORRECTED", "MARK_FOR_REVIEW": "NEEDS_FURTHER_REVIEW"
    }
    event = {
        "id": _id(), "action": payload.action, "status": status_map[payload.action],
        "comment": payload.comment, "corrected_value": payload.corrected_value,
        "user_id": user["_id"], "reviewer_role": user.get("role"), "timestamp": _now()
    }
    await compliance_reviews_collection.update_one(
        {"_id": review_id},
        {"$set": {"status": event["status"], "updated_at": _now()},
         "$push": {"history": event}}
    )
    await compliance_events_collection.insert_one({
        "_id": _id(), "review_id": review_id, "document_ids": record["document_ids"], **event
    })
    return await compliance_reviews_collection.find_one({"_id": review_id})


@router.get("/reviews/{review_id}/history")
async def review_history(review_id: str, user: dict = Depends(get_current_user)):
    record = await compliance_reviews_collection.find_one({"_id": review_id})
    if not record:
        raise HTTPException(404, "Review item not found.")
    await _load_indexed_documents(user, record["document_ids"])
    return {"review_id": review_id, "history": record.get("history", [])}
