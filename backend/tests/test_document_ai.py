import os

import fitz
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app import models
from app.auth import hash_password
from app.database import users_collection
from app.main import app
from app.services.docai import facts as F
from app.services.docai import qa
from app.services.docai.calculations import calculate_financial_value

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
USERS = [("op_a", "Operator@123", "DATA_ENTRY_OPERATOR"), ("op_b", "Operator@123", "DATA_ENTRY_OPERATOR"),
         ("officer", "Officer@123", "REVENUE_OFFICER"), ("admin", "Admin@123", "ADMIN")]

BASE = ("Loan Agreement. Under Clause 4, interest shall be eight percent per annum on the principal. "
        "The borrower shall repay within five years.")
AMEND = ("Amendment notice dated 15 December 2025. This amends the Loan Agreement. "
         "Under Clause 4 of the Loan Agreement, the revised interest shall be ten percent per annum. "
         "This amendment is effective from 1 January 2026.")


def make_pdf(*page_texts: str) -> bytes:
    pdf = fitz.open()
    for t in page_texts:
        pg = pdf.new_page()
        pg.insert_textbox(fitz.Rect(50, 50, 545, 790), t, fontsize=11)
    return pdf.tobytes()


@pytest_asyncio.fixture(autouse=True)
async def _users():
    for name, pw, role in USERS:
        await users_collection.insert_one({"_id": models.gen_uuid(), "username": name, "full_name": name,
                                           "hashed_password": hash_password(pw), "role": role, "created_at": models.utcnow()})


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def hdr(client, name):
    pw = next(p for n, p, _ in USERS if n == name)
    r = await client.post("/api/auth/login", json={"username": name, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def upload_pdf(client, h, filename, *pages):
    r = await client.post("/api/documents/upload", files={"file": (filename, make_pdf(*pages), "application/pdf")}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def index(client, h, doc_id):
    r = await client.post(f"/api/document-ai/documents/{doc_id}/index", headers=h)
    assert r.status_code == 202, r.text
    job = await client.get(f"/api/document-ai/indexing-jobs/{r.json()['indexing_job_id']}", headers=h)
    assert job.json()["status"] == "COMPLETED", job.json()
    return job.json()


async def ask(client, h, question, ids, **kw):
    return await client.post("/api/document-ai/qa/ask", json={"question": question, "document_ids": ids, **kw}, headers=h)


# ------------------------------------------------------------------ ownership (security)
@pytest.mark.asyncio
async def test_documents_records_audit_are_isolated_between_operators(client):
    a, b, officer = await hdr(client, "op_a"), await hdr(client, "op_b"), await hdr(client, "officer")
    with open(os.path.join(SAMPLE_DIR, "english_land_record.png"), "rb") as f:
        r = await client.post("/api/documents/upload", files={"file": ("x.png", f, "image/png")}, headers=a)
    doc_id = r.json()["id"]
    rec = await client.post(f"/api/documents/{doc_id}/process", headers=a)
    assert rec.status_code == 200, rec.text
    rec_id = rec.json()["id"]

    assert (await client.get("/api/documents", headers=b)).json() == []
    for path in (f"/api/documents/{doc_id}", f"/api/documents/{doc_id}/file", f"/api/records/{rec_id}",
                 f"/api/records/{rec_id}/audit"):
        assert (await client.get(path, headers=b)).status_code == 404, path
    assert (await client.post(f"/api/documents/{doc_id}/process", headers=b)).status_code == 404
    assert (await client.patch(f"/api/records/{rec_id}/fields/owner_name", json={"new_value": "Hacked", "reason": "x"}, headers=b)).status_code == 404
    assert (await client.get("/api/records", headers=b)).json() == []
    assert (await client.get("/api/audit", headers=b)).json() == []
    assert (await client.get("/api/search", params={"q": "a"}, headers=b)).json() == []
    assert (await client.get("/api/dashboard/stats", headers=b)).json()["records_extracted"] == 0
    # owner and reviewer roles keep access
    assert (await client.get(f"/api/records/{rec_id}", headers=a)).status_code == 200
    assert (await client.get(f"/api/records/{rec_id}", headers=officer)).status_code == 200
    assert len((await client.get("/api/documents", headers=officer)).json()) == 1


@pytest.mark.asyncio
async def test_document_ai_rejects_foreign_documents_and_roles(client):
    a, b = await hdr(client, "op_a"), await hdr(client, "op_b")
    doc = await upload_pdf(client, a, "loan_agreement.pdf", BASE)
    assert (await client.post(f"/api/document-ai/documents/{doc}/index", headers=b)).status_code == 404
    await index(client, a, doc)
    r = await ask(client, b, "interest rate", [doc])
    assert r.status_code == 404 and r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert (await client.get(f"/api/document-ai/contradictions?document_ids={doc}", headers=b)).status_code == 404
    ans = (await ask(client, a, "interest rate", [doc])).json()
    assert (await client.get(f"/api/document-ai/answers/{ans['answer_id']}", headers=b)).status_code == 404
    assert (await client.get(f"/api/document-ai/answers/{ans['answer_id']}")).status_code == 401


# ------------------------------------------------------------------ indexing / QA / citations
@pytest.mark.asyncio
async def test_index_ask_cites_real_pages_and_every_quote_is_on_the_page(client):
    a = await hdr(client, "op_a")
    d1 = await upload_pdf(client, a, "loan_agreement.pdf", "Cover page. Parties are listed here.", BASE)
    job = await index(client, a, d1)
    assert job["pages_total"] == 2 and job["chunks_created"] > 0
    again = await client.post(f"/api/document-ai/documents/{d1}/index", headers=a)
    assert again.status_code == 202 and again.json()["indexing_job_id"] == job["job_id"]  # idempotent

    r = await ask(client, a, "What is the interest rate per annum?", [d1])
    body = r.json()
    assert r.status_code == 200 and not body["abstained"]
    assert body["faithfulness_method"] == "verified_claim_ratio"
    ev = {e["evidence_id"]: e for e in body["evidence"]}
    claim = body["claims"][0]
    e = ev[claim["evidence_ids"][0]]
    assert e["page_number"] == 2 and e["filename"] == "loan_agreement.pdf"  # page 2, not page 1
    assert "eight percent" in e["quote"] and e["verification"]["quote_found_in_source"]
    pdf = fitz.open(stream=make_pdf("Cover page. Parties are listed here.", BASE), filetype="pdf")
    assert e["quote"] in " ".join(pdf[e["page_number"] - 1].get_text().split())  # real PDF page text

    ver = await client.post(f"/api/document-ai/answers/{body['answer_id']}/verify", headers=a)
    assert ver.status_code == 200 and ver.json()["invalid_citation_count"] == 0
    assert (await client.get(f"/api/document-ai/answers/{body['answer_id']}", headers=a)).json()["answer_id"] == body["answer_id"]


@pytest.mark.asyncio
async def test_abstains_when_evidence_is_missing_and_validates_input(client):
    a = await hdr(client, "op_a")
    doc = await upload_pdf(client, a, "loan_agreement.pdf", BASE)
    unindexed = await upload_pdf(client, a, "other.pdf", "Some other text about land.")
    await index(client, a, doc)
    body = (await ask(client, a, "What is the vehicle registration penalty?", [doc])).json()
    assert body["abstained"] and body["claims"] == [] and body["evidence"] == [] and body["missing_evidence"]
    assert (await ask(client, a, "   ", [doc])).status_code == 400
    assert (await ask(client, a, "interest", [unindexed])).status_code == 409
    assert (await client.post("/api/document-ai/qa/ask", json={"question": "x", "document_ids": []}, headers=a)).status_code == 422


# ------------------------------------------------------------------ contradictions / amendments
@pytest.mark.asyncio
async def test_amendment_resolves_conflict_only_with_base_reference_and_effective_date(client):
    a = await hdr(client, "op_a")
    base = await upload_pdf(client, a, "loan_agreement.pdf", BASE)
    amend = await upload_pdf(client, a, "amendment_1.pdf", AMEND)
    await index(client, a, base)
    await index(client, a, amend)
    ids = f"{base},{amend}"
    items = (await client.get(f"/api/document-ai/contradictions?document_ids={ids}", headers=a)).json()["items"]
    assert len(items) == 1
    con = items[0]
    assert con["status"] == "RESOLVED_BY_AMENDMENT" and con["resolution"]["controlling_document_id"] == amend
    assert con["resolution"]["effective_from"] == "2026-01-01"
    assert {e["document_id"] for e in con["evidence"]} == {base, amend}
    assert all(e["verification"]["page_verified"] for e in con["evidence"])

    amds = (await client.get(f"/api/document-ai/amendments?document_ids={ids}", headers=a)).json()["items"]
    assert amds[0]["status"] == "ACTIVE" and amds[0]["old_value"].startswith("eight") and amds[0]["new_value"].startswith("ten")
    assert amds[0]["announced_on"] == "2025-12-15" and amds[0]["effective_from"] == "2026-01-01"
    detail = await client.get(f"/api/document-ai/amendments/{amds[0]['amendment_id']}", headers=a)
    assert detail.status_code == 200 and detail.json()["base_document"]["filename"] == "loan_agreement.pdf"

    body = (await ask(client, a, "What is the interest per annum?", [base, amend])).json()
    by_doc = {next(e for e in body["evidence"] if e["evidence_id"] == c["evidence_ids"][0])["document_id"]: c for c in body["claims"]}
    assert by_doc[amend]["status"] == "SUPPORTED" and by_doc[base]["status"] == "CONTRADICTED"  # superseded text is qualified
    only_current = (await ask(client, a, "What is the interest per annum?", [base, amend], include_superseded_documents=False)).json()
    assert all(e["document_id"] == amend for e in only_current["evidence"])


@pytest.mark.asyncio
async def test_conflict_without_amendment_evidence_goes_to_review_not_resolved(client):
    a = await hdr(client, "op_a")
    d1 = await upload_pdf(client, a, "deed_one.pdf", "The interest on the loan is eight percent per annum.")
    d2 = await upload_pdf(client, a, "deed_two.pdf", "The interest on the loan is twelve percent per annum.")  # newer upload, no amendment language
    d3 = await upload_pdf(client, a, "amend_no_date.pdf", "Amendment. The revised interest on the loan is twelve percent per annum.")
    for d in (d1, d2, d3):
        await index(client, a, d)
    s1 = (await client.get(f"/api/document-ai/contradictions?document_ids={d1},{d2}", headers=a)).json()["items"]
    assert s1[0]["status"] == "OPEN" and s1[0]["resolution"]["controlling_document_id"] is None  # upload order never wins
    s2 = (await client.get(f"/api/document-ai/contradictions?document_ids={d1},{d3}", headers=a)).json()["items"]
    assert s2[0]["status"] == "NEEDS_HUMAN_REVIEW" and s2[0]["resolution"]["requires_human_review"]
    amds = (await client.get(f"/api/document-ai/amendments?document_ids={d1},{d3}", headers=a)).json()["items"]
    assert amds[0]["status"] == "REVIEW_REQUIRED" and amds[0]["requires_human_review"]


def test_different_plots_are_not_contradictions():
    pages = [{"document_id": "1", "filename": "a.pdf", "page": 1, "source_type": "PDF_TEXT", "text": "The area of Plot 12 is 5 acres."},
             {"document_id": "2", "filename": "b.pdf", "page": 1, "source_type": "PDF_TEXT", "text": "The area of Plot 99 is 7 acres."}]
    assert F.analyse(pages)["contradictions"] == []


def test_amendment_chain_marks_prior_version_superseded_and_tracks_root():
    amendments = [
        {"amendment_id": "amd_ab", "base_document_id": "A", "amending_document_id": "B",
         "topic": "interest (percent)", "status": "ACTIVE", "requires_human_review": False},
        {"amendment_id": "amd_bc", "base_document_id": "B", "amending_document_id": "C",
         "topic": "interest (percent)", "status": "ACTIVE", "requires_human_review": False},
    ]
    F._flag_cycles(amendments)
    F._annotate_amendment_chains(amendments)

    first, second = amendments
    assert first["status"] == "SUPERSEDED"
    assert second["status"] == "ACTIVE"
    assert first["chain_id"] == second["chain_id"]
    assert second["root_document_id"] == "A" and second["chain_depth"] == 2
    assert second["previous_amendment_id"] == "amd_ab"
    assert first["successor_amendment_ids"] == ["amd_bc"]


def test_amendment_cycles_are_flagged():
    amds = [{"base_document_id": "A", "amending_document_id": "B", "status": "ACTIVE", "requires_human_review": False},
            {"base_document_id": "B", "amending_document_id": "A", "status": "ACTIVE", "requires_human_review": False}]
    F._flag_cycles(amds)
    assert amds[0]["status"] == "ACTIVE" and amds[1]["status"] == "REVIEW_REQUIRED"


# ------------------------------------------------------------------ scoring / quote checks / review
def test_faithfulness_uses_verified_source_quotes_not_retrieval_status():
    claims = [
        {"status": "SUPPORTED", "text": "The annual rate is 8%.", "evidence_ids": ["ev1"]},
        {"status": "PARTIALLY_SUPPORTED", "text": "The principal is INR 100,000.", "evidence_ids": ["ev2"]},
        {"status": "CONTRADICTED", "text": "The fee is 2%.", "evidence_ids": ["ev3"]},
        {"status": "INSUFFICIENT_EVIDENCE", "text": "Unsupported claim", "evidence_ids": ["ev4"]},
    ]
    evidence = [
        {"evidence_id": "ev1", "quote": "The annual rate is 8%.", "verification": {"quote_found_in_source": True}},
        {"evidence_id": "ev2", "quote": "The principal is INR 100,000.", "verification": {"quote_found_in_source": True}},
        {"evidence_id": "ev3", "quote": "The fee is 2%.", "verification": {"quote_found_in_source": True}},
        {"evidence_id": "ev4", "quote": "Different source text.", "verification": {"quote_found_in_source": True}},
    ]
    assert qa.faithfulness(claims, evidence) == 0.75
    evidence[1]["verification"]["quote_found_in_source"] = False
    assert qa.faithfulness(claims, evidence) == 0.5
    assert qa.faithfulness([], evidence) is None
    assert F.verify_quote("a b c", "a  b") == (0, 3) and F.verify_quote("abc", "abd") is None


@pytest.mark.asyncio
async def test_human_review_requires_officer_reason_and_keeps_evidence(client):
    a, officer = await hdr(client, "op_a"), await hdr(client, "officer")
    doc = await upload_pdf(client, a, "loan_agreement.pdf", BASE)
    await index(client, a, doc)
    body = (await ask(client, a, "interest rate", [doc])).json()
    cid = body["claims"][0]["claim_id"]
    url = f"/api/document-ai/claims/{cid}/review"
    assert (await client.post(url, json={"decision": "ACCEPT"}, headers=a)).status_code == 403
    assert (await client.post(url, json={"decision": "MARK_UNRESOLVED"}, headers=officer)).status_code == 400
    assert (await client.post(url, json={"decision": "BOGUS"}, headers=officer)).status_code == 400
    ok = await client.post(url, json={"decision": "MARK_UNRESOLVED", "reason": "scan unclear"}, headers=officer)
    assert ok.status_code == 200 and ok.json()["review_status"] == "MARK_UNRESOLVED"
    after = (await client.get(f"/api/document-ai/answers/{body['answer_id']}", headers=officer)).json()
    assert after["evidence"] == body["evidence"] and after["claims"][0]["review"]["reason"] == "scan unclear"
    assert (await client.get("/api/audit?action=DOCAI_CLAIM_REVIEW", headers=officer)).json()


@pytest.mark.asyncio
async def test_invalid_upload_and_pagination_errors(client):
    a = await hdr(client, "op_a")
    r = await client.post("/api/documents/upload", files={"file": ("evil.exe", b"MZ", "application/octet-stream")}, headers=a)
    assert r.status_code == 400
    doc = await upload_pdf(client, a, "loan_agreement.pdf", BASE)
    await index(client, a, doc)
    assert (await client.get(f"/api/document-ai/contradictions?document_ids={doc}&limit=0", headers=a)).status_code == 400
    assert (await client.get(f"/api/document-ai/contradictions?document_ids={doc}&status=BAD", headers=a)).status_code == 400
    assert (await client.get("/api/document-ai/contradictions", headers=a)).status_code == 422


def test_semantic_only_retrieval_is_never_auto_supported():
    page = {
        "document_id": "doc-semantic",
        "filename": "loan_terms.pdf",
        "page": 3,
        "source_type": "PDF_TEXT",
        "text": "Interest is charged at eight percent per annum.",
    }
    chunk = qa.build_chunks([page])[0]
    key = (page["document_id"], page["page"], chunk["start"], chunk["end"])
    result = qa.answer_question(
        "interest rate amount percentage",
        [page],
        ["doc-semantic"],
        vector_scores={key: 0.91},
    )
    assert result["retrieval_mode"] == "HYBRID_BM25_VECTOR"
    assert not result["abstained"]
    assert result["claims"][0]["status"] == "PARTIALLY_SUPPORTED"
    assert result["claims"][0]["requires_human_review"] is True
    assert result["evidence"][0]["page_number"] == 3
    assert result["evidence"][0]["verification"]["quote_found_in_source"] is True



def test_labelled_due_date_conflict_has_verbatim_evidence_and_no_guessed_winner():
    pages = [
        {"document_id": "loan-a", "filename": "loan_a.pdf", "page": 2, "source_type": "PDF_TEXT",
         "text": "The payment due date is 1 March 2026."},
        {"document_id": "loan-b", "filename": "loan_b.pdf", "page": 4, "source_type": "PDF_TEXT",
         "text": "The payment due date is 15 March 2026."},
    ]
    result = F.analyse(pages, today=F.date(2026, 2, 1))
    conflicts = [x for x in result["contradictions"] if x["topic"] == "due date"]
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["status"] == "OPEN"
    assert conflict["resolution"]["controlling_document_id"] is None
    assert conflict["resolution"]["requires_human_review"] is True
    assert {e["document_id"] for e in conflict["evidence"]} == {"loan-a", "loan-b"}
    assert all(e["verification"]["quote_found_in_source"] for e in conflict["evidence"])
    assert "1 March 2026" in conflict["evidence"][0]["quote"] or "1 March 2026" in conflict["evidence"][1]["quote"]


def test_labelled_date_conflicts_do_not_compare_different_clauses():
    pages = [
        {"document_id": "contract-a", "filename": "contract_a.pdf", "page": 1, "source_type": "PDF_TEXT",
         "text": "Under Clause 4, the payment due date is 1 March 2026."},
        {"document_id": "contract-b", "filename": "contract_b.pdf", "page": 1, "source_type": "PDF_TEXT",
         "text": "Under Clause 9, the payment due date is 15 March 2026."},
    ]
    result = F.analyse(pages, today=F.date(2026, 2, 1))
    assert not [x for x in result["contradictions"] if x["topic"] == "due date"]


def test_eligibility_age_threshold_conflict_is_flagged_with_both_quotes():
    pages = [
        {"document_id": "policy-a", "filename": "policy_a.pdf", "page": 2, "source_type": "PDF_TEXT",
         "text": "Applicants must meet a minimum age of 21 years."},
        {"document_id": "policy-b", "filename": "policy_b.pdf", "page": 3, "source_type": "PDF_TEXT",
         "text": "The minimum age is 18 years."},
    ]
    result = F.analyse(pages)
    conflicts = [x for x in result["contradictions"] if x["topic"] == "minimum age"]
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["status"] == "OPEN"
    assert conflict["resolution"]["controlling_document_id"] is None
    assert conflict["resolution"]["requires_human_review"] is True
    assert {e["document_id"] for e in conflict["evidence"]} == {"policy-a", "policy-b"}
    assert all(e["quote"] and e["verification"]["page_verified"] for e in conflict["evidence"])


def test_obligation_notice_period_conflict_is_detected():
    pages = [
        {"document_id": "contract-a", "filename": "contract_a.pdf", "page": 1, "source_type": "PDF_TEXT",
         "text": "The notice period is 30 days."},
        {"document_id": "contract-b", "filename": "contract_b.pdf", "page": 1, "source_type": "PDF_TEXT",
         "text": "The notice period shall be 60 days."},
    ]
    result = F.analyse(pages)
    conflicts = [x for x in result["contradictions"] if x["topic"] == "notice period"]
    assert len(conflicts) == 1
    assert {e["document_id"] for e in conflicts[0]["evidence"]} == {"contract-a", "contract-b"}
    assert conflicts[0]["resolution"]["requires_human_review"] is True


def test_eligibility_thresholds_for_different_clauses_are_not_compared():
    pages = [
        {"document_id": "policy-a", "filename": "policy_a.pdf", "page": 1, "source_type": "PDF_TEXT",
         "text": "Under Clause 4, the minimum age is 21 years."},
        {"document_id": "policy-b", "filename": "policy_b.pdf", "page": 1, "source_type": "PDF_TEXT",
         "text": "Under Clause 9, the minimum age is 18 years."},
    ]
    result = F.analyse(pages)
    assert not [x for x in result["contradictions"] if x["topic"] == "minimum age"]


def test_processing_fee_and_overdue_charge_are_not_false_contradictions():
    pages = [
        {"document_id": "policy-a", "filename": "policy_a.pdf", "page": 1,
         "source_type": "PDF_TEXT",
         "text": "The processing fee is 0.75 percent."},
        {"document_id": "policy-b", "filename": "policy_b.pdf", "page": 1,
         "source_type": "PDF_TEXT",
         "text": "The processing fee is 1.00 percent."},
        {"document_id": "policy-c", "filename": "policy_c.pdf", "page": 1,
         "source_type": "PDF_TEXT",
         "text": "The overdue instalment fee is 1.50 percent."},
    ]

    result = F.analyse(pages)

    processing_conflicts = [
        x for x in result["contradictions"]
        if x["topic"].startswith("processing fee")
    ]
    overdue_conflicts = [
        x for x in result["contradictions"]
        if x["topic"].startswith("overdue charge")
    ]

    assert len(processing_conflicts) == 1
    assert overdue_conflicts == []



def test_financial_calculations_return_formula_and_working():
    simple = calculate_financial_value("simple_interest", 100000, 8, 2, "years")
    assert simple["result"] == {"interest": 16000.0, "total_amount": 116000.0}
    assert simple["formula"] == "SI = P × R × T / 100"
    assert "100000" in simple["working"]
    assert simple["input_source"] == "USER_PROVIDED"

    emi = calculate_financial_value("emi", 120000, 0, 12, "months")
    assert emi["result"]["monthly_emi"] == 10000.0
    assert emi["result"]["total_payable"] == 120000.0

    compound = calculate_financial_value("compound_interest", 100000, 12, 1, "years", 12)
    assert compound["result"]["total_amount"] > 112000.0


def test_financial_calculator_rejects_invalid_inputs():
    import pytest
    with pytest.raises(ValueError):
        calculate_financial_value("simple_interest", 0, 8, 2, "years")
    with pytest.raises(ValueError):
        calculate_financial_value("unknown", 100000, 8, 2, "years")



@pytest.mark.asyncio
async def test_phase8_hindi_response_language_and_calculator_api(client):
    operator = await hdr(client, "op_a")

    calc = await client.post(
        "/api/document-ai/calculate",
        json={
            "calculation_type": "simple_interest",
            "principal": 100000,
            "annual_rate_percent": 8,
            "duration_value": 2,
            "duration_unit": "years",
        },
        headers=operator,
    )
    assert calc.status_code == 200, calc.text
    assert calc.json()["result"]["interest"] == 16000.0
    assert calc.json()["input_source"] == "USER_PROVIDED"

    doc = await upload_pdf(client, operator, "loan_agreement.pdf", BASE)
    await index(client, operator, doc)
    response = await ask(client, operator, "interest rate", [doc], language="hi")
    assert response.status_code == 200, response.text
    assert response.json()["response_language"] == "hi"
    assert response.json()["evidence"][0]["verification"]["quote_found_in_source"] is True



def test_hindi_question_retrieves_hindi_source_passage_with_verified_quote():
    page = {
        "document_id": "doc-hindi",
        "filename": "policy_hindi.pdf",
        "page": 1,
        "source_type": "PDF_TEXT",
        "text": "वार्षिक ब्याज दर आठ प्रतिशत है।",
    }
    result = qa.answer_question("वार्षिक ब्याज दर क्या है?", [page], ["doc-hindi"])
    assert not result["abstained"]
    assert result["claims"][0]["status"] == "SUPPORTED"
    assert result["evidence"][0]["quote"] == page["text"]
    assert result["evidence"][0]["verification"]["quote_found_in_source"] is True
    assert result["faithfulness_score"] == 1.0
