"""Local BGE-M3 embeddings and scale-safe hybrid ranking primitives.

Embeddings are optional and local-only. Source text and page citations remain the
authoritative evidence; vectors are used only to retrieve candidate passages.
"""
import math
from typing import Iterable

import httpx

from ...config import settings


class EmbeddingError(RuntimeError):
    """Raised when local embedding inference returns unusable output."""


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch using Ollama's /api/embed endpoint."""
    if not settings.OLLAMA_EMBEDDINGS_ENABLED:
        raise EmbeddingError("Local embeddings are disabled.")
    cleaned = [str(text).strip() for text in texts]
    if not cleaned or any(not text for text in cleaned):
        raise EmbeddingError("Embedding input must contain non-empty text.")
    url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/embed"
    try:
        response = httpx.post(
            url,
            json={"model": settings.OLLAMA_EMBEDDING_MODEL, "input": cleaned},
            timeout=settings.OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        vectors = response.json().get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(cleaned):
            raise EmbeddingError("Embedding response count does not match input.")
        normalized = []
        dimension = None
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError("Embedding response contains an invalid vector.")
            values = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in values):
                raise EmbeddingError("Embedding response contains a non-finite value.")
            if dimension is None:
                dimension = len(values)
            elif len(values) != dimension:
                raise EmbeddingError("Embedding dimensions are inconsistent.")
            normalized.append(values)
        return normalized
    except EmbeddingError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise EmbeddingError("Local embedding inference failed.") from exc


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity, or zero for empty/zero-norm/incompatible vectors."""
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(a) ** 2 for a in left))
    right_norm = math.sqrt(sum(float(b) ** 2 for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def reciprocal_rank_fusion(rankings: Iterable[Iterable[str]], k: int = 60) -> dict[str, float]:
    """Fuse independent ranked result lists without comparing incompatible score scales."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen = set()
        for rank, key in enumerate(ranking, start=1):
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores
