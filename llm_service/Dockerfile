# llm_service/Dockerfile
FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync

# Copy the package source
COPY llm_service/ ./llm_service/

# Set PYTHONPATH so imports work in Docker
ENV PYTHONPATH=/app:/app/llm_service

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

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI app
CMD ["uv", "run", "--directory", "/app/llm_service", \
     "uvicorn", "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]

#CMD ["uvicorn", "src.api.v1.main:app", "--host", "0.0.0.0", "--port", "8000"]
