"""Conservative extraction of explicitly labelled eligibility and obligation thresholds.

Only same-label, numeric rule values are compared. Conflicts are flagged for human review;
this module never decides which document governs.
"""
import hashlib
import re
from typing import List

from .nlp import sentence_spans

NUM = r"(\d[\d,]*(?:\.\d+)?)"
RULES = [
    ("minimum_age", re.compile(r"\b(?:minimum\s+age(?:\s+requirement)?|at\s+least)\s*(?:is|of)?\s*" + NUM + r"\s*years?\s*(?:old|of\s+age)?\b", re.I), "years"),
    ("maximum_age", re.compile(r"\b(?:maximum\s+age(?:\s+limit)?|not\s+more\s+than)\s*(?:is|of)?\s*" + NUM + r"\s*years?\b", re.I), "years"),
    ("minimum_income", re.compile(r"\b(?:minimum\s+(?:annual\s+)?income|annual\s+income\s+of\s+at\s+least)\s*(?:is|of|shall\s+be)?\s*(?:rs\.?|inr|₹)?\s*" + NUM, re.I), "inr"),
    ("notice_period", re.compile(r"\bnotice\s+period\s*(?:is|of|shall\s+be)?\s*" + NUM + r"\s*(days?|months?)\b", re.I), "period"),
    ("submission_period", re.compile(r"\b(?:submit|submission|file|filing)\b[^.!?]{0,100}?\bwithin\s+" + NUM + r"\s*(days?|months?)\b", re.I), "period"),
    ("repayment_period", re.compile(r"\b(?:repay|repayment)\b[^.!?]{0,100}?\bwithin\s+" + NUM + r"\s*(days?|months?|years?)\b", re.I), "period"),
]
SCOPE_RE = re.compile(r"\b(?:survey|plot|khasra|khata|clause|section)\s*(?:no\.?|number)?\s*[:#]?\s*([\w/-]*\d[\w/-]*)", re.I)


def _extract(page: dict) -> List[dict]:
    facts = []
    for start, end in sentence_spans(page["text"]):
        sentence = page["text"][start:end]
        for label, pattern, unit in RULES:
            matches = list(pattern.finditer(sentence))
            if len(matches) != 1:
                continue
            match = matches[0]
            raw_value = float(match.group(1).replace(",", ""))
            actual_unit = unit
            if unit == "period":
                actual_unit = match.group(2).lower().rstrip("s")
            facts.append({
                "label": label, "value": raw_value, "unit": actual_unit,
                "raw": match.group(0), "sentence": sentence, "start": start, "end": end,
                "document_id": page["document_id"], "filename": page["filename"],
                "page": page["page"], "scope": {x.lower() for x in SCOPE_RE.findall(sentence)},
                "source_type": page["source_type"],
            })
    return facts


def detect_rule_conflicts(pages: List[dict], detected_at: str) -> List[dict]:
    grouped = {}
    for page in pages:
        for fact in _extract(page):
            grouped.setdefault((fact["label"], fact["unit"]), []).append(fact)

    conflicts = []
    page_lookup = {(p["document_id"], p["page"]): p["text"] for p in pages}
    for (label, unit), facts in grouped.items():
        seen = set()
        for index, a in enumerate(facts):
            for b in facts[index + 1:]:
                if a["document_id"] == b["document_id"] or a["value"] == b["value"]:
                    continue
                if a["scope"] and b["scope"] and not (a["scope"] & b["scope"]):
                    continue
                pair = tuple(sorted(((a["document_id"], a["page"], a["start"]),
                                     (b["document_id"], b["page"], b["start"]))))
                if pair in seen:
                    continue
                seen.add(pair)
                evidence = []
                for fact in (a, b):
                    quote = fact["sentence"]
                    # Sentence is an exact slice from its originating page.
                    evidence.append({
                        "evidence_id": "ev_" + hashlib.sha1(
                            f'{fact["document_id"]}|{fact["page"]}|{fact["start"]}|{fact["end"]}'.encode()
                        ).hexdigest()[:10],
                        "document_id": fact["document_id"], "filename": fact["filename"],
                        "page_number": fact["page"], "section": None, "quote": quote,
                        "start_char": fact["start"], "end_char": fact["end"],
                        "relation": "CONTRADICTS", "source_type": fact["source_type"],
                        "verification": {"quote_found_in_source": page_lookup.get((fact["document_id"], fact["page"]), "")[fact["start"]:fact["end"]] == quote,
                                         "page_verified": page_lookup.get((fact["document_id"], fact["page"]), "")[fact["start"]:fact["end"]] == quote},
                    })
                uncertain_scope = bool(a["scope"]) != bool(b["scope"])
                conflicts.append({
                    "contradiction_id": "con_" + hashlib.sha1(repr(pair).encode()).hexdigest()[:10],
                    "topic": label.replace("_", " "), "status": "NEEDS_HUMAN_REVIEW" if uncertain_scope else "OPEN",
                    "severity": "HIGH",
                    "explanation": (
                        f'{a["filename"]} p.{a["page"]} states {a["raw"]}; '
                        f'{b["filename"]} p.{b["page"]} states {b["raw"]}. '
                        "Both statements concern the same labelled rule; governing precedence requires review."
                    ),
                    "evidence": evidence,
                    "resolution": {"rule": None, "controlling_document_id": None,
                                   "effective_from": None, "requires_human_review": True},
                    "detected_at": detected_at,
                    "_doc_ids": [a["document_id"], b["document_id"]],
                })
    return conflicts
