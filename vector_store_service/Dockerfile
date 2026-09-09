FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock ./

# Copy shared + service code
COPY shared /app/shared
COPY vector_store_service /app/vector_store_service
# Copy alembic config + migrations
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations


# System dependencies
RUN apt-get update && \
    apt-get install -y postgresql-client tesseract-ocr && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies from repo root
RUN uv sync

# Ensure imports work across services
ENV PYTHONPATH=/app:/app/shared

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ARG RELEASE_VERSION=dev

LABEL org.opencontainers.image.source="https://github.com/sankar-ramamoorthy/rag-foundry-universal" \
      org.opencontainers.image.url="https://github.com/sankar-ramamoorthy/rag-foundry-universal" \
      org.opencontainers.image.title="rag-foundry-universal" \
      org.opencontainers.image.description="Graph-aware RAG system for code repositories and documents" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${RELEASE_VERSION}"

EXPOSE 8002

# Run FastAPI app
CMD ["uv", "run", "--directory", "/app/vector_store_service", \
     "uvicorn", "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8002"]
