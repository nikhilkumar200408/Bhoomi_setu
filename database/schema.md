# BhoomiTrust AI — MongoDB collection reference (`bhoomitrust_db`)

This mirrors `backend/app/models.py` and `backend/app/database.py` exactly.
MongoDB is schemaless — the application creates collections and indexes
automatically on startup (`create_indexes()` in `app/database.py`). This file
is a readable reference only.

## `users`
```
{
  _id: string (uuid),
  username: string (unique, indexed),
  full_name: string,
  hashed_password: string,   // bcrypt or argon2, see PASSWORD_HASH_SCHEME
  role: "ADMIN" | "DATA_ENTRY_OPERATOR" | "REVENUE_OFFICER",
  created_at: datetime
}
```

## `documents`
```
{
  _id: string (uuid),
  filename: string,
  stored_path: string | null,
  file_type: string,
  file_size_bytes: int,
  status: "UPLOADED" | "PROCESSING" | "PROCESSED" | "FAILED",
  scenario_tag: string | null,
  uploaded_by: string (user id) | null,
  uploaded_at: datetime,       // indexed
  processed_at: datetime | null,
  error_message: string | null
}
```

## `records`
Land records embed their fields, validations, and verification history as
sub-documents — a record is read/written as a single atomic document.
```
{
  _id: string (uuid),
  document_id: string,          // indexed
  status: "PENDING_REVIEW" | "AUTO_PASSED" | "VERIFIED" | "REJECTED" | "UNRESOLVED",  // indexed
  overall_confidence: float,
  anomaly_score: int,
  anomaly_level: "LOW" | "MEDIUM" | "HIGH",
  anomaly_reasons: [string],
  created_at: datetime,          // indexed
  verified_at: datetime | null,
  verified_by: string | null,
  fields: [
    {
      id: string, field_name: string, value: string | null,
      confidence: float, ocr_confidence: float, extraction_confidence: float,
      confidence_band: "HIGH" | "REVIEW" | "VERIFY",
      source_page: int | null, source_bbox: [float] | null, source_text: string | null,
      review_reason: string | null, validation_status: "PASS" | "WARNING" | "FAIL" | "UNVALIDATED"
    }
  ],                              // indexed: fields.field_name, fields.value
  validations: [
    { id: string, rule: string, status: "PASS" | "WARNING" | "FAIL",
      severity: "LOW" | "MEDIUM" | "HIGH", message: string, affected_field: string | null,
      created_at: datetime }
  ],
  verification_actions: [
    { id: string, action: "EDIT" | "APPROVE" | "REJECT" | "MARK_UNRESOLVED",
      field_name: string | null, old_value: string | null, new_value: string | null,
      reason: string | null, user_id: string | null, timestamp: datetime }
  ]
}
```

## `audit`
System-wide, append-only audit trail (also joined by `record_id` /
`document_id` for a single record's full history from upload onward).
```
{
  _id: string (uuid),
  record_id: string | null,
  document_id: string | null,
  action: string,   // UPLOAD | OCR | EXTRACTION | VALIDATION | EDIT | APPROVE | REJECT | MARK_UNRESOLVED
  user_id: string | null,
  old_value: string | null,
  new_value: string | null,
  log_metadata: object,
  timestamp: datetime   // indexed
}
```
