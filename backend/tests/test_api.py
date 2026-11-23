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
async def test_batch_upload(client: AsyncClient):
    operator_headers = {"Authorization": f"Bearer {await get_token(client, 'operator_test', 'Operator@123')}"}
    files = []
    for filename in ("english_land_record.png", "hindi_land_record.png"):
        files.append(("files", (filename, open(os.path.join(SAMPLE_DIR, filename), "rb"), "image/png")))
    resp = await client.post("/api/documents/upload-batch", files=files, headers=operator_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2
