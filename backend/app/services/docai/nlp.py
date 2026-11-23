"""Tokenisation, sentence chunking with offsets, and BM25 ranking (no external services)."""
import math
import re
from collections import Counter
from typing import Dict, List

STOP = set("""a an the of to in on at for by with from and or is are was were be been being this that these those
it its as what which who whom whose when where why how do does did shall will would can could may might must
under over any all each per than then there their his her our your i we you he she they not no""".split())
STOP.update("क्या है हैं था थी थे के की का में पर से और या यह वह को कब कहाँ कौन कितना कितनी कितने कृपया बताएं बताइए".split())
_TOKEN = re.compile(r"\w+", re.UNICODE)
_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+(?=[A-Z0-9\u0900-\u097F\u0C80-\u0CFF(\"'])")


def tokens(text: str) -> List[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if t in STOP:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def sentence_spans(text: str, max_chars: int = 500) -> List[tuple]:
    """(start, end) offsets of sentences in `text`; very long sentences are split on ';' / length."""
    spans, start = [], 0
    for m in _SENT_SPLIT.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    final = []
    for s, e in spans:
        while e - s > max_chars:
            cut = text.rfind(" ", s, s + max_chars)
            cut = cut if cut > s else s + max_chars
            final.append((s, cut))
            s = cut + 1
        if e > s:
            final.append((s, e))
    return [(s, e) for s, e in final if text[s:e].strip()]


def bm25_rank(query_terms: List[str], docs: List[List[str]], k1: float = 1.5, b: float = 0.75) -> List[float]:
    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df: Dict[str, int] = Counter()
    for d in docs:
        for t in set(d):
            df[t] += 1
    scores = []
    for d in docs:
        tf = Counter(d)
        score = 0.0
        for t in set(query_terms):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(score)
    return scores
