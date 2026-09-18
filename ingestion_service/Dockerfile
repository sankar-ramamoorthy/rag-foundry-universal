# Base image: Python 3.12 with uv support
FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Root project: only used to put the `alembic` CLI on PATH (ingestion_service
# is the only service that owns DB access/migrations). Not what the app
# server runs -- see the service project below.
COPY pyproject.toml uv.lock ./
ENV UV_HTTP_TIMEOUT=120
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --no-dev

# Service project: this is what actually runs (Docling/torch/tree-sitter
# live here, not in the root project above). Baked into the image at build
# time and invoked directly by CMD below (issue #41) -- previously CMD ran
# `uv run --directory /app/ingestion_service`, which resolved this project
# from scratch on every container start/recreation, downloading multi-GB
# Docling/torch/CUDA wheels each time. Copying just the dependency files
# first (before the full service COPY below) keeps this layer cached
# across code-only changes.
COPY ingestion_service/pyproject.toml ingestion_service/uv.lock /app/ingestion_service/
RUN cd /app/ingestion_service && uv sync --no-dev

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

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ARG RELEASE_VERSION=dev

ENV APP_GIT_SHA=${GIT_SHA} \
    APP_BUILD_DATE=${BUILD_DATE} \
    APP_RELEASE_VERSION=${RELEASE_VERSION}

LABEL org.opencontainers.image.source="https://github.com/sankar-ramamoorthy/rag-foundry-universal" \
      org.opencontainers.image.url="https://github.com/sankar-ramamoorthy/rag-foundry-universal" \
      org.opencontainers.image.title="rag-foundry-universal" \
      org.opencontainers.image.description="Graph-aware RAG system for code repositories and documents" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${RELEASE_VERSION}"

EXPOSE 8000

WORKDIR /app/ingestion_service
CMD ["/app/ingestion_service/.venv/bin/python", "-m", "uvicorn", \
     "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
