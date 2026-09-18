# llm_service/Dockerfile
FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Service project: baked into the image at build time and invoked directly
# by CMD below (issue #41) -- previously this synced the unrelated *root*
# project here, then CMD ran `uv run --directory /app/llm_service`, which
# resolved the real (llm_service) project from scratch on every container
# start/recreation instead of using anything built into the image. Copying
# just the dependency files first keeps this layer cached across code-only
# changes.
COPY llm_service/pyproject.toml llm_service/uv.lock /app/llm_service/
RUN cd /app/llm_service && uv sync

# Copy the package source
COPY shared /app/shared
COPY llm_service/ ./llm_service/

# Set PYTHONPATH so imports work in Docker
ENV PYTHONPATH=/app:/app/llm_service

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

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI app
WORKDIR /app/llm_service
CMD ["/app/llm_service/.venv/bin/python", "-m", "uvicorn", \
     "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
