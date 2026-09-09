FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy minimal pyproject.toml — no Docling, no PyTorch
COPY gradio/pyproject.toml ./pyproject.toml
COPY shared /app/shared

# Copy gradio app from its actual location
COPY ingestion_service/src/ui/gradio_app.py /app/gradio_app.py

RUN uv sync --no-dev

ENV API_BASE_URL=http://ingestion_service:8000
ENV RAG_API_BASE_URL=http://rag_orchestrator:8000
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

EXPOSE 7860

CMD ["uv", "run", "python", "/app/gradio_app.py"]
