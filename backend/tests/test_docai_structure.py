from app.services.docai.structure import build_document_structure, reconstruct_sections, reconstruct_tables


def test_section_continues_across_pages_and_keeps_exact_page_spans():
    pages = [
        {"document_id": "d1", "filename": "agreement.pdf", "page": 1,
         "text": "Clause 7: Payment obligations\nThe borrower shall pay each instalment"},
        {"document_id": "d1", "filename": "agreement.pdf", "page": 2,
         "text": "within thirty days of the due date. Late charges may apply."},
    ]

    sections = reconstruct_sections(pages)

    assert len(sections) == 1
    assert sections[0]["heading"] == "Clause 7: Payment obligations"
    assert sections[0]["page_numbers"] == [1, 2]
    assert [span["page"] for span in sections[0]["source_spans"]] == [1, 2]
    assert "within thirty days" in sections[0]["source_spans"][1]["quote"]


def test_sections_never_merge_across_documents():
    pages = [
        {"document_id": "a", "filename": "a.pdf", "page": 1, "text": "Clause 1: Scope\nAlpha applies."},
        {"document_id": "b", "filename": "b.pdf", "page": 1, "text": "Clause 1: Scope\nBeta applies."},
    ]

    sections = reconstruct_sections(pages)

    assert len(sections) == 2
    assert sections[0]["document_id"] == "a"
    assert sections[1]["document_id"] == "b"


def test_adjacent_tables_merge_only_when_headers_match_exactly():
    pages = [
        {"document_id": "d1", "filename": "fees.pdf", "page": 1, "tables": [
            {"table_index": 0, "rows": [["Fee", "Rate"], ["Processing", "1.0%"]]}
        ]},
        {"document_id": "d1", "filename": "fees.pdf", "page": 2, "tables": [
            {"table_index": 0, "rows": [["Fee", "Rate"], ["Late charge", "1.5%"]]}
        ]},
    ]

    tables = reconstruct_tables(pages)

    assert len(tables) == 1
    assert tables[0]["page_numbers"] == [1, 2]
    assert tables[0]["rows"] == [
        ["Fee", "Rate"], ["Processing", "1.0%"], ["Late charge", "1.5%"]
    ]
    assert tables[0]["continuation_status"] == "MERGED_EXACT_HEADER"
    assert [span["page"] for span in tables[0]["source_spans"]] == [1, 2]


def test_table_fragments_with_different_headers_are_not_merged():
    pages = [
        {"document_id": "d1", "page": 1, "tables": [
            {"rows": [["Fee", "Rate"], ["Processing", "1.0%"]]}
        ]},
        {"document_id": "d1", "page": 2, "tables": [
            {"rows": [["Condition", "Value"], ["Tenure", "5 years"]]}
        ]},
    ]

    tables = reconstruct_tables(pages)

    assert len(tables) == 2
    assert tables[0]["page_numbers"] == [1]
    assert tables[1]["page_numbers"] == [2]


def test_structure_manifest_reports_heuristics_and_provenance():
    manifest = build_document_structure([
        {"document_id": "d1", "filename": "x.pdf", "page": 1,
         "text": "Clause 2: Eligibility\nMinimum age is 21."}
    ])

    assert manifest["section_count"] == 1
    assert manifest["source_page_count"] == 1
    assert "SECTION_GROUPING_IS_HEURISTIC" in manifest["warnings"]
