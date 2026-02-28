FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy ONLY the ingestion service project metadata
COPY ingestion_service/pyproject.toml ingestion_service/uv.lock ./ingestion_service/

# Copy source code
COPY ingestion_service /app/ingestion_service
COPY shared /app/shared

# Install UI dependencies FROM ingestion_service project
WORKDIR /app/ingestion_service
RUN uv sync --extra ui --no-dev

ENV API_BASE_URL=http://ingestion_service:8000
ENV RAG_API_BASE_URL=http://rag_orchestrator:8000
ENV PYTHONPATH=/app:/app/shared

CMD ["uv", "run", "--directory", "/app/ingestion_service", "-m", "src.ui.gradio_app"]
