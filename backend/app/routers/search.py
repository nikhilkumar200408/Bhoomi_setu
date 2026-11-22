from typing import List

from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..database import records_collection
from ..deps import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])

SEARCHABLE_FIELDS = ["owner_name", "survey_number", "khasra_number", "khata_number", "village", "tehsil", "district"]


@router.get("", response_model=List[schemas.SearchResultItem])
async def search(q: str = Query(..., min_length=1), user: dict = Depends(get_current_user)):
    cursor = records_collection.find(
        {
            "fields": {
                "$elemMatch": {
                    "field_name": {"$in": SEARCHABLE_FIELDS},
                    "value": {"$regex": q, "$options": "i"},
                }
            }
        }
    )

    results: List[schemas.SearchResultItem] = []
    async for record in cursor:
        field_map = {f["field_name"]: f["value"] for f in record["fields"]}
        results.append(
            schemas.SearchResultItem(
                record_id=record["_id"],
                document_id=record["document_id"],
                owner_name=field_map.get("owner_name"),
                survey_number=field_map.get("survey_number"),
                khasra_number=field_map.get("khasra_number"),
                khata_number=field_map.get("khata_number"),
                village=field_map.get("village"),
                tehsil=field_map.get("tehsil"),
                district=field_map.get("district"),
                status=record["status"],
                overall_confidence=record["overall_confidence"],
            )
        )
    return results
