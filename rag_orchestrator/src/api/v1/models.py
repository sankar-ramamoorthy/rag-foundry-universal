# rag_orchestrator/src/api/v1/models.py (UPDATED)
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

class RAGQuery(BaseModel):
    query: str
    repo_id: Optional[str] = None  # NEW: Repo selection
    top_k: int = 5
    provider: Optional[str] = None
    model: Optional[str] = None

class RAGResponse(BaseModel):  # Updated name
    answer: str
    sources: List[str]
    repo_id: str  # NEW
    retrieval_plan: Dict[str, Any]  # NEW: Graph expansion details

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
