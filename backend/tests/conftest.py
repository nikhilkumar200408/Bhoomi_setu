import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

# Patch the Motor client before router/service modules bind collection imports.
import app.database as dbmod  # noqa: E402

dbmod.client = AsyncMongoMockClient()
dbmod.db = dbmod.client[dbmod.settings.MONGODB_DB_NAME]
dbmod.users_collection = dbmod.db["users"]
dbmod.documents_collection = dbmod.db["documents"]
dbmod.audit_collection = dbmod.db["audit"]
dbmod.docai_pages_collection = dbmod.db["docai_pages"]
dbmod.docai_jobs_collection = dbmod.db["docai_jobs"]
dbmod.docai_answers_collection = dbmod.db["docai_answers"]
dbmod.docai_vectors_collection = dbmod.db["docai_vectors"]
dbmod.chat_sessions_collection = dbmod.db["chat_sessions"]
dbmod.compliance_checklists_collection = dbmod.db["compliance_checklists"]
dbmod.compliance_rules_collection = dbmod.db["compliance_rules"]
dbmod.compliance_reviews_collection = dbmod.db["compliance_reviews"]
dbmod.compliance_events_collection = dbmod.db["compliance_events"]


@pytest_asyncio.fixture(autouse=True)
async def _clean_collections():
    collections = (
        dbmod.users_collection, dbmod.documents_collection, dbmod.audit_collection,
        dbmod.docai_pages_collection, dbmod.docai_jobs_collection, dbmod.docai_answers_collection,
        dbmod.docai_vectors_collection, dbmod.chat_sessions_collection,
        dbmod.compliance_checklists_collection, dbmod.compliance_rules_collection,
        dbmod.compliance_reviews_collection, dbmod.compliance_events_collection,
    )
    for coll in collections:
        await coll.delete_many({})
    yield
