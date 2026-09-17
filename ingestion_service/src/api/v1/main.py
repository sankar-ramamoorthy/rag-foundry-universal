from fastapi import FastAPI
from shared.runtime_provenance import install_version_route

from src.api.health import router as health_router
from src.api.v1 import router as v1_router
from src.api.errors import register_error_handlers

# Register handlers before routers
app = FastAPI(title="Rag Foundry"  ,  docs_url="/docs",  # ← ADD THIS
    redoc_url="/redoc",
)

register_error_handlers(app)
install_version_route(app, "ingestion_service")

app.include_router(health_router)
app.include_router(v1_router)


@app.get("/")
def root():
    return {"service": "rag-ingestion"}
