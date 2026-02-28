# rag_orchestrator/Dockerfile
FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync

# Copy the package source
COPY rag_orchestrator/ ./rag_orchestrator/

# Set PYTHONPATH so imports work in Docker
ENV PYTHONPATH=/app:/app/rag_orchestrator

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI app
CMD ["uv", "run", "--directory", "/app/rag_orchestrator", \
     "uvicorn", "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
