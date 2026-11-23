import pytest

from app.services.docai.text import extract_pages
from app.services.docai.web_source import WebImportError, fetch_public_page


def test_web_import_rejects_unallowlisted_hosts_before_network_access():
    with pytest.raises(WebImportError, match="not allowlisted"):
        fetch_public_page("https://example.com/terms", "")


def test_plain_text_webpage_source_is_indexable(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Source title: Terms\nSource URL: https://example.com/terms\n\nThe processing fee is 1 percent.", encoding="utf-8")
    pages = extract_pages(str(source))
    assert len(pages) == 1
    assert pages[0]["source_type"] == "WEB_TEXT"
    assert "processing fee is 1 percent" in pages[0]["text"]
    assert pages[0]["extraction_metadata"]["extraction_method"] == "WEBPAGE_TEXT"
