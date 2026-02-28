from fastapi import FastAPI
from src.api.v1.routes import router

app = FastAPI(title="RAG Orchestrator")

app.include_router(router, prefix="/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}
