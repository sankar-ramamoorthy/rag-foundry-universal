# rag_orchestrator/src/api/v1/models.py (UPDATED)
from typing import List, Literal, Optional, Dict, Any

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
    # WP-S8: optional cross-encoder reranker. None = use the deployment's
    # RERANK_ENABLED default; explicit True/False overrides per-request,
    # so the same deployment can serve an A/B comparison without a
    # redeploy.
    rerank: Optional[bool] = None


class RAGResponse(BaseModel):  # Updated name
    answer: str
    sources: List[str]
    repo_id: str  # NEW
    retrieval_plan: Dict[str, Any]  # NEW: Graph expansion details
    # WP-M5: which model actually answered (incl. WP-M2 fallbacks)
    model_used: Optional[str] = None
    model_alias: Optional[str] = None
    fallback_from: Optional[str] = None
    # WP-T1b: one ID connecting every retrieval-pipeline stage-event log
    # line for this request.
    trace_id: Optional[str] = None
    # WP-S8: whether the reranker actually ran for this response.
    reranked: bool = False


class SearchQuery(BaseModel):
    question: str
    top_k: int = 5


class SimpleRAGQuery(BaseModel):
    query: str
    repo_id: Optional[str] = None  # NEW: Repo selection
    top_k: int = 5
    provider: Optional[str] = None
    model: Optional[str] = None
    # WP-S8: see RAGQuery.rerank -- same override semantics.
    rerank: Optional[bool] = None


class SimpleRAGResponse(BaseModel):  # Updated name
    final_context_manifest: List[Dict[str, Any]] = []
    answer: str
    sources: List[str]
    # WP-M5: which model actually answered (incl. WP-M2 fallbacks)
    model_used: Optional[str] = None
    model_alias: Optional[str] = None
    fallback_from: Optional[str] = None
    # WP-S8: whether the reranker actually ran for this response.
    reranked: bool = False


# --- TRACE / IMPACT (issue #198) ---


class ResolvedStartModel(BaseModel):
    canonical_id: str
    file_path: str


class HopModel(BaseModel):
    canonical_id: str
    file_path: str
    hop_index: int
    relation_type: str
    parent_canonical_id: str
    # Issue #220: confidence/call_sites/bases/etc when the underlying
    # edge carried relationship_metadata; {} otherwise.
    metadata: Dict[str, Any] = {}


class GapNoteModel(BaseModel):
    canonical_id: str
    reason: str


class TraceResponse(BaseModel):
    repo_id: str
    resolved_start: ResolvedStartModel
    relation_types: List[str]
    direction: str
    max_depth: int
    hops: List[HopModel]
    truncated: bool
    depth_limited: bool
    gaps: List[GapNoteModel]


class ImpactBasisModel(BaseModel):
    relation_type: str
    hop_distance: int
    path: List[str]
    # Issue #220: see HopModel.metadata.
    metadata: Dict[str, Any] = {}


class ImpactCandidateModel(BaseModel):
    canonical_id: str
    file_path: str
    basis: List[ImpactBasisModel]


class ImpactResponse(BaseModel):
    repo_id: str
    resolved_start: ResolvedStartModel
    relation_types_considered: List[str]
    max_depth: int
    candidates: List[ImpactCandidateModel]
    truncated: bool


# --- Issue #200, Stage A3: bounded evidence-sufficiency workflow ---


class EvidenceRequest(BaseModel):
    mode: Literal["orient", "trace", "impact"]
    # TRACE/IMPACT: a canonical_id or bare symbol name (see
    # resolve_start_symbol). Required for those modes, rejected for ORIENT.
    start: Optional[str] = None
    # TRACE only. None -> {"CALL"}, matching the existing GET /trace default.
    relation_types: Optional[List[str]] = None
    # TRACE only.
    direction: str = "forward"
    # TRACE/IMPACT only. None -> the mode's server ceiling
    # (settings.TRACE_MAX_DEPTH / IMPACT_MAX_DEPTH).
    max_depth: Optional[int] = None
    # ORIENT only: which structural-inventory facets are required for
    # this request to be sufficient (e.g. ["services", "manifests"]).
    required_facets: Optional[List[str]] = None
    # TRACE only: a canonical_id the traversal must reach for the
    # request to be sufficient. Without it, TRACE only obligates a
    # resolved start (see evidence_sufficiency.assess_trace).
    required_target: Optional[str] = None
    # Stage A4, all modes: when set, one /generate call explains the
    # finalized evidence (see evidence_service._generate_evidence_
    # explanation). Omitted -> no generation, structured evidence only.
    explanation_query: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class EvidenceItemModel(BaseModel):
    identity: str
    kind: str
    supporting: Optional[str] = None


class ExplanationModel(BaseModel):
    answer: Optional[str] = None
    model_used: Optional[str] = None
    model_alias: Optional[str] = None
    fallback_from: Optional[str] = None
    skipped_reason: Optional[str] = None


class EvidenceAssessmentModel(BaseModel):
    policy_version: str
    status: Literal["satisfied", "partial", "needs_clarification"]
    obligations: Dict[str, str]
    reason_codes: List[str]
    evidence: List[EvidenceItemModel]
    missing_obligations: List[str]


class EvidenceStepModel(BaseModel):
    action: str
    reason: str
    outcome: str


class EvidenceResponse(BaseModel):
    repo_id: str
    mode: str
    assessment: EvidenceAssessmentModel
    steps: List[EvidenceStepModel]
    stop_reason: str
    explanation: Optional[ExplanationModel] = None
