from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/v1/ingestions")


class IngestionCreate(BaseModel):
    ingestion_id: str
    source_type: str
    metadata: dict


@router.post("")
async def create_ingestion(request: IngestionCreate):
    # TODO: persist in Postgres
    return {"status": "ok", "ingestion_id": request.ingestion_id}
