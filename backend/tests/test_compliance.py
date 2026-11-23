import pytest

from app.database import (
    documents_collection, docai_pages_collection,
    compliance_checklists_collection, compliance_rules_collection,
    compliance_reviews_collection, compliance_events_collection,
)
from app.routers.compliance import (
    ChecklistCreate, RequirementInput, VersionCompareRequest, RuleCreate,
    RuleRunRequest, ReviewCreate, EvidenceInput, ReviewUpdate,
    create_checklist, compare_versions, create_rule, run_rule,
    create_review, update_review, review_history,
)


USER = {"_id": "reviewer-1", "role": "ADMIN", "username": "reviewer"}


async def seed_document(document_id: str, filename: str, text: str, page: int = 1):
    await documents_collection.insert_one({
        "_id": document_id, "filename": filename, "docai_status": "INDEXED",
        "uploaded_by": USER["_id"],
    })
    await docai_pages_collection.insert_one({
        "document_id": document_id, "filename": filename, "page": page,
        "text": text, "source_type": "PDF_TEXT",
    })


@pytest.mark.asyncio
async def test_checklist_reports_found_partial_and_missing_with_page_evidence():
    await seed_document("doc-a", "agreement.pdf", "Signed service agreement. Identity proof received.")
    result = await create_checklist(ChecklistCreate(
        name="Intake checklist",
        document_ids=["doc-a"],
        requirements=[
            RequirementInput(label="Signed agreement", keywords=["signed service agreement"]),
            RequirementInput(label="Identity card", keywords=["identity proof card"]),
            RequirementInput(label="Payment receipt", keywords=["payment receipt"]),
        ],
    ), USER)

    statuses = {item["label"]: item["status"] for item in result["requirements"]}
    assert statuses == {
        "Signed agreement": "FOUND",
        "Identity card": "NEEDS_VERIFICATION",
        "Payment receipt": "MISSING",
    }
    found = next(x for x in result["requirements"] if x["label"] == "Signed agreement")
    assert found["evidence"][0]["document_id"] == "doc-a"
    assert found["evidence"][0]["page"] == 1
    assert await compliance_checklists_collection.count_documents({"user_id": USER["_id"]}) == 1


@pytest.mark.asyncio
async def test_version_comparison_returns_page_level_added_removed_and_modified_text():
    await seed_document("old", "agreement-v1.pdf", "Owner: Alex\nArea: 10 acres\nTerm: 5 years", 1)
    await seed_document("new", "agreement-v2.pdf", "Owner: Alex\nArea: 12 acres\nTerm: 5 years\nSigned by both parties", 2)

    result = await compare_versions(VersionCompareRequest(
        old_document_id="old", new_document_id="new"
    ), USER)

    assert result["summary"]["modified"] == 1
    assert result["summary"]["added"] == 1
    assert result["summary"]["removed"] == 0
    assert result["modified"][0]["old"]["page"] == 1
    assert result["modified"][0]["new"]["page"] == 2
    assert "10 acres" in result["modified"][0]["old"]["quote"]
    assert "12 acres" in result["modified"][0]["new"]["quote"]


@pytest.mark.asyncio
async def test_custom_rule_failure_creates_pending_human_review():
    await seed_document("doc-rule", "contract.pdf", "Signed service contract with two parties.")
    rule = await create_rule(RuleCreate(
        name="Registration reference required",
        operator="contains",
        expected_value="registration number",
        severity="HIGH",
    ), USER)

    result = await run_rule(rule["_id"], RuleRunRequest(document_ids=["doc-rule"]), USER)
    assert result["summary"] == {"total": 1, "passed": 0, "failed": 1}
    review = await compliance_reviews_collection.find_one({"source_id": rule["_id"]})
    assert review is not None
    assert review["status"] == "PENDING"


@pytest.mark.asyncio
async def test_human_review_decisions_append_audit_history():
    await seed_document("doc-review", "deed.pdf", "Owner: Alex. Survey number 88/2.")
    review = await create_review(ReviewCreate(
        title="Confirm owner name",
        description="Check the extracted owner against the original source.",
        source_type="MANUAL",
        document_ids=["doc-review"],
        evidence=[EvidenceInput(
            document_id="doc-review", filename="deed.pdf", page=1,
            quote="Owner: Alex."
        )],
    ), USER)

    updated = await update_review(review["_id"], ReviewUpdate(
        action="CORRECT", comment="Compared with the signed original.",
        corrected_value="Alexander Smith",
    ), USER)
    history = await review_history(review["_id"], USER)

    assert updated["status"] == "CORRECTED"
    assert len(history["history"]) == 1
    assert history["history"][0]["corrected_value"] == "Alexander Smith"
    assert await compliance_events_collection.count_documents({"review_id": review["_id"]}) == 1
