"""
Central service URL configuration.
All inter-service URLs for Docker internal networking.
Import this anywhere a service needs to call another service.
"""

import os

# Internal Docker network URLs (container-to-container)
INGESTION_SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", "http://ingestion_service:8000")
VECTOR_STORE_URL      = os.getenv("VECTOR_STORE_URL",      "http://vector_store_service:8002")
LLM_SERVICE_URL       = os.getenv("LLM_SERVICE_URL",       "http://llm_service:8000")
RAG_ORCHESTRATOR_URL  = os.getenv("RAG_ORCHESTRATOR_URL",  "http://rag_orchestrator:8000")