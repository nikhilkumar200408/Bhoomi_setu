from typing import List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .auth import decode_access_token
from .database import users_collection, documents_collection, records_collection
from . import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    user = await users_collection.find_one({"_id": user_id})
    if user is None:
        raise credentials_exception
    return user


def require_roles(allowed: List[str]):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is not permitted to perform this action.",
            )
        return user

    return checker


# ---------------------------------------------------------------------------
# Ownership / data-isolation helpers.
#
# Policy: ADMIN and REVENUE_OFFICER are reviewer roles and may see every
# document and record (officers must review what operators upload). A
# DATA_ENTRY_OPERATOR only sees documents they uploaded, and the records,
# audit entries and statistics derived from them. Unauthorized access to a
# specific resource answers 404 so existence is not leaked.
# ---------------------------------------------------------------------------
PRIVILEGED_ROLES = ("ADMIN", "REVENUE_OFFICER")


def is_privileged(user: dict) -> bool:
    return user["role"] in PRIVILEGED_ROLES


def document_scope(user: dict) -> dict:
    """Mongo filter restricting the documents collection to what the user may see."""
    return {} if is_privileged(user) else {"uploaded_by": user["_id"]}


async def accessible_document_ids(user: dict) -> Optional[List[str]]:
    """None means unrestricted; otherwise the list of document ids the user owns."""
    if is_privileged(user):
        return None
    return [d["_id"] async for d in documents_collection.find({"uploaded_by": user["_id"]}, {"_id": 1})]


def record_scope(doc_ids: Optional[List[str]]) -> dict:
    return {} if doc_ids is None else {"document_id": {"$in": doc_ids}}


async def get_accessible_document(document_id: str, user: dict) -> dict:
    document = await documents_collection.find_one({"_id": document_id, **document_scope(user)})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def get_accessible_record(record_id: str, user: dict) -> dict:
    record = await records_collection.find_one({"_id": record_id})
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if not is_privileged(user):
        await get_accessible_document(record["document_id"], user)  # 404 if not theirs
    return record
