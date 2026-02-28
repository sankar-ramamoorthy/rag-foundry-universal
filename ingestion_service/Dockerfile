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

# System dependencies
RUN apt-get update && \
    apt-get install -y \
        postgresql-client \
        tesseract-ocr \
        curl \
        build-essential \
        git \
        python3-dev \
        libgl1 \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# IS2: Install Python dependencies with CPU-only PyTorch
# --no-dev excludes ruff/pre-commit/pyright (dev tools, not needed in image)
# --extra-index-url ensures torch installs CPU variant
ENV UV_HTTP_TIMEOUT=120
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --no-dev --extra-index-url https://download.pytorch.org/whl/cpu

# Pre-download Docling models at build time
# Avoids slow first-run download when a document is first ingested
# Models cached at /root/.cache/docling/
# IS2: Pre-download Docling models at build time
#RUN /app/.venv/bin/python -c "\
#from docling.document_converter import DocumentConverter; \
#print('Downloading Docling models...'); \
#DocumentConverter(); \
#print('Docling models ready.')"

# Set PYTHONPATH for service and shared code
ENV PYTHONPATH=/app:/app/shared

# Docling model cache location (explicit for clarity)
ENV DOCLING_CACHE_DIR=/root/.cache/docling

EXPOSE 8000

CMD ["uv", "run", "--directory", "/app/ingestion_service", \
     "uvicorn", "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]