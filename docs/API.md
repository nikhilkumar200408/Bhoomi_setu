# API Reference

This file covers the existing land-record API. The new Document AI API
(`/api/document-ai/*`) is specified in [`API_CONTRACT.md`](API_CONTRACT.md), which is
the source of truth for it and is not yet implemented in the backend.

Full interactive documentation (Swagger/OpenAPI) is available at
`http://localhost:8000/docs` whenever the backend is running.

Base URL (local): `http://localhost:8000`

All endpoints except `/api/auth/login` and `/api/health` require a bearer
token: `Authorization: Bearer <token>`.

## Auth

| Method | Path              | Roles | Description                     |
|--------|-------------------|-------|----------------------------------|
| POST   | `/api/auth/login` | any   | Returns a JWT + user profile     |
| GET    | `/api/auth/me`    | any   | Returns the current user profile |

## Documents

| Method | Path                              | Roles           | Description                                            |
|--------|------------------------------------|-----------------|----------------------------------------------------------|
| POST   | `/api/documents/upload`            | DATA_ENTRY_OPERATOR | Upload one file (real OCR pipeline: OpenCV + Tesseract, eng/hin/kan) |
| POST   | `/api/documents/upload-batch`      | DATA_ENTRY_OPERATOR | Batch upload multiple files                              |
| POST   | `/api/documents/{id}/process`      | DATA_ENTRY_OPERATOR | Runs the full pipeline: OCR → translation → extraction → confidence → validation → anomaly |
| GET    | `/api/documents/{id}/file`         | any             | Streams the original uploaded file (auth required)      |
| GET    | `/api/documents`                   | any             | List all documents                                       |
| GET    | `/api/documents/{id}`              | any             | Document detail incl. its land_record_id                 |

## Records

| Method | Path                                          | Roles              | Description                                     |
|--------|------------------------------------------------|--------------------|---------------------------------------------------|
| GET    | `/api/records`                                 | any                | List land records (optional `?status=` filter)   |
| GET    | `/api/records/public-verify/{id}`              | none               | Public certificate verification (no login)        |
| GET    | `/api/records/{id}`                            | any                | Full record detail: fields, validations, document |
| PATCH  | `/api/records/{id}/fields/{field_name}`        | REVENUE_OFFICER    | Edit an extracted field value                     |
| POST   | `/api/records/{id}/verify`                     | REVENUE_OFFICER    | `{action, signature}` — signature (base64 PNG) required for APPROVE |
| GET    | `/api/records/{id}/audit`                      | any                | Full audit history for the record                 |

## Dashboard / Search / Audit

| Method | Path                    | Roles | Description                              |
|--------|--------------------------|-------|--------------------------------------------|
| GET    | `/api/dashboard/stats`  | any   | Aggregate stats + chart data for the dashboard |
| GET    | `/api/dashboard/officer-queue` | any | Revenue Officer queue (`?risk=flagged\|all`, default flagged) |
| GET    | `/api/dashboard/export.csv` | any | CSV export (`?status=`, `?district=`) |
| GET    | `/api/dashboard/user-activity` | ADMIN | Per-user activity summary          |
| GET    | `/api/search?q=`        | any   | Search by owner, survey, khasra, khata, village, tehsil, district |
| GET    | `/api/audit`            | any   | System-wide audit log (optional `?action=` filter) |

## Example: full pipeline via curl

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"Operator@123"}' | jq -r .access_token)

DOC=$(curl -s -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@backend/sample_data/english_land_record.png")

DOC_ID=$(echo $DOC | jq -r .id)

RECORD=$(curl -s -X POST http://localhost:8000/api/documents/$DOC_ID/process \
  -H "Authorization: Bearer $TOKEN")

echo $RECORD | jq
```
