"""
MongoDB connection (Motor async client) for BhoomiTrust AI.

Replaces the previous SQLAlchemy/SQLite setup. A single AsyncIOMotorClient is
created at import time and reused for the life of the process; FastAPI's
startup/shutdown hooks (see main.py) verify connectivity and build indexes.
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import settings

client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URL)
db: AsyncIOMotorDatabase = client[settings.MONGODB_DB_NAME]

# Collections (per spec: records, documents, audit, users)
users_collection = db["users"]
documents_collection = db["documents"]
audit_collection = db["audit"]
# Document AI (see docs/API_CONTRACT.md)
docai_pages_collection = db["docai_pages"]
docai_jobs_collection = db["docai_jobs"]
docai_answers_collection = db["docai_answers"]
docai_vectors_collection = db["docai_vectors"]
chat_sessions_collection = db["chat_sessions"]


def get_db() -> AsyncIOMotorDatabase:
    """FastAPI dependency — returns the shared Motor database handle."""
    return db


async def create_indexes() -> None:
    """Called once on app startup. Safe to call repeatedly (idempotent)."""
    await users_collection.create_index("username", unique=True)
    await documents_collection.create_index("uploaded_at")
    await audit_collection.create_index("timestamp")
    await audit_collection.create_index("document_id")
    await documents_collection.create_index("uploaded_by")
    await docai_pages_collection.create_index([("document_id", 1), ("page", 1)], unique=True)
    await docai_jobs_collection.create_index("document_id")
    await docai_answers_collection.create_index("user_id")
    await docai_answers_collection.create_index("claims.claim_id")
    await chat_sessions_collection.create_index([("user_id", 1), ("updated_at", -1)])
    await docai_vectors_collection.create_index([("document_id", 1), ("page", 1)])


async def ping() -> bool:
    await client.admin.command("ping")
    return True
