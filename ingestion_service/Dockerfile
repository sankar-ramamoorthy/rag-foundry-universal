# Base image: Python 3.12 with uv support
FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Copy shared + service code
COPY shared /app/shared
COPY ingestion_service /app/ingestion_service

# Copy Alembic config + migrations
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations

# System dependencies for tree-sitter and other tools
RUN apt-get update && \
    apt-get install -y \
        postgresql-client \
        tesseract-ocr \
        curl \
        build-essential \
        git \
        python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies from pyproject.toml using uv
RUN uv sync

# Set PYTHONPATH for service and shared code
ENV PYTHONPATH=/app:/app/shared

# Expose ingestion service port
EXPOSE 8000

# Default command to run the ingestion service
CMD ["uv", "run", "--directory", "/app/ingestion_service", \
     "uvicorn", "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
