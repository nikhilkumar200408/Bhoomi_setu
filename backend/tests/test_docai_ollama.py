import httpx
import pytest

from app.config import settings
from app.services.docai import ollama


def _inputs():
    claims = [{"status": "SUPPORTED", "text": "The annual rate is 8%."}]
    evidence = [{
        "evidence_id": "ev_1",
        "filename": "policy.pdf",
        "page_number": 4,
        "quote": "The annual interest rate is eight percent.",
    }]
    return claims, evidence


def test_ollama_is_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    claims, evidence = _inputs()
    result = ollama.generate_evidence_draft("What is the rate?", claims, evidence)
    assert result == {"status": "DISABLED", "draft": None, "model": None}


def test_ollama_skips_partial_or_review_required_claims(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    claims, evidence = _inputs()
    claims[0]["status"] = "PARTIALLY_SUPPORTED"
    result = ollama.generate_evidence_draft("What is the rate?", claims, evidence)
    assert result["status"] == "SKIPPED_REVIEW_REQUIRED"
    assert result["draft"] is None


def test_ollama_returns_unverified_draft_without_replacing_evidence(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(settings, "OLLAMA_CHAT_MODEL", "llama3.2")
    claims, evidence = _inputs()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "The annual rate is eight percent [policy.pdf, p.4]."}}

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    result = ollama.generate_evidence_draft("What is the rate?", claims, evidence)

    assert result["status"] == "DRAFT_UNVERIFIED"
    assert result["model"] == "llama3.2"
    assert "unverified" in result["notice"].lower()
    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["json"]["model"] == "llama3.2"
    assert captured["json"]["options"]["temperature"] == 0


def test_ollama_failure_is_normalized(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    claims, evidence = _inputs()

    def fail(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(ollama.httpx, "post", fail)
    with pytest.raises(ollama.OllamaError, match="Local Ollama inference failed"):
        ollama.generate_evidence_draft("What is the rate?", claims, evidence)
