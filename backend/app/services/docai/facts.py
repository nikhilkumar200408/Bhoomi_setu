"""Rule-based fact extraction, contradiction detection and amendment tracking.

A "fact" is a numeric value (percent, rupee amount, area, duration) found in a sentence that also names a
topic word (interest, rent, penalty ...). Two facts conflict only when they share topic + unit, carry
different values, and do not obviously refer to different plots/clauses. Precedence is never decided by
upload order: an amendment only wins when (a) the amending text uses amendment language, (b) it identifies
the base document, and (c) an effective date is stated and has been reached. Anything else is surfaced for
human review.
"""
import hashlib
import re
from datetime import date, datetime
from typing import Dict, List, Optional

from .nlp import sentence_spans
from .date_conflicts import detect_date_conflicts
from .rule_conflicts import detect_rule_conflicts

TOPICS = ["interest", "penalty", "fee", "rent", "price", "consideration", "tax", "duty", "deposit",
          "premium", "tenure", "period", "area", "rate", "amount"]
WORDNUM = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
WORDNUM.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                "hundred": 100})
_NUM = r"\b(\d[\d,]*(?:\.\d+)?|" + "|".join(WORDNUM) + r")"
PATTERNS = [
    ("percent", re.compile(_NUM + r"\s*(?:%|per\s*cent|percent)", re.I)),
    ("inr", re.compile(r"(?:rs\.?|inr|₹)\s*" + r"(\d[\d,]*(?:\.\d+)?)", re.I)),
    ("area", re.compile(_NUM + r"\s*(acres?|hectares?|guntas?)", re.I)),
    ("duration", re.compile(_NUM + r"\s*(years?|months?|days?)", re.I)),
]
MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
_MON = "|".join(MONTHS)
DATE_RES = [
    re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MON + r")[,]?\s+(\d{4})", re.I),
    re.compile(r"(" + _MON + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"),  # day-first (Indian convention)
]
AMEND_CUE = re.compile(r"amend|revis|substitut|supersed|in place of|modif|replac", re.I)
SCOPE_RE = re.compile(r"\b(?:survey|plot|khasra|khata|clause|section)\s*(?:no\.?|number)?\s*[:#]?\s*([\w/-]*\d[\w/-]*)", re.I)
REF_ID_RE = re.compile(r"\b[A-Z]{2,}[-/]\d[\w/-]*\b")
EFFECTIVE_RE = re.compile(r"(?:effective|with effect)\s+(?:from|on|date)?[:\s]*", re.I)
ANNOUNCED_RE = re.compile(r"(?:dated|announced on|published on|notified on|issued on)[:\s]*", re.I)


def _num(s: str) -> Optional[float]:
    s = s.lower().replace(",", "")
    if s in WORDNUM:
        return float(WORDNUM[s])
    try:
        return float(s)
    except ValueError:
        return None


def _parse_match(m: re.Match, idx: int) -> Optional[date]:
    g = m.groups()
    try:
        if idx == 0:
            return date(int(g[2]), MONTHS[g[1].lower()], int(g[0]))
        if idx == 1:
            return date(int(g[2]), MONTHS[g[0].lower()], int(g[1]))
        if idx == 2:
            return date(int(g[0]), int(g[1]), int(g[2]))
        return date(int(g[2]), int(g[1]), int(g[0]))
    except (ValueError, KeyError):
        return None


def date_after(text: str, label_re: re.Pattern) -> Optional[str]:
    """ISO date that directly follows a label such as 'effective from' (within 40 chars)."""
    for lm in label_re.finditer(text):
        window = text[lm.end(): lm.end() + 40]
        for idx, dre in enumerate(DATE_RES):
            m = dre.match(window.lstrip(" :"))
            d = _parse_match(m, idx) if m else None
            if d:
                return d.isoformat()
    return None


def _fact_topic(low: str) -> Optional[str]:
    if re.search(r"\bprocessing\s+fees?\b", low):
        return "processing fee"

    if (
        re.search(r"\b(?:overdue|late payment|delayed payment)\b", low)
        and re.search(r"\b(?:fee|fees|penalty|penalties|charge|charges)\b", low)
    ):
        return "overdue charge"

    return next((t for t in TOPICS if re.search(r"\b" + t, low)), None)


def extract_facts(page: dict) -> List[dict]:
    text = page["text"]
    facts = []
    for s, e in sentence_spans(text):
        sent = text[s:e]
        low = sent.lower()
        topic = _fact_topic(low)
        if not topic:
            continue
        for unit, rx in PATTERNS:
            found = list(rx.finditer(sent))
            if len(found) != 1:  # ambiguous: several values of one unit in a sentence -> skip, never guess
                continue
            value = _num(found[0].group(1))
            if value is None:
                continue
            u = unit if unit != "area" and unit != "duration" else found[0].group(2).lower().rstrip("s")
            facts.append({"topic": topic, "unit": u, "value": value, "raw": found[0].group(0),
                          "document_id": page["document_id"], "filename": page["filename"], "page": page["page"],
                          "start": s, "end": e, "sentence": sent,
                          "scope": {x.lower() for x in SCOPE_RE.findall(sent)}, "source_type": page["source_type"]})
    return facts


def verify_quote(page_text: str, quote: str) -> Optional[tuple]:
    """Backend-side check that `quote` occurs verbatim (after whitespace normalisation) on the page."""
    q = " ".join(quote.split())
    i = page_text.find(q) if q else -1
    return (i, i + len(q)) if i >= 0 else None


def section_for(page_text: str, start: int) -> Optional[str]:
    last = None
    for m in re.finditer(r"(?:clause|section|article)\s+[\w.()-]+", page_text[:start], re.I):
        last = m.group(0)
    return last


def evidence(page: dict, start: int, end: int, relation: str) -> dict:
    quote = page["text"][start:end]
    span = verify_quote(page["text"], quote)
    eid = "ev_" + hashlib.sha1(f"{page['document_id']}|{page['page']}|{start}|{end}".encode()).hexdigest()[:10]
    return {"evidence_id": eid, "document_id": page["document_id"], "filename": page["filename"],
            "page_number": page["page"], "section": section_for(page["text"], start), "quote": quote,
            "start_char": span[0] if span else None, "end_char": span[1] if span else None,
            "relation": relation, "source_type": page["source_type"],
            "verification": {"quote_found_in_source": span is not None, "page_verified": span is not None}}


def _doc_text(pages: List[dict], doc_id: str) -> str:
    return " ".join(p["text"] for p in pages if p["document_id"] == doc_id)


def _stem(filename: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", filename.rsplit(".", 1)[0].lower()).strip()


def _base_identified(base_id: str, amend_id: str, pages: List[dict], names: Dict[str, str]) -> bool:
    amend_text = _doc_text(pages, amend_id)
    stem = _stem(names[base_id])
    # strip the stored upload prefix (uuid_) if present, then require a meaningful stem
    stem = re.sub(r"^[0-9a-f]{8}( [0-9a-f]{4}){3} [0-9a-f]{12} ", "", stem)
    if len(stem) >= 4 and stem in re.sub(r"[^a-z0-9]+", " ", amend_text.lower()):
        return True
    return bool(set(REF_ID_RE.findall(_doc_text(pages, base_id))) & set(REF_ID_RE.findall(amend_text)))


def _is_amending(fact: dict, pages: List[dict]) -> bool:
    if AMEND_CUE.search(fact["sentence"]):
        return True
    first = next((p for p in pages if p["document_id"] == fact["document_id"] and p["page"] == 1), None)
    return bool(first and AMEND_CUE.search(first["text"][:300]))  # title/heading of the document


def analyse(pages: List[dict], today: Optional[date] = None) -> dict:
    """Returns {'contradictions': [...], 'amendments': [...]} for the given indexed pages."""
    today = today or datetime.utcnow().date()
    names = {p["document_id"]: p["filename"] for p in pages}
    page_index = {(p["document_id"], p["page"]): p for p in pages}
    by_key: Dict[tuple, List[dict]] = {}
    for p in pages:
        for f in extract_facts(p):
            by_key.setdefault((f["topic"], f["unit"]), []).append(f)

    contradictions, amendments, edges, now = [], [], [], datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    for (topic, unit), facts in by_key.items():
        seen_pairs = set()
        for i, a in enumerate(facts):
            for b in facts[i + 1:]:
                if a["value"] == b["value"] or (a["document_id"], a["page"], a["start"]) == (b["document_id"], b["page"], b["start"]):
                    continue
                if a["document_id"] == b["document_id"] and a["page"] == b["page"]:
                    continue
                if a["scope"] and b["scope"] and not (a["scope"] & b["scope"]):
                    continue  # clearly different plot/clause: different values are not a contradiction
                pair = tuple(sorted([(a["document_id"], a["page"], a["start"]), (b["document_id"], b["page"], b["start"])]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                scope_uncertain = bool(a["scope"]) != bool(b["scope"])
                aa, bb = _is_amending(a, pages), _is_amending(b, pages)
                base = amend = None
                if a["document_id"] != b["document_id"] and aa != bb:
                    amend, base = (a, b) if aa else (b, a)
                status, rule, controlling, eff, ann, requires = "OPEN", None, None, None, None, True
                amd = None
                if amend is not None:
                    amend_text = _doc_text(pages, amend["document_id"])
                    eff = date_after(amend_text, EFFECTIVE_RE)
                    ann = date_after(amend_text, ANNOUNCED_RE)
                    identified = _base_identified(base["document_id"], amend["document_id"], pages, names)
                    if identified and eff and not scope_uncertain:
                        if date.fromisoformat(eff) <= today:
                            status, rule, controlling, requires = "RESOLVED_BY_AMENDMENT", "LATER_EFFECTIVE_AMENDMENT", amend["document_id"], False
                            a_status = "ACTIVE"
                        else:
                            status, rule, controlling = "OPEN", "AMENDMENT_NOT_YET_EFFECTIVE", base["document_id"]
                            a_status = "PENDING_EFFECTIVE_DATE"
                    else:
                        status, a_status = "NEEDS_HUMAN_REVIEW", "REVIEW_REQUIRED"
                    amd = (amend, base, eff, ann, a_status)
                elif aa and bb or scope_uncertain:
                    status = "NEEDS_HUMAN_REVIEW"
                cid = "con_" + hashlib.sha1(repr(pair).encode()).hexdigest()[:10]
                ev_a = evidence(page_index[(a["document_id"], a["page"])], a["start"], a["end"], "CONTRADICTS")
                ev_b = evidence(page_index[(b["document_id"], b["page"])], b["start"], b["end"], "CONTRADICTS")
                if amend is not None and status == "RESOLVED_BY_AMENDMENT":
                    (ev_a if amend is a else ev_b)["relation"] = "SUPPORTS"
                contradictions.append({
                    "contradiction_id": cid, "topic": f"{topic} ({unit})",
                    "status": status, "severity": "HIGH" if unit in ("percent", "inr") else "MEDIUM",
                    "explanation": f"{names[a['document_id']]} p.{a['page']} states {a['raw']}; "
                                   f"{names[b['document_id']]} p.{b['page']} states {b['raw']} for the same {topic}.",
                    "evidence": [ev_a, ev_b],
                    "resolution": {"rule": rule, "controlling_document_id": controlling, "effective_from": eff,
                                   "requires_human_review": requires},
                    "detected_at": now, "_doc_ids": [a["document_id"], b["document_id"]]})
                if amd:
                    am, bs, ef, an, st = amd
                    edges.append((bs["document_id"], am["document_id"]))
                    amendments.append({
                        "amendment_id": "amd_" + cid[4:], "base_document_id": bs["document_id"],
                        "amending_document_id": am["document_id"], "topic": f"{topic} ({unit})",
                        "change_summary": f"{topic.capitalize()} changed from {bs['raw']} to {am['raw']}.",
                        "old_value": bs["raw"], "new_value": am["raw"], "announced_on": an, "effective_from": ef,
                        "status": st,
                        "evidence_ids": [(ev_a if bs is a else ev_b)["evidence_id"], (ev_a if am is a else ev_b)["evidence_id"]],
                        "relationship_confidence": None,
                        "requires_human_review": st == "REVIEW_REQUIRED", "_doc_ids": [bs["document_id"], am["document_id"]]})
    contradictions.extend(detect_date_conflicts(pages, now))
    contradictions.extend(detect_rule_conflicts(pages, now))
    _flag_cycles(amendments)
    _annotate_amendment_chains(amendments)
    return {"contradictions": contradictions, "amendments": amendments}


def _annotate_amendment_chains(amendments: List[dict]) -> None:
    """Attach deterministic chain provenance and mark an amendment superseded by its successor.

    Only evidence-backed, non-review edges participate. Upload order is never used.
    """
    by_topic: Dict[str, List[dict]] = {}
    for item in amendments:
        by_topic.setdefault(item["topic"], []).append(item)

    for topic, items in by_topic.items():
        eligible = [x for x in items if x.get("status") in ("ACTIVE", "PENDING_EFFECTIVE_DATE")]
        incoming = {x["amending_document_id"]: x for x in eligible}
        outgoing = {x["base_document_id"]: x for x in eligible}

        for item in eligible:
            predecessor = incoming.get(item["base_document_id"])
            successor = outgoing.get(item["amending_document_id"])
            if (item.get("status") == "ACTIVE" and predecessor and predecessor is not item
                    and predecessor.get("status") == "ACTIVE"):
                predecessor["status"] = "SUPERSEDED"
            item["previous_amendment_id"] = predecessor.get("amendment_id") if predecessor else None
            item["successor_amendment_ids"] = (
                [successor["amendment_id"]] if successor and successor is not item else []
            )

        # Resolve each edge to its earliest evidenced base document. Cycles have already
        # been flagged and are excluded from this traversal.
        for item in eligible:
            root = item["base_document_id"]
            depth = 1
            seen = {item["amending_document_id"]}
            while root in incoming:
                prior = incoming[root]
                candidate = prior["base_document_id"]
                if candidate in seen:
                    break
                seen.add(candidate)
                root = candidate
                depth += 1
            item["root_document_id"] = root
            item["chain_depth"] = depth
            item["chain_id"] = "chain_" + hashlib.sha1(
                f"{topic}|{root}".encode()
            ).hexdigest()[:10]

    # Keep a consistent response shape for review-required edges too.
    for item in amendments:
        item.setdefault("previous_amendment_id", None)
        item.setdefault("successor_amendment_ids", [])
        item.setdefault("root_document_id", item["base_document_id"])
        item.setdefault("chain_depth", 1)
        item.setdefault("chain_id", "chain_" + hashlib.sha1(
            f"{item['topic']}|{item['base_document_id']}".encode()
        ).hexdigest()[:10])


def _flag_cycles(amendments: List[dict]) -> None:
    """Amendment relationships must not form cycles: edges that close one are sent to human review."""
    graph: Dict[str, set] = {}
    for amd in amendments:
        b, a = amd["base_document_id"], amd["amending_document_id"]

        def reaches(src: str, dst: str, seen: set) -> bool:
            if src == dst:
                return True
            seen.add(src)
            return any(reaches(n, dst, seen) for n in graph.get(src, ()) if n not in seen)

        if reaches(a, b, set()):
            amd["status"], amd["requires_human_review"] = "REVIEW_REQUIRED", True
        else:
            graph.setdefault(b, set()).add(a)
