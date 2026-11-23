"""Evidence-linked intelligence extraction for the TrustLens workspace.

This module deliberately uses deterministic patterns and existing OCR/layout metadata.
Extracted entities are candidates for review, not legal conclusions.
"""
import hashlib
import re
from typing import Dict, List, Tuple

from .nlp import tokens, bm25_rank

PATTERNS = {
    "PROPERTY_ID": [
        re.compile(r"\b(?:khasra|khata|survey|plot|gat)\s*(?:no\.?|number|#)?\s*[:.-]?\s*([A-Z0-9/-]{2,24})", re.I),
    ],
    "AGREEMENT_ID": [
        re.compile(r"\b(?:agreement|deed|document|registration)\s*(?:no\.?|number|#)?\s*[:.-]?\s*([A-Z0-9/-]{3,30})", re.I),
    ],
    "DATE": [
        re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b", re.I),
    ],
    "OWNER": [
        re.compile(r"\b(?:owner|owned by|purchaser|seller|lessor|lessee|applicant|in the name of)\s*[:：-]?\s*([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,4})", re.I),
        re.compile(r"(?:मालिक|स्वामी|खातेदार|आवेदक)\s*[:：-]?\s*([\u0900-\u097F]{2,30}(?:\s+[\u0900-\u097F]{2,30}){0,3})"),
    ],
}
LABELS = {"OWNER": "Person / owner candidate", "PROPERTY_ID": "Property identifier", "AGREEMENT_ID": "Document reference", "DATE": "Date"}


def _id(kind: str, value: str) -> str:
    return kind.lower() + "_" + hashlib.sha1((kind + "|" + value.casefold()).encode()).hexdigest()[:12]


def _normal(value: str) -> str:
    return " ".join(value.strip(" .,:;-").split())


def _confidence(page: dict, matched_text: str) -> Tuple[float, str]:
    meta = page.get("extraction_metadata") or {}
    blocks = page.get("layout_blocks") or []
    matching = [b for b in blocks if matched_text.casefold() in str(b.get("text", "")).casefold()]
    scores = [float(b["confidence"]) for b in matching if isinstance(b.get("confidence"), (int, float)) and b["confidence"] >= 0]
    if scores:
        score = sum(scores) / len(scores)
        basis = "OCR line confidence"
    elif isinstance(meta.get("ocr_confidence_avg"), (int, float)):
        score = float(meta["ocr_confidence_avg"])
        basis = "page OCR confidence"
    elif page.get("source_type") == "PDF_TEXT":
        score, basis = 0.72, "native PDF text layer; heuristic extraction score"
    else:
        score, basis = 0.68, "text extraction heuristic; not model-calibrated"
    return max(0.0, min(1.0, score)), basis


def extract_entities(pages: List[dict]) -> dict:
    nodes: Dict[str, dict] = {}
    edges: Dict[str, dict] = {}
    fields: List[dict] = []
    visual: List[dict] = []
    docs = {}
    for page in pages:
        did = page["document_id"]
        docs[did] = page.get("filename", "Document")
        doc_node = "document_" + did
        nodes.setdefault(doc_node, {"id": doc_node, "type": "DOCUMENT", "label": docs[did], "document_id": did})
        local_entities = []
        source_text = page.get("text", "")
        for kind, regexes in PATTERNS.items():
            for rx in regexes:
                for match in rx.finditer(source_text):
                    value = _normal(match.group(1) if kind == "OWNER" else match.group(0) if kind == "DATE" else match.group(1))
                    if len(value) < 2:
                        continue
                    start, end = match.span()
                    quote = source_text[max(0, start - 65):min(len(source_text), end + 65)].strip()
                    confidence, basis = _confidence(page, value)
                    status = "VERIFIED" if confidence >= .85 and value.casefold() in source_text.casefold() else "NEEDS_REVIEW" if confidence >= .60 else "UNCERTAIN"
                    eid = _id(kind, value)
                    nodes.setdefault(eid, {"id": eid, "type": kind, "label": value, "category": LABELS[kind]})
                    edge_id = _id("EDGE", doc_node + "|" + eid + "|" + str(page["page"]))
                    edges.setdefault(edge_id, {"id": edge_id, "source": doc_node, "target": eid, "type": "MENTIONS", "document_id": did, "page": page["page"]})
                    local_entities.append((kind, eid))
                    fields.append({
                        "id": _id("FIELD", f"{did}|{page['page']}|{kind}|{value}|{start}"),
                        "document_id": did, "filename": docs[did], "page": page["page"],
                        "field_type": kind, "label": LABELS[kind], "value": value,
                        "confidence": round(confidence, 3), "confidence_basis": basis,
                        "status": status, "quote": quote,
                        "source_verified": value.casefold() in source_text.casefold(),
                    })
        owners = [eid for kind, eid in local_entities if kind == "OWNER"]
        properties = [eid for kind, eid in local_entities if kind == "PROPERTY_ID"]
        for owner in owners:
            for prop in properties:
                edge_id = _id("EDGE", owner + "|" + prop + "|" + did + "|" + str(page["page"]))
                edges.setdefault(edge_id, {"id": edge_id, "source": owner, "target": prop, "type": "APPEARS_WITH", "document_id": did, "page": page["page"], "requires_review": True})

        blocks = page.get("layout_blocks") or []
        low_blocks = [b for b in blocks if isinstance(b.get("confidence"), (int, float)) and 0 <= b["confidence"] < .60]
        low_blocks = [{"text": b.get("text", ""), "confidence": b.get("confidence"), "bbox": b.get("bbox", [])} for b in low_blocks]
        text_lower = source_text.casefold()
        cues = []
        if re.search(r"signature|signed| हस्ताक्षर|दस्तखत", text_lower):
            cues.append("Signature wording found in extracted text; inspect original page for actual signature.")
        if re.search(r"stamp|seal|revenue stamp|मोह[रर]|मुहर|स्टाम्प", text_lower):
            cues.append("Stamp/seal wording found in extracted text; visual seal authenticity is not assessed.")
        if page.get("source_type") == "OCR_TEXT" and (low_blocks or (page.get("extraction_metadata") or {}).get("quality_status") in ("LOW", "REVIEW")):
            cues.append("Low-confidence scanned text; manually inspect handwriting and unclear regions.")
        if cues or low_blocks:
            visual.append({
                "document_id": did, "filename": docs[did], "page": page["page"],
                "source_type": page.get("source_type"), "review_candidates": low_blocks,
                "signals": cues or ["Low-confidence OCR region; manual visual inspection recommended."],
                "analysis_status": "REVIEW_CANDIDATE_ONLY",
            })
    return {
        "nodes": list(nodes.values()), "edges": list(edges.values()),
        "fields": fields, "visual_review": visual,
        "documents": [{"id": did, "filename": name} for did, name in docs.items()],
        "notice": "Entity and relationship candidates are pattern-extracted from indexed text. Co-occurrence is not proof of legal ownership or title.",
    }


def search_pages(query: str, pages: List[dict], limit: int = 20) -> list:
    query_terms = tokens(query)
    if not query_terms:
        return []
    ranked_docs = [tokens(p.get("text", "")) for p in pages]
    scores = bm25_rank(query_terms, ranked_docs)
    ranked = sorted(zip(scores, pages), key=lambda item: item[0], reverse=True)
    results = []
    for score, page in ranked:
        if score <= 0:
            continue
        text = page.get("text", "")
        terms = [t for t in query_terms if t in tokens(text)]
        snippet = text[:900]
        if len(text) > 900 and terms:
            low = text.casefold()
            pos = min([low.find(t) for t in terms if low.find(t) >= 0] or [0])
            snippet = text[max(0, pos - 260):min(len(text), pos + 640)]
        results.append({
            "document_id": page["document_id"], "filename": page.get("filename"),
            "page": page["page"], "score": round(float(score), 4),
            "matched_terms": terms, "snippet": snippet,
            "source_type": page.get("source_type"),
        })
        if len(results) >= limit:
            break
    return results
