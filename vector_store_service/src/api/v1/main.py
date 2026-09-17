from fastapi import FastAPI
from shared.runtime_provenance import install_version_route
from src.api.v1 import ingestions, vectors

app = FastAPI(title="Vector Store Service")
install_version_route(app, "vector_store_service")

app.include_router(ingestions.router)
app.include_router(vectors.router)


# ✅ Health check endpoint for Docker
@app.get("/health")
def health_check():
    return {"status": "ok"}
