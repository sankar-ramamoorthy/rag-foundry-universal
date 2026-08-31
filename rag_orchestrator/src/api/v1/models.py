# rag_orchestrator/src/api/v1/models.py (UPDATED)
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

class RAGQuery(BaseModel):
    query: str
    repo_id: Optional[str] = None  # NEW: Repo selection
    top_k: int = 5
    provider: Optional[str] = None
    model: Optional[str] = None
    # WP-L6a (#85): optional language scope (python/typescript/javascript).
    # Omitted = today's unfiltered, all-languages behavior, unchanged.
    language: Optional[str] = None

class RAGResponse(BaseModel):  # Updated name
    answer: str
    sources: List[str]
    repo_id: str  # NEW
    retrieval_plan: Dict[str, Any]  # NEW: Graph expansion details
    # WP-M5: which model actually answered (incl. WP-M2 fallbacks)
    model_used: Optional[str] = None
    model_alias: Optional[str] = None
    fallback_from: Optional[str] = None

class SearchQuery(BaseModel):
    question: str
    top_k: int = 5

class SimpleRAGQuery(BaseModel):
    query: str
    repo_id: Optional[str] = None  # NEW: Repo selection
    top_k: int = 5
    provider: Optional[str] = None
    model: Optional[str] = None

class SimpleRAGResponse(BaseModel):  # Updated name
    answer: str
    sources: List[str]
    # WP-M5: which model actually answered (incl. WP-M2 fallbacks)
    model_used: Optional[str] = None
    model_alias: Optional[str] = None
    fallback_from: Optional[str] = None
