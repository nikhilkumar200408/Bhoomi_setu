from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..database import audit_collection
from ..deps import get_current_user, accessible_document_ids

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[schemas.AuditLogOut])
async def list_audit_logs(
    action: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    user: dict = Depends(get_current_user),
):
    query: dict = {"action": action} if action else {}
    doc_ids = await accessible_document_ids(user)
    if doc_ids is not None:
        # Operators only see audit entries for their own documents or their own actions.
        query["$or"] = [{"document_id": {"$in": doc_ids}}, {"user_id": user["_id"]}]
    cursor = audit_collection.find(query).sort("timestamp", -1).limit(limit)
    logs = []
    async for log in cursor:
        logs.append(schemas.AuditLogOut(
            id=log["_id"], record_id=log.get("record_id"), document_id=log.get("document_id"),
            action=log["action"], user_id=log.get("user_id"), old_value=log.get("old_value"),
            new_value=log.get("new_value"), log_metadata=log.get("log_metadata", {}), timestamp=log["timestamp"],
        ))
    return logs
