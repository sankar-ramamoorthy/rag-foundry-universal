# ingestion_service/src/api/v1/summary.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from uuid import UUID

from src.core.database_session import get_sessionmaker
from shared.models.document_node import DocumentNode

SessionLocal = get_sessionmaker()
router = APIRouter(tags=["summary"])

# -----------------------------
# Request model
# -----------------------------
class SummaryPayload(BaseModel):
    ingestion_id: str
    summary: str

# -----------------------------
# POST /summary
# -----------------------------
@router.post("/summary")
def save_summary(payload: SummaryPayload):
    try:
        uid = UUID(payload.ingestion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ingestion_id")

    with SessionLocal() as session:
        doc = session.query(DocumentNode).filter_by(
            source=f"file_document_{payload.ingestion_id}"
        ).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        doc.summary = payload.summary
        session.commit()

    return {"status": "summary_saved"}
