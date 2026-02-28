from fastapi import FastAPI
from src.api.v1 import ingestions, vectors

app = FastAPI(title="Vector Store Service")

app.include_router(ingestions.router)
app.include_router(vectors.router)


# ✅ Health check endpoint for Docker
@app.get("/health")
def health_check():
    return {"status": "ok"}
