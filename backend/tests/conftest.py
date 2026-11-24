import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

# IMPORTANT: patch app.database's Motor client with an in-memory mongomock
# client BEFORE any router/service module is imported, since they bind
# `from ..database import x_collection` at import time.
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


@pytest_asyncio.fixture(autouse=True)
async def _clean_collections():
    """Every test starts against an empty in-memory database."""
    for coll in (dbmod.users_collection, dbmod.documents_collection, dbmod.audit_collection,
                 dbmod.docai_pages_collection, dbmod.docai_jobs_collection, dbmod.docai_answers_collection, dbmod.docai_vectors_collection, dbmod.chat_sessions_collection):
        await coll.delete_many({})
    yield
