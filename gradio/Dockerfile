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

EXPOSE 7860

CMD ["uv", "run", "python", "/app/gradio_app.py"]