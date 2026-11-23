"""Evidence-backed comparison of explicitly labelled document dates.

Date disagreements are surfaced for review; this module never decides legal precedence.
"""
import hashlib
import re
from datetime import date
from typing import List, Optional

from .nlp import sentence_spans

MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
MON = "|".join(MONTHS)
DATE_PATTERNS = [
    re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + MON + r")[,]?\s+(\d{4})", re.I),
    re.compile(r"(" + MON + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"),
]
LABELS = {
    "due_date": re.compile(r"\b(?:due\s+date|payment\s+due(?:\s+date)?)\b\s*(?:is|on|:|shall\s+be|will\s+be)?\s*", re.I),
    "expiry_date": re.compile(r"\b(?:expiry\s+date|expires?\s+on|expiration\s+date|valid\s+until)\b\s*(?:is|:)?\s*", re.I),
    "renewal_date": re.compile(r"\b(?:renewal\s+date|renew(?:s|ed)?\s+on)\b\s*(?:is|:)?\s*", re.I),
    "commencement_date": re.compile(r"\b(?:commencement\s+date|commences?\s+on|starts?\s+on)\b\s*(?:is|:)?\s*", re.I),
    "deadline": re.compile(r"\b(?:deadline|last\s+date|must\s+be\s+submitted\s+by)\b\s*(?:is|on|:)?\s*", re.I),
}
SCOPE_RE = re.compile(r"\b(?:survey|plot|khasra|khata|clause|section)\s*(?:no\.?|number)?\s*[:#]?\s*([\w/-]*\d[\w/-]*)", re.I)


def _parse(match: re.Match, index: int) -> Optional[date]:
    g = match.groups()
    try:
        if index == 0:
            return date(int(g[2]), MONTHS[g[1].lower()], int(g[0]))
        if index == 1:
            return date(int(g[2]), MONTHS[g[0].lower()], int(g[1]))
        if index == 2:
            return date(int(g[0]), int(g[1]), int(g[2]))
        return date(int(g[2]), int(g[1]), int(g[0]))
    except (ValueError, KeyError):
        return None


def _date_after(sentence: str, label: re.Pattern) -> Optional[tuple]:
    for label_match in label.finditer(sentence):
        tail = sentence[label_match.end():label_match.end() + 40].lstrip(" :")
        for index, pattern in enumerate(DATE_PATTERNS):
            match = pattern.match(tail)
            parsed = _parse(match, index) if match else None
            if parsed:
                return parsed, match.group(0)
    return None


def _extract(page: dict) -> List[dict]:
    found = []
    for start, end in sentence_spans(page["text"]):
        sentence = page["text"][start:end]
        for label, pattern in LABELS.items():
            parsed = _date_after(sentence, pattern)
            if parsed:
                value, raw = parsed
                found.append({
                    "label": label, "value": value, "raw": raw, "sentence": sentence,
                    "start": start, "end": end, "document_id": page["document_id"],
                    "filename": page["filename"], "page": page["page"],
                    "scope": {x.lower() for x in SCOPE_RE.findall(sentence)},
                    "source_type": page["source_type"],
                })
    return found


def detect_date_conflicts(pages: List[dict], detected_at: str) -> List[dict]:
    """Compare same-labelled dates across documents; never infer which date controls."""
    grouped = {}
    for page in pages:
        for fact in _extract(page):
            grouped.setdefault(fact["label"], []).append((page, fact))

    conflicts = []
    for label, entries in grouped.items():
        seen = set()
        for index, (page_a, a) in enumerate(entries):
            for page_b, b in entries[index + 1:]:
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
                for page, fact in ((page_a, a), (page_b, b)):
                    quote = fact["sentence"]
                    q = " ".join(quote.split())
                    source = " ".join(page["text"].split())
                    verified = q in source
                    evidence.append({
                        "evidence_id": "ev_" + hashlib.sha1(
                            f'{fact["document_id"]}|{fact["page"]}|{fact["start"]}|{fact["end"]}'.encode()
                        ).hexdigest()[:10],
                        "document_id": fact["document_id"], "filename": fact["filename"],
                        "page_number": fact["page"], "section": None, "quote": quote,
                        "start_char": fact["start"], "end_char": fact["end"],
                        "relation": "CONTRADICTS", "source_type": fact["source_type"],
                        "verification": {"quote_found_in_source": verified, "page_verified": verified},
                    })
                uncertain_scope = bool(a["scope"]) != bool(b["scope"])
                cid = "con_" + hashlib.sha1(repr(pair).encode()).hexdigest()[:10]
                conflicts.append({
                    "contradiction_id": cid, "topic": label.replace("_", " "),
                    "status": "NEEDS_HUMAN_REVIEW" if uncertain_scope else "OPEN",
                    "severity": "HIGH",
                    "explanation": (
                        f'{a["filename"]} p.{a["page"]} states {a["raw"]}; '
                        f'{b["filename"]} p.{b["page"]} states {b["raw"]} for {label.replace("_", " ")}. '
                        "The system does not infer which date is legally controlling."
                    ),
                    "evidence": evidence,
                    "resolution": {"rule": None, "controlling_document_id": None,
                                   "effective_from": None, "requires_human_review": True},
                    "detected_at": detected_at,
                    "_doc_ids": [a["document_id"], b["document_id"]],
                })
    return conflicts
