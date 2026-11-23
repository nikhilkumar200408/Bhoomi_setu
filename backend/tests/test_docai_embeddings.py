import httpx
import pytest

from app.config import settings
from app.services.docai import embeddings


def test_embed_texts_calls_local_ollama(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test/")
    monkeypatch.setattr(settings, "OLLAMA_EMBEDDING_MODEL", "bge-m3")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    result = embeddings.embed_texts(["loan interest", "insurance premium"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "http://ollama.test/api/embed"
    assert captured["json"]["model"] == "bge-m3"
    assert captured["json"]["input"] == ["loan interest", "insurance premium"]


def test_embed_texts_is_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_EMBEDDINGS_ENABLED", False)
    with pytest.raises(embeddings.EmbeddingError, match="disabled"):
        embeddings.embed_texts(["a clause"])


def test_embed_texts_rejects_invalid_vectors(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_EMBEDDINGS_ENABLED", True)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.1, float("nan")]]}

    monkeypatch.setattr(embeddings.httpx, "post", lambda *a, **k: Response())
    with pytest.raises(embeddings.EmbeddingError, match="non-finite"):
        embeddings.embed_texts(["a clause"])


def test_cosine_similarity_handles_direction_and_zero_vectors():
    assert embeddings.cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert embeddings.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert embeddings.cosine_similarity([0, 0], [1, 0]) == 0.0
    assert embeddings.cosine_similarity([1], [1, 2]) == 0.0


def test_reciprocal_rank_fusion_combines_keyword_and_vector_rankings():
    scores = embeddings.reciprocal_rank_fusion([
        ["exact-match", "semantic-match"],
        ["semantic-match", "meaning-match"],
    ])
    assert scores["semantic-match"] > scores["exact-match"]
    assert scores["semantic-match"] > scores["meaning-match"]
