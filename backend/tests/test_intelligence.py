from app.services.docai.intelligence import extract_entities, search_pages


def test_extracts_document_entities_with_source_provenance():
    page = {
        "document_id": "doc-1",
        "filename": "sale-deed.pdf",
        "page": 1,
        "source_type": "PDF_TEXT",
        "text": "Owner: Rajesh Kumar. Survey No: 123/4. Agreement No: 44/2020. Dated 12/04/2021.",
        "layout_blocks": [],
        "extraction_metadata": {"quality_status": "TEXT_LAYER_PRESENT"},
    }

    result = extract_entities([page])
    kinds = {node["type"] for node in result["nodes"]}

    assert {"DOCUMENT", "OWNER", "PROPERTY_ID", "AGREEMENT_ID", "DATE"} <= kinds
    assert result["fields"]
    assert all(field["document_id"] == "doc-1" and field["page"] == 1 for field in result["fields"])
    assert any(edge["type"] == "MENTIONS" for edge in result["edges"])
    assert any(edge["type"] == "APPEARS_WITH" for edge in result["edges"])


def test_confidence_never_claims_native_pdf_text_is_legally_verified():
    page = {
        "document_id": "doc-2",
        "filename": "record.pdf",
        "page": 1,
        "source_type": "PDF_TEXT",
        "text": "Owner: Rajesh Kumar. Survey No: 123/4.",
        "layout_blocks": [],
        "extraction_metadata": {"quality_status": "TEXT_LAYER_PRESENT"},
    }
    fields = extract_entities([page])["fields"]
    assert fields
    assert all(field["status"] == "NEEDS_REVIEW" for field in fields)
    assert all(field["confidence_basis"].startswith("native PDF") for field in fields)


def test_low_confidence_ocr_is_flagged_for_visual_review():
    page = {
        "document_id": "doc-3",
        "filename": "scan.png",
        "page": 1,
        "source_type": "OCR_TEXT",
        "text": "Owner: Rajesh Kumar",
        "layout_blocks": [{"text": "Owner: Rajesh Kumar", "confidence": 0.42, "bbox": [10, 20, 200, 40]}],
        "extraction_metadata": {"quality_status": "LOW", "ocr_confidence_avg": 0.42},
    }
    review = extract_entities([page])["visual_review"]
    assert len(review) == 1
    assert review[0]["review_candidates"][0]["confidence"] == 0.42


def test_natural_language_search_returns_page_level_source():
    pages = [{
        "document_id": "doc-4", "filename": "deed.pdf", "page": 2,
        "source_type": "PDF_TEXT",
        "text": "Owner Rajesh Kumar is recorded for Survey Number 123/4.",
    }]
    results = search_pages("Rajesh Kumar", pages)
    assert results
    assert results[0]["document_id"] == "doc-4"
    assert results[0]["page"] == 2
    assert "Rajesh" in results[0]["snippet"]
