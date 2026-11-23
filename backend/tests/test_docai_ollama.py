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


@pytest.mark.parametrize("claim_status", ["PARTIALLY_SUPPORTED", "CONTRADICTED"])
def test_ollama_generates_unverified_draft_for_partial_or_conflicting_evidence(
    monkeypatch, claim_status
):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(settings, "OLLAMA_CHAT_MODEL", "llama3.2")

    claims, evidence = _inputs()
    claims[0]["status"] = claim_status

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "This is an unverified evidence summary."}}

    monkeypatch.setattr(ollama.httpx, "post", lambda *args, **kwargs: Response())

    result = ollama.generate_evidence_draft("What is the rate?", claims, evidence)

    assert result["status"] == "DRAFT_UNVERIFIED"
    assert result["draft"] is not None
    assert "unverified" in result["notice"].lower()


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



def test_ollama_hindi_mode_requests_hindi_without_translating_source_quotes(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(settings, "OLLAMA_CHAT_MODEL", "llama3.2")
    claims, evidence = _inputs()
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "दस्तावेज़ के अनुसार दर 8% है [policy.pdf, p.4]."}}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    result = ollama.generate_evidence_draft("ब्याज दर क्या है?", claims, evidence, "hi")
    system_prompt = captured["json"]["messages"][0]["content"]
    assert "natural Hindi" in system_prompt
    assert "Do not translate or alter quoted source text" in system_prompt
    assert result["status"] == "DRAFT_UNVERIFIED"
