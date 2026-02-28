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

EXPOSE 8002

# Run FastAPI app
CMD ["uv", "run", "--directory", "/app/vector_store_service", \
     "uvicorn", "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8002"]
