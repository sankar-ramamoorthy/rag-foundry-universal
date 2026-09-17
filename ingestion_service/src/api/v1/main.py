from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import threading
from src.core.database_session import get_engine
from src.core.ingestion_ownership import reconcile_ingestions
from src.core.ingestion_jobs import recovery_loop
from shared.runtime_provenance import install_version_route

from src.api.health import router as health_router
from src.api.v1 import router as v1_router
from src.api.errors import register_error_handlers

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(reconcile_ingestions, get_engine())
    stop = threading.Event()
    recovery = threading.Thread(
        target=recovery_loop, args=(stop,), daemon=True, name="ingestion-recovery",
    )
    recovery.start()
    try:
        yield
    finally:
        stop.set()
        await asyncio.to_thread(recovery.join, 2)


# Register handlers before routers
app = FastAPI(title="Rag Foundry"  ,  docs_url="/docs",  # ← ADD THIS
    redoc_url="/redoc",
    lifespan=lifespan,
)

register_error_handlers(app)
install_version_route(app, "ingestion_service")

app.include_router(health_router)
app.include_router(v1_router)


@app.get("/")
def root():
    return {"service": "rag-ingestion"}
