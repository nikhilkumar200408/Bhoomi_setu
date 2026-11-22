import os
import shutil

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import users_collection
from app import models
from app.auth import hash_password

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_data")
TESSERACT_AVAILABLE = shutil.which("tesseract") is not None

pytestmark = pytest.mark.skipif(
    not TESSERACT_AVAILABLE,
    reason="tesseract-ocr (+ hin/kan langpacks) not installed — see backend/.env.example",
)


@pytest_asyncio.fixture(autouse=True)
async def _seed_users():
    for username, full_name, password, role in [
        ("operator_test", "Test Operator", "Operator@123", models.UserRole.DATA_ENTRY_OPERATOR),
        ("officer_test", "Test Revenue Officer", "Officer@123", models.UserRole.REVENUE_OFFICER),
        ("admin_test", "Test Admin", "Admin@123", models.UserRole.ADMIN),
    ]:
        await users_collection.insert_one({
            "_id": models.gen_uuid(), "username": username, "full_name": full_name,
            "hashed_password": hash_password(password), "role": role.value, "created_at": models.utcnow(),
        })


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def get_token(client: AsyncClient, username, password):
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def upload_sample(client: AsyncClient, headers: dict, filename: str) -> dict:
    path = os.path.join(SAMPLE_DIR, filename)
    with open(path, "rb") as f:
        resp = await client.post(
            "/api/documents/upload", files={"file": (filename, f, "image/png")}, headers=headers
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_full_real_pipeline_english_sample(client: AsyncClient):
    """Runs the ACTUAL OpenCV + Tesseract + regex extraction + validation
    pipeline against a real sample scanned document image — no mocks."""
    operator_headers = {"Authorization": f"Bearer {await get_token(client, 'operator_test', 'Operator@123')}"}
    officer_headers = {"Authorization": f"Bearer {await get_token(client, 'officer_test', 'Officer@123')}"}

    document = await upload_sample(client, operator_headers, "english_land_record.png")
    assert document["status"] == "UPLOADED"

    resp = await client.post(f"/api/documents/{document['id']}/process", headers=operator_headers)
    assert resp.status_code == 200, resp.text
    record = resp.json()
    record_id = record["id"]

    resp = await client.get(f"/api/records/{record_id}", headers=officer_headers)
    detail = resp.json()
    assert len(detail["fields"]) == 14
    owner_field = next(f for f in detail["fields"] if f["field_name"] == "owner_name")
    assert "Ramesh" in (owner_field["value"] or "")

    # Approving without a signature must fail
    resp = await client.post(f"/api/records/{record_id}/verify", json={"action": "APPROVE"}, headers=officer_headers)
    assert resp.status_code == 400

    # Approving with a signature succeeds and returns a signature hash
    resp = await client.post(
        f"/api/records/{record_id}/verify",
        json={"action": "APPROVE", "signature": "data:image/png;base64,ZmFrZS1zaWc="},
        headers=officer_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["signature_hash"]

    resp = await client.get(f"/api/records/{record_id}", headers=officer_headers)
    body = resp.json()
    assert body["status"] == "VERIFIED"
    assert body["signature_hash"]

    resp = await client.get(f"/api/records/{record_id}/audit", headers=officer_headers)
    actions = [a["action"] for a in resp.json()]
    for expected in ("OCR", "EXTRACTION", "VALIDATION", "APPROVE"):
        assert expected in actions


@pytest.mark.asyncio
async def test_hindi_and_kannada_samples_extract_native_script(client: AsyncClient):
    operator_headers = {"Authorization": f"Bearer {await get_token(client, 'operator_test', 'Operator@123')}"}

    for filename, expected_snippet in [
        ("hindi_land_record.png", "देवी"),
        ("kannada_land_record.png", "ಹೆಗ್ಡೆ"),
    ]:
        document = await upload_sample(client, operator_headers, filename)
        resp = await client.post(f"/api/documents/{document['id']}/process", headers=operator_headers)
        assert resp.status_code == 200, resp.text
        record = resp.json()
        resp = await client.get(f"/api/records/{record['id']}", headers=operator_headers)
        owner_field = next(f for f in resp.json()["fields"] if f["field_name"] == "owner_name")
        assert expected_snippet in (owner_field["value"] or "")


@pytest.mark.asyncio
async def test_batch_upload(client: AsyncClient):
    operator_headers = {"Authorization": f"Bearer {await get_token(client, 'operator_test', 'Operator@123')}"}
    files = []
    for filename in ("english_land_record.png", "hindi_land_record.png"):
        files.append(("files", (filename, open(os.path.join(SAMPLE_DIR, filename), "rb"), "image/png")))
    resp = await client.post("/api/documents/upload-batch", files=files, headers=operator_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_rbac_admin_cannot_upload_or_verify(client: AsyncClient):
    admin_headers = {"Authorization": f"Bearer {await get_token(client, 'admin_test', 'Admin@123')}"}
    path = os.path.join(SAMPLE_DIR, "english_land_record.png")
    with open(path, "rb") as f:
        resp = await client.post(
            "/api/documents/upload", files={"file": ("x.png", f, "image/png")}, headers=admin_headers
        )
    assert resp.status_code == 403

    resp = await client.post("/api/records/some-id/verify", json={"action": "APPROVE"}, headers=admin_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rbac_data_entry_operator_cannot_verify(client: AsyncClient):
    operator_headers = {"Authorization": f"Bearer {await get_token(client, 'operator_test', 'Operator@123')}"}
    document = await upload_sample(client, operator_headers, "english_land_record.png")
    resp = await client.post(f"/api/documents/{document['id']}/process", headers=operator_headers)
    record_id = resp.json()["id"]

    resp = await client.post(f"/api/records/{record_id}/verify", json={"action": "APPROVE"}, headers=operator_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_officer_queue_risk_filter(client: AsyncClient):
    operator_headers = {"Authorization": f"Bearer {await get_token(client, 'operator_test', 'Operator@123')}"}
    officer_headers = {"Authorization": f"Bearer {await get_token(client, 'officer_test', 'Officer@123')}"}

    document = await upload_sample(client, operator_headers, "kannada_land_record.png")
    await client.post(f"/api/documents/{document['id']}/process", headers=operator_headers)

    resp = await client.get("/api/dashboard/officer-queue", params={"risk": "all"}, headers=officer_headers)
    assert resp.status_code == 200
    all_count = len(resp.json())

    resp = await client.get("/api/dashboard/officer-queue", headers=officer_headers)  # default: flagged only
    assert resp.status_code == 200
    flagged_count = len(resp.json())
    assert flagged_count <= all_count


@pytest.mark.asyncio
async def test_csv_export_and_public_verify(client: AsyncClient):
    operator_headers = {"Authorization": f"Bearer {await get_token(client, 'operator_test', 'Operator@123')}"}
    officer_headers = {"Authorization": f"Bearer {await get_token(client, 'officer_test', 'Officer@123')}"}

    document = await upload_sample(client, operator_headers, "english_land_record.png")
    resp = await client.post(f"/api/documents/{document['id']}/process", headers=operator_headers)
    record_id = resp.json()["id"]

    # CSV export
    resp = await client.get("/api/dashboard/export.csv", headers=officer_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "owner_name" in resp.text
    assert "Ramesh" in resp.text

    # Public verify: 404 before approval
    resp = await client.get(f"/api/records/public-verify/{record_id}")
    assert resp.status_code == 404

    await client.post(
        f"/api/records/{record_id}/verify",
        json={"action": "APPROVE", "signature": "data:image/png;base64,ZmFrZS1zaWc="},
        headers=officer_headers,
    )

    # Public verify: works after approval, no auth header needed
    resp = await client.get(f"/api/records/public-verify/{record_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "VERIFIED"
    assert body["signature_hash"]
