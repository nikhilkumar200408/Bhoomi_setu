from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import schemas
from ..database import records_collection, documents_collection, audit_collection
from ..deps import get_current_user, require_roles, accessible_document_ids, record_scope, get_accessible_record
from ..services.verification.service import edit_field, apply_verification_action

router = APIRouter(prefix="/api/records", tags=["records"])


def _record_out(r: dict) -> schemas.LandRecordOut:
    return schemas.LandRecordOut(
        id=r["_id"], document_id=r["document_id"], status=r["status"],
        overall_confidence=r["overall_confidence"], anomaly_score=r["anomaly_score"],
        anomaly_level=r["anomaly_level"], anomaly_reasons=r["anomaly_reasons"],
        created_at=r["created_at"], verified_at=r.get("verified_at"), verified_by=r.get("verified_by"),
        signature_hash=r.get("signature_hash"),
    )


def _field_out(f: dict) -> schemas.ExtractedFieldOut:
    return schemas.ExtractedFieldOut(
        id=f["id"], field_name=f["field_name"], value=f["value"], confidence=f["confidence"],
        ocr_confidence=f["ocr_confidence"], extraction_confidence=f["extraction_confidence"],
        confidence_band=f["confidence_band"], source_page=f.get("source_page"),
        source_bbox=f.get("source_bbox"), source_text=f.get("source_text"),
        review_reason=f.get("review_reason"), validation_status=f["validation_status"],
    )


def _validation_out(v: dict) -> schemas.ValidationResultOut:
    return schemas.ValidationResultOut(
        id=v["id"], rule=v["rule"], status=v["status"], severity=v["severity"],
        message=v["message"], affected_field=v.get("affected_field"),
    )


async def _document_out(document_id: str) -> schemas.DocumentOut:
    doc = await documents_collection.find_one({"_id": document_id})
    return schemas.DocumentOut(
        id=doc["_id"], filename=doc["filename"], file_type=doc["file_type"],
        file_size_bytes=doc["file_size_bytes"], status=doc["status"],
        uploaded_at=doc["uploaded_at"],
        processed_at=doc.get("processed_at"), error_message=doc.get("error_message"),
    )


@router.get("", response_model=List[schemas.LandRecordOut])
async def list_records(
    status_filter: Optional[str] = Query(None, alias="status"),
    user: dict = Depends(get_current_user),
):
    query = record_scope(await accessible_document_ids(user))
    if status_filter:
        query["status"] = status_filter
    cursor = records_collection.find(query).sort("created_at", -1)
    return [_record_out(r) async for r in cursor]


@router.get("/{record_id}", response_model=schemas.LandRecordDetailOut)
async def get_record(record_id: str, user: dict = Depends(get_current_user)):
    record = await get_accessible_record(record_id, user)
    base = _record_out(record)
    return schemas.LandRecordDetailOut(
        **base.model_dump(),
        fields=[_field_out(f) for f in record["fields"]],
        validations=[_validation_out(v) for v in record["validations"]],
        document=await _document_out(record["document_id"]),
    )


@router.patch("/{record_id}/fields/{field_name}", response_model=schemas.ExtractedFieldOut)
async def update_field(
    record_id: str,
    field_name: str,
    payload: schemas.FieldUpdateRequest,
    user: dict = Depends(require_roles(["DATA_ENTRY_OPERATOR", "REVENUE_OFFICER"])),
):
    record = await get_accessible_record(record_id, user)
    if not any(f["field_name"] == field_name for f in record["fields"]):
        raise HTTPException(status_code=404, detail="Field not found")

    updated_field = await edit_field(record, field_name, payload.new_value, user, payload.reason)
    return _field_out(updated_field)


@router.post("/{record_id}/verify", response_model=schemas.VerificationActionOut)
async def verify_record(
    record_id: str,
    payload: schemas.VerifyRequest,
    user: dict = Depends(require_roles(["REVENUE_OFFICER"])),
):
    record = await get_accessible_record(record_id, user)
    if payload.action.upper() not in ("APPROVE", "REJECT", "MARK_UNRESOLVED"):
        raise HTTPException(status_code=400, detail="action must be one of APPROVE, REJECT, MARK_UNRESOLVED")

    try:
        action = await apply_verification_action(record, payload.action, user, payload.reason, payload.signature)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.VerificationActionOut(
        id=action["id"], action=action["action"], field_name=action.get("field_name"),
        old_value=action.get("old_value"), new_value=action.get("new_value"),
        reason=action.get("reason"), user_id=action.get("user_id"), timestamp=action["timestamp"],
        signature_hash=action.get("signature_hash"),
    )


@router.get("/public-verify/{record_id}", response_model=schemas.PublicVerificationOut)
async def public_verify(record_id: str):
    """UNAUTHENTICATED — intentionally minimal. Meant to be reached by
    scanning the QR code on a printed Digital Verification Certificate, so
    anyone holding the paper can confirm it's genuine without needing a
    BhoomiTrust login. Exposes only the signature hash + verification
    status — never owner name, survey number, or any other land-record PII."""
    record = await records_collection.find_one({"_id": record_id})
    if not record or record["status"] != "VERIFIED":
        raise HTTPException(status_code=404, detail="No verified record found for this certificate")
    return schemas.PublicVerificationOut(
        record_id=record["_id"],
        status=record["status"],
        verified_at=record["verified_at"],
        signature_hash=record.get("signature_hash"),
    )


@router.get("/{record_id}/audit", response_model=List[schemas.AuditLogOut])
async def record_audit(record_id: str, user: dict = Depends(get_current_user)):
    record = await get_accessible_record(record_id, user)
    # Include both record-level events (EDIT/VERIFY/APPROVE/REJECT) and the
    # earlier document-level pipeline events (UPLOAD/OCR/EXTRACTION/
    # VALIDATION) that occurred before the record existed, so the audit
    # trail for a record shows its complete history from upload onward.
    cursor = audit_collection.find(
        {"$or": [{"record_id": record_id}, {"document_id": record["document_id"]}]}
    ).sort("timestamp", 1)
    logs = []
    async for log in cursor:
        logs.append(schemas.AuditLogOut(
            id=log["_id"], record_id=log.get("record_id"), document_id=log.get("document_id"),
            action=log["action"], user_id=log.get("user_id"), old_value=log.get("old_value"),
            new_value=log.get("new_value"), log_metadata=log.get("log_metadata", {}), timestamp=log["timestamp"],
        ))
    return logs
