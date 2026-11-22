import pytest

from app.services.validation.engine import run_validation, _parse_area, _valid_date


def test_parse_area():
    assert _parse_area("2.35 acres") == 2.35
    assert _parse_area("not a number") is None


def test_valid_date():
    assert _valid_date("12-04-2018") is True
    assert _valid_date("garbage") is False


@pytest.mark.asyncio
async def test_required_owner_fail():
    fields = {"owner_name": None, "survey_number": "145/2A", "village": "Rampur", "tehsil": "Dewas", "district": "Dewas"}
    results = await run_validation("rec-1", fields)
    owner_result = [r for r in results if r["rule"] == "required_owner"][0]
    assert owner_result["status"] == "FAIL"


@pytest.mark.asyncio
async def test_area_mismatch_detected():
    fields = {
        "owner_name": "Sunita Devi", "survey_number": "212/1B", "plot_area": "3.10 acres",
        "village": "Kannod", "tehsil": "Kannod", "district": "Dewas",
    }
    results = await run_validation("rec-2", fields, related_area_evidence="2.40 acres")
    mismatch = [r for r in results if r["rule"] == "consistency_area_mismatch"][0]
    assert mismatch["status"] == "WARNING"
    assert "inconsistency" in mismatch["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_survey_detected():
    from app.database import records_collection
    from app import models

    await records_collection.insert_one({
        "_id": "other-record", "document_id": "doc-x", "status": "PENDING_REVIEW",
        "overall_confidence": 90.0, "anomaly_score": 0, "anomaly_level": "LOW", "anomaly_reasons": [],
        "created_at": models.utcnow(), "verified_at": None, "verified_by": None,
        "fields": [{"id": "f1", "field_name": "survey_number", "value": "145/2A", "confidence": 95.0,
                    "ocr_confidence": 95.0, "extraction_confidence": 95.0, "confidence_band": "HIGH",
                    "source_page": 1, "source_bbox": None, "source_text": None, "review_reason": None,
                    "validation_status": "PASS"}],
        "validations": [], "verification_actions": [],
    })

    fields = {"owner_name": "Anil", "survey_number": "145/2A", "village": "Rampur", "tehsil": "Dewas", "district": "Dewas"}
    results = await run_validation("rec-3", fields)
    dup = [r for r in results if r["rule"] == "consistency_duplicate_survey"][0]
    assert dup["status"] == "WARNING"
