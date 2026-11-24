import fitz

from app.services.docai import text as extraction


def make_pdf(*page_texts):
    pdf = fitz.open()
    for page_text in page_texts:
        page = pdf.new_page()
        page.insert_textbox(fitz.Rect(45, 45, 550, 780), page_text, fontsize=11)
    return pdf.tobytes()


def test_native_pdf_text_keeps_legacy_fields_and_adds_layout_metadata(tmp_path):
    path = tmp_path / "agreement.pdf"
    path.write_bytes(make_pdf(
        "LOAN AGREEMENT\nClause 4: Interest shall be eight percent per annum. "
        "Repayment shall occur within five years."
    ))

    pages = extraction.extract_pages(str(path))

    assert len(pages) == 1
    page = pages[0]
    assert page["page"] == 1
    assert page["source_type"] == "PDF_TEXT"
    assert "eight percent" in page["text"]
    assert page["layout_blocks"]
    assert page["layout_blocks"][0]["bbox"]
    assert page["extraction_metadata"]["quality_status"] == "TEXT_LAYER_PRESENT"
    assert page["extraction_metadata"]["text_word_count"] > 5
    assert "tables" in page and "table_detection_status" in page["extraction_metadata"]


def test_low_text_pdf_page_uses_ocr_and_preserves_page_number(tmp_path, monkeypatch):
    path = tmp_path / "scanned.pdf"
    path.write_bytes(make_pdf(""))

    def fake_ocr(_path, page_number=1, coordinate_scale=1.0):
        assert coordinate_scale > 1
        return {
            "text": "Policy holder must pay the premium.",
            "layout_blocks": [{
                "text": "Policy holder must pay the premium.",
                "bbox": [10.0, 20.0, 200.0, 40.0],
                "confidence": 0.91,
                "block_type": "OCR_LINE",
            }],
            "ocr_confidence_avg": 0.91,
        }

    monkeypatch.setattr(extraction, "_ocr_image_details", fake_ocr)
    pages = extraction.extract_pages(str(path))

    assert pages[0]["source_type"] == "OCR_TEXT"
    assert pages[0]["page"] == 1
    assert "premium" in pages[0]["text"]
    assert pages[0]["extraction_metadata"]["quality_status"] == "HIGH"
    assert "OCR_TEXT_REQUIRES_SOURCE_REVIEW" in pages[0]["extraction_metadata"]["warnings"]


def test_multi_page_pdf_keeps_independent_page_provenance(tmp_path):
    path = tmp_path / "multi.pdf"
    path.write_bytes(make_pdf(
        "Page one. This agreement identifies the borrower and lender.",
        "Page two. The interest rate is eight percent per annum.",
    ))

    pages = extraction.extract_pages(str(path))

    assert [page["page"] for page in pages] == [1, 2]
    assert all(page["source_type"] == "PDF_TEXT" for page in pages)
    assert "borrower" in pages[0]["text"]
    assert "interest rate" in pages[1]["text"]
    assert all(page["extraction_metadata"]["page_width_pt"] > 0 for page in pages)
