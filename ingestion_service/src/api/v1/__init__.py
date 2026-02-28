# ingestion_service/src/api/v1/__init__.py (ADD GRAPH ROUTER)
from fastapi import APIRouter

from src.api.v1.ingest import router as ingest_router
from src.api.v1.summary import router as ingest_summary
from src.api.v1.codebase_ingest import router as codebase_ingest_router
from src.api.v1.repos import router as repos_router
from src.api.v1.graph import router as graph_router  # NEW

router = APIRouter(prefix="/v1")

router.include_router(ingest_router)
router.include_router(ingest_summary)
router.include_router(codebase_ingest_router)
router.include_router(repos_router)
router.include_router(graph_router)  # NEW
