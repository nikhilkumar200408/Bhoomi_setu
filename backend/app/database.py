"""MongoDB connection and collection registry for TrustLens AI."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import settings

client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URL)
db: AsyncIOMotorDatabase = client[settings.MONGODB_DB_NAME]

users_collection = db["users"]
documents_collection = db["documents"]
audit_collection = db["audit"]
docai_pages_collection = db["docai_pages"]
docai_jobs_collection = db["docai_jobs"]
docai_answers_collection = db["docai_answers"]
docai_vectors_collection = db["docai_vectors"]
chat_sessions_collection = db["chat_sessions"]

# Phase 2 verification and compliance collections.
compliance_checklists_collection = db["compliance_checklists"]
compliance_rules_collection = db["compliance_rules"]
compliance_reviews_collection = db["compliance_reviews"]
compliance_events_collection = db["compliance_events"]


def get_db() -> AsyncIOMotorDatabase:
    return db


async def create_indexes() -> None:
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
    await compliance_checklists_collection.create_index([("user_id", 1), ("created_at", -1)])
    await compliance_rules_collection.create_index([("user_id", 1), ("created_at", -1)])
    await compliance_reviews_collection.create_index([("document_ids", 1), ("status", 1)])
    await compliance_events_collection.create_index([("review_id", 1), ("timestamp", -1)])


async def ping() -> bool:
    await client.admin.command("ping")
    return True
