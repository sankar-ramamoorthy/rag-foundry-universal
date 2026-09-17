from fastapi import FastAPI
from shared.runtime_provenance import install_version_route
from src.api.v1.routes import router

app = FastAPI(title="RAG Orchestrator")
install_version_route(app, "rag_orchestrator")

app.include_router(router, prefix="/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}
