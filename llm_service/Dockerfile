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

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI app
CMD ["uv", "run", "--directory", "/app/llm_service", \
     "uvicorn", "src.api.v1.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]

#CMD ["uvicorn", "src.api.v1.main:app", "--host", "0.0.0.0", "--port", "8000"]
