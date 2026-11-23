"""Extractive cross-document QA with backend-verified page citations and abstention."""
from datetime import datetime
from typing import Dict, List

from ...models import gen_uuid
from . import facts as F
from .nlp import bm25_rank, sentence_spans, tokens
from .embeddings import reciprocal_rank_fusion

MIN_COVERAGE = 0.5      # share of question terms a passage must contain to be used as evidence
PARTIAL_BELOW = 0.8     # coverage below this -> PARTIALLY_SUPPORTED
MAX_CLAIMS = 3
FAITHFULNESS_METHOD = "verified_claim_ratio"


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def build_chunks(pages: List[dict]) -> List[dict]:
    chunks = []
    for p in pages:
        for s, e in sentence_spans(p["text"]):
            chunks.append({"page": p, "start": s, "end": e, "tokens": tokens(p["text"][s:e])})
    return chunks


def faithfulness(claims: List[dict]):
    if not claims:
        return None
    return round(sum(c["status"] == "SUPPORTED" for c in claims) / len(claims), 4)


def answer_question(question: str, pages: List[dict], doc_ids: List[str], include_superseded: bool = True,
                    max_evidence: int = 5, vector_scores: Dict[tuple, float] | None = None) -> dict:
    q_terms = sorted(set(tokens(question)))
    chunks = build_chunks(pages)
    analysis = F.analyse(pages)
    # documents whose conflicting value was replaced by an effective amendment
    replaced_ev = {}
    for c in analysis["contradictions"]:
        if c["status"] == "RESOLVED_BY_AMENDMENT":
            for ev in c["evidence"]:
                if ev["relation"] != "SUPPORTS":
                    replaced_ev[ev["evidence_id"]] = c

    chunk_map, lexical_scores = {}, {}
    for c in chunks:
        p = c["page"]
        key = (p["document_id"], p["page"], c["start"], c["end"])
        chunk_map[key] = c
    bm25_ranking, vector_ranking = [], []
    if q_terms and chunks:
        bm = bm25_rank(q_terms, [c["tokens"] for c in chunks])
        for c, score in zip(chunks, bm):
            p = c["page"]
            key = (p["document_id"], p["page"], c["start"], c["end"])
            coverage = len(set(q_terms) & set(c["tokens"])) / len(q_terms)
            if coverage >= MIN_COVERAGE and score > 0:
                lexical_scores[key] = (score, coverage)
        bm25_ranking = [key for key, _ in sorted(lexical_scores.items(), key=lambda item: (-item[1][0], item[0]))[:50]]
    if vector_scores:
        vector_ranking = [key for key, score in sorted(vector_scores.items(), key=lambda item: (-item[1], item[0]))
                          if key in chunk_map and score >= 0.35
                          and len(set(q_terms) & set(chunk_map[key]["tokens"])) / max(1, len(q_terms)) >= 0.25][:50]
    fused = reciprocal_rank_fusion([[repr(key) for key in bm25_ranking], [repr(key) for key in vector_ranking]])
    scored = []
    key_lookup = {repr(candidate): candidate for candidate in chunk_map}
    for key, fused_score in fused.items():
        chunk_key = key_lookup.get(key)
        if chunk_key is None:
            continue
        c = chunk_map[chunk_key]
        coverage = len(set(q_terms) & set(c["tokens"])) / max(1, len(q_terms))
        semantic_only = chunk_key not in lexical_scores
        scored.append((fused_score, coverage, c, semantic_only))
    scored.sort(key=lambda x: (-x[0], x[2]["page"]["document_id"], x[2]["page"]["page"], x[2]["start"]))

    claims, evidences = [], {}
    for s, cov, c, semantic_only in scored:
        if len(claims) >= min(MAX_CLAIMS, max_evidence):
            break
        ev = F.evidence(c["page"], c["start"], c["end"], "SUPPORTS")
        if not ev["verification"]["quote_found_in_source"]:
            continue  # never emit a citation the backend could not verify
        if ev["evidence_id"] in evidences:
            continue
        old = replaced_ev.get(ev["evidence_id"])
        if old and not include_superseded:
            continue
        status = "SUPPORTED" if cov >= PARTIAL_BELOW and not semantic_only else "PARTIALLY_SUPPORTED"
        explanation = f"Passage contains {round(cov * 100)}% of the question's key terms."
        if semantic_only:
            explanation += " Retrieved by semantic similarity only; human verification is required."
        if old:
            status, ev["relation"] = "CONTRADICTED", "CONTRADICTS"
            explanation = ("Superseded: an amendment effective "
                           f"{old['resolution']['effective_from']} replaces this value ({old['contradiction_id']}).")
        evidences[ev["evidence_id"]] = ev
        claims.append({"claim_id": "claim_" + gen_uuid()[:12], "text": ev["quote"], "status": status,
                       "confidence": round(cov, 4), "evidence_ids": [ev["evidence_id"]], "explanation": explanation,
                       "requires_human_review": status != "SUPPORTED", "review": None})

    relevant = [c for c in analysis["contradictions"]
                if set(tokens(c["topic"])) & set(q_terms) and c["status"] != "RESOLVED_BY_AMENDMENT"]
    conflicts = [{k: v for k, v in c.items() if k != "_doc_ids"} for c in relevant]
    abstained = not claims
    if abstained:
        answer = "I cannot determine this from the selected documents."
        missing = [{"description": "No passage covering the question's key terms was found.",
                    "searched_document_ids": doc_ids}]
    else:
        answer = " ".join(f"[{evidences[c['evidence_ids'][0]]['filename']}, p.{evidences[c['evidence_ids'][0]]['page_number']}] "
                          f"{c['text']}" for c in claims)
        if conflicts:
            answer += " Note: the selected documents contain conflicting values on this topic; see conflicts."
        missing = []
    return {"answer_id": "ans_" + gen_uuid()[:12], "question": question, "answer": answer, "abstained": abstained,
            "faithfulness_score": 0.0 if abstained else faithfulness(claims),
            "faithfulness_method": FAITHFULNESS_METHOD,
            "retrieval_mode": "HYBRID_BM25_VECTOR" if vector_scores else "BM25", "claims": claims,
            "evidence": list(evidences.values()), "missing_evidence": missing, "conflicts": conflicts,
            "created_at": _now()}


def reverify(answer: dict, pages_by_key: Dict[tuple, dict], verify_quotes: bool, recheck_claims: bool) -> dict:
    """Re-checks every stored citation against current page text and recomputes the score."""
    invalid = 0
    for ev in answer["evidence"]:
        page = pages_by_key.get((ev["document_id"], ev["page_number"]))
        span = F.verify_quote(page["text"], ev["quote"]) if (page and verify_quotes) else (None if verify_quotes else (ev["start_char"], ev["end_char"]))
        ok = span is not None
        ev["verification"] = {"quote_found_in_source": ok, "page_verified": ok}
        invalid += 0 if ok else 1
    ev_ok = {e["evidence_id"]: e["verification"]["quote_found_in_source"] for e in answer["evidence"]}
    if recheck_claims:
        for c in answer["claims"]:
            if not all(ev_ok.get(i) for i in c["evidence_ids"]):
                c["status"], c["requires_human_review"] = "INSUFFICIENT_EVIDENCE", True
                c["explanation"] = "Cited quote could not be verified on the cited page."
    answer["faithfulness_score"] = 0.0 if answer["abstained"] else faithfulness(answer["claims"])
    return {"answer_id": answer["answer_id"], "verification_status": "COMPLETED",
            "faithfulness_score": answer["faithfulness_score"], "faithfulness_method": FAITHFULNESS_METHOD,
            "claims_checked": len(answer["claims"]),
            **{f"claims_{k}": sum(c["status"] == s for c in answer["claims"]) for k, s in (
                ("supported", "SUPPORTED"), ("partially_supported", "PARTIALLY_SUPPORTED"),
                ("contradicted", "CONTRADICTED"), ("insufficient_evidence", "INSUFFICIENT_EVIDENCE"))},
            "invalid_citation_count": invalid, "verified_at": _now()}
