"""
Seeds realistic user accounts and runs 3 real sample scanned land-record
images (English, Hindi, Kannada — see backend/sample_data/) through the
ACTUAL OpenCV + Tesseract + translation + validation pipeline end-to-end.
No mock JSON, no scenario tags, no fabricated field values — every value in
the seeded records is genuinely OCR'd and extracted from the sample images.

Run with: python -m app.seed_real_data
"""
import asyncio
import os

from . import models
from .auth import hash_password
from .database import users_collection, documents_collection, records_collection, create_indexes
from .services.pipeline import process_document

SAMPLE_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_data")

REAL_USERS = [
    {"username": "admin", "full_name": "System Admin", "password": "Admin@123", "role": models.UserRole.ADMIN},
    {"username": "operator", "full_name": "Data Entry Operator", "password": "Operator@123",
     "role": models.UserRole.DATA_ENTRY_OPERATOR},
    {"username": "revenue_officer", "full_name": "Revenue Officer", "password": "Officer@123",
     "role": models.UserRole.REVENUE_OFFICER},
]

SAMPLE_FILES = ["english_land_record.png", "hindi_land_record.png", "kannada_land_record.png"]


async def seed():
    await create_indexes()

    created_users = {}
    for u in REAL_USERS:
        existing = await users_collection.find_one({"username": u["username"]})
        if existing:
            created_users[u["username"]] = existing
            continue
        user = {
            "_id": models.gen_uuid(),
            "username": u["username"],
            "full_name": u["full_name"],
            "hashed_password": hash_password(u["password"]),
            "role": u["role"].value,
            "created_at": models.utcnow(),
        }
        await users_collection.insert_one(user)
        created_users[u["username"]] = user
        print(f"Created user: {u['username']} / {u['password']} ({u['role'].value})")

    operator = created_users["operator"]

    if await documents_collection.count_documents({}) > 0:
        print("Documents already exist — skipping sample ingestion.")
        return

    for fname in SAMPLE_FILES:
        src_path = os.path.abspath(os.path.join(SAMPLE_DATA_DIR, fname))
        if not os.path.exists(src_path):
            print(f"WARNING: sample file not found, skipping: {src_path}")
            continue

        document = {
            "_id": models.gen_uuid(),
            "filename": fname,
            "stored_path": src_path,
            "file_type": "image/png",
            "file_size_bytes": os.path.getsize(src_path),
            "status": models.DocumentStatus.UPLOADED.value,
            "uploaded_by": operator["_id"],
            "uploaded_at": models.utcnow(),
            "processed_at": None,
            "error_message": None,
        }
        await documents_collection.insert_one(document)
        print(f"Running real OCR + extraction + validation pipeline on {fname} ...")
        record = await process_document(document, operator)
        print(
            f"  -> record {record['_id']}: status={record['status']} "
            f"confidence={record['overall_confidence']}% anomaly={record['anomaly_level']}"
        )

    print("Seeding complete. All records were produced by the real OCR pipeline (no mock data).")


if __name__ == "__main__":
    asyncio.run(seed())
