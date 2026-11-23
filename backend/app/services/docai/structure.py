"""Conservative document-level structure reconstruction.

This module groups page text into traceable sections and joins table fragments only
when adjacent pages expose the same non-empty header. It never invents missing cells.
"""
import re
from typing import Any, Dict, List

_SPACE = re.compile(r"\\s+")
_HEADING = re.compile(
    r"^(?:(?:section|clause|article|schedule|annexure|appendix)\\s+"
    r"[A-Z0-9][A-Z0-9.()/-]*|[0-9]+(?:\\.[0-9]+)*[.)]?\\s+.{2,})$",
    re.IGNORECASE,
)
_CONTINUATION_END = re.compile(r"(?:[-,:;]\\s*|\\b(?:and|or|of|the|to|with|including)\\s*)$", re.I)


def _clean(value: Any) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _lines(page: dict) -> List[str]:
    # Prefer the original page text; layout blocks are metadata and may omit content.
    return [line.strip() for line in str(page.get("text", "")).splitlines() if line.strip()]


def reconstruct_sections(pages: List[dict]) -> List[dict]:
    """Group clauses/paragraphs across pages while retaining exact page fragments.

    The grouping is deliberately conservative: only explicit clause-like headings
    start a new section. Page fragments are never rewritten or used as citations.
    """
    ordered = sorted(pages, key=lambda p: (str(p.get("document_id", "")), int(p.get("page", 0))))
    sections: List[dict] = []
    current = None
    for page in ordered:
        page_no = int(page.get("page", 0))
        doc_id = page.get("document_id")
        filename = page.get("filename")
        raw_text = str(page.get("text", "") or "")
        lines = _lines(page)
        if not lines:
            continue
        page_fragments: List[str] = []
        for line in lines:
            if _HEADING.match(line) and len(line) <= 180:
                if current:
                    sections.append(current)
                current = {
                    "section_id": f"{doc_id or 'document'}:section:{len(sections) + 1}",
                    "heading": line,
                    "text": "",
                    "document_id": doc_id,
                    "filename": filename,
                    "page_numbers": [],
                    "source_spans": [],
                    "reconstruction": "EXPLICIT_HEADING",
                }
            if current is None:
                current = {
                    "section_id": f"{doc_id or 'document'}:section:{len(sections) + 1}",
                    "heading": None,
                    "text": "",
                    "document_id": doc_id,
                    "filename": filename,
                    "page_numbers": [],
                    "source_spans": [],
                    "reconstruction": "PAGE_TEXT_GROUP",
                }
            page_fragments.append(line)
        if current and page_fragments:
            fragment = "\\n".join(page_fragments)
            current["text"] = (current["text"] + "\\n" + fragment).strip()
            if page_no not in current["page_numbers"]:
                current["page_numbers"].append(page_no)
            current["source_spans"].append({
                "document_id": doc_id,
                "filename": filename,
                "page": page_no,
                "quote": fragment,
            })
        # A new page without a heading remains part of the current section. This
        # preserves possible cross-page clauses without asserting semantic linkage.
    if current:
        sections.append(current)
    return sections


def _header_key(row: list) -> tuple:
    return tuple(_clean(cell).casefold() for cell in row)


def reconstruct_tables(pages: List[dict]) -> List[dict]:
    """Join adjacent-page table fragments only when their headers match exactly."""
    ordered = sorted(pages, key=lambda p: (str(p.get("document_id", "")), int(p.get("page", 0))))
    tables: List[dict] = []
    last_by_document: Dict[str, dict] = {}
    for page in ordered:
        doc_id = str(page.get("document_id", ""))
        page_no = int(page.get("page", 0))
        for fragment in page.get("tables", []) or []:
            rows = [[_clean(cell) for cell in row] for row in (fragment.get("rows") or [])]
            rows = [row for row in rows if any(row)]
            if not rows:
                continue
            header = _header_key(rows[0])
            previous = last_by_document.get(doc_id)
            can_join = bool(
                previous
                and header
                and previous["header_key"] == header
                and previous["page_numbers"][-1] == page_no - 1
            )
            if can_join:
                target = previous
                target["rows"].extend(rows[1:] if len(rows) > 1 else [])
                target["page_numbers"].append(page_no)
                target["source_spans"].append({
                    "document_id": page.get("document_id"),
                    "filename": page.get("filename"),
                    "page": page_no,
                    "table_index": fragment.get("table_index"),
                    "bbox": fragment.get("bbox"),
                })
                target["continuation_status"] = "MERGED_EXACT_HEADER"
            else:
                target = {
                    "table_id": f"{doc_id or 'document'}:table:{len(tables) + 1}",
                    "document_id": page.get("document_id"),
                    "filename": page.get("filename"),
                    "header": rows[0],
                    "header_key": header,
                    "rows": rows,
                    "page_numbers": [page_no],
                    "source_spans": [{
                        "document_id": page.get("document_id"),
                        "filename": page.get("filename"),
                        "page": page_no,
                        "table_index": fragment.get("table_index"),
                        "bbox": fragment.get("bbox"),
                    }],
                    "continuation_status": "SINGLE_PAGE_OR_UNMATCHED",
                }
                tables.append(target)
            last_by_document[doc_id] = target
    for table in tables:
        table.pop("header_key", None)
    return tables


def build_document_structure(pages: List[dict]) -> dict:
    """Return a document-level structure manifest with provenance preserved."""
    sections = reconstruct_sections(pages)
    tables = reconstruct_tables(pages)
    return {
        "sections": sections,
        "tables": tables,
        "section_count": len(sections),
        "table_count": len(tables),
        "source_page_count": len({(p.get("document_id"), p.get("page")) for p in pages}),
        "warnings": [
            "SECTION_GROUPING_IS_HEURISTIC",
            "TABLES_JOIN_ONLY_ON_EXACT_ADJACENT_PAGE_HEADER_MATCH",
            "SOURCE_PAGE_QUOTES_REMAIN_AUTHORITATIVE",
        ],
    }
