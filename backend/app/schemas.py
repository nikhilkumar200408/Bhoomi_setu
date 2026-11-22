from datetime import datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, ConfigDict


# ---------- Auth ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    full_name: str
    role: str


# ---------- Documents ----------

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class DocumentDetailOut(DocumentOut):
    land_record_id: Optional[str] = None


# ---------- Extracted Fields ----------

class ExtractedFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    field_name: str
    value: Optional[str]
    confidence: float
    ocr_confidence: float
    extraction_confidence: float
    confidence_band: str
    source_page: Optional[int]
    source_bbox: Optional[List[float]]
    source_text: Optional[str]
    review_reason: Optional[str]
    validation_status: str


class FieldUpdateRequest(BaseModel):
    new_value: str
    reason: Optional[str] = "Manual correction by reviewer"


# ---------- Validation ----------

class ValidationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    rule: str
    status: str
    severity: str
    message: str
    affected_field: Optional[str]


# ---------- Land Record ----------

class LandRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    status: str
    overall_confidence: float
    anomaly_score: int
    anomaly_level: str
    anomaly_reasons: List[str]
    created_at: datetime
    verified_at: Optional[datetime]
    verified_by: Optional[str]
    signature_hash: Optional[str] = None


class LandRecordDetailOut(LandRecordOut):
    fields: List[ExtractedFieldOut]
    validations: List[ValidationResultOut]
    document: DocumentOut


# ---------- Verification ----------

class VerifyRequest(BaseModel):
    action: str  # APPROVE | REJECT | MARK_UNRESOLVED
    reason: Optional[str] = None
    signature: Optional[str] = None  # base64 PNG data URL, required for APPROVE


class VerificationActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action: str
    field_name: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    reason: Optional[str]
    user_id: Optional[str]
    signature_hash: Optional[str] = None
    timestamp: datetime


# ---------- Audit ----------

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    record_id: Optional[str]
    document_id: Optional[str]
    action: str
    user_id: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    log_metadata: Dict[str, Any]
    timestamp: datetime


# ---------- Dashboard ----------

class DashboardStats(BaseModel):
    documents_processed: int
    records_extracted: int
    pending_verification: int
    average_confidence: float
    auto_processed_pct: float
    human_review_pct: float
    validation_warnings: int
    average_processing_time_seconds: float
    confidence_distribution: Dict[str, int]
    validation_error_categories: Dict[str, int]
    verification_status_breakdown: Dict[str, int]
    district_wise_progress: Dict[str, int]
    is_synthetic: bool = True


class OfficerQueueItem(BaseModel):
    record_id: str
    document_id: str
    owner_name: Optional[str]
    survey_number: Optional[str]
    village: Optional[str]
    district: Optional[str]
    status: str
    overall_confidence: float
    anomaly_level: str
    anomaly_reasons: List[str]
    created_at: datetime


class UserActivityItem(BaseModel):
    user_id: str
    username: str
    full_name: str
    role: str
    action_count: int
    last_action_at: Optional[datetime]


class SearchResultItem(BaseModel):
    record_id: str
    document_id: str
    owner_name: Optional[str]
    survey_number: Optional[str]
    khasra_number: Optional[str]
    khata_number: Optional[str]
    village: Optional[str]
    tehsil: Optional[str]
    district: Optional[str]
    status: str
    overall_confidence: float


class PublicVerificationOut(BaseModel):
    """Minimal, unauthenticated response for QR-code certificate verification."""
    record_id: str
    status: str
    verified_at: Optional[datetime]
    signature_hash: Optional[str]
