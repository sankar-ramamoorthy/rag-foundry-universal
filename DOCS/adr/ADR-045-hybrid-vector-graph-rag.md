## **DOCS\adr\ADR-045-hybrid-vector-graph-rag.md*

***

# **ADR-045: Hybrid Vector+Graph RAG Pipeline with Repo Selection**

**Status:** Proposed  
**Date:** 2026-02-20  
**Deciders:** Platform Architecture Team  
**Supersedes:** None  
**Related:** ADR-030 (Unified Artifact Graph), ADR-044 (Shared Graph Models)

***

## **Context**

The platform has evolved from document-only RAG to a **unified artifact graph** capable of representing code entities, documents, and ADRs with rich relationships (`CALL`, `DEFINES`, `IMPORT`). 

**Current Capabilities:**
- Vector search over chunked content ✓
- Unified graph storage (`DocumentNode`, `DocumentRelationship`) ✓
- In-memory `CodebaseGraph` traversal utilities ✓
- `RetrievalPlan` abstraction ready for expansion ✓

**Gap:** No integration between semantic vector search and structural graph traversal.

**User Need:** Answer queries like `"methods in math_utils.py"` by combining:
1. **Semantic retrieval** → find relevant starting points (`math_utils.py`)
2. **Structural traversal** → expand to all methods via `DEFINES` relationships

***

## **Decision**

Implement a **hybrid vector+graph RAG pipeline** that:

1. **Repo Selection:** Query parameter + `/v1/repos` API + Gradio dropdown UX
2. **Seed Selection:** Vector search (`doc_type="code"`) → extract `canonical_id`
3. **Graph Expansion:** Keyword-driven traversal strategy selection
4. **Unified Retrieval:** `canonical_id` → `document_id` → chunks → existing pipeline
5. **Preserve Existing Pipeline:** No changes to `execute_retrieval_plan`, `agent_adapter`, etc.

***

## **Detailed Design**

### **1. Repo Resolution (No Hardcoding)**

```
Frontend (Gradio):              Backend (service.py):
┌─────────────────────────────┐  ┌──────────────────────────┐
│ Repo: [Payments ▼]          │  │ repo_id = repo_name_to_id│
│ Query: "methods..."         │──┤     ["payments"]        │
└─────────────────────────────┘  │ → "123e4567..."          │
                                 └──────────────────────────┘
```

**ingestion_service API:**
```
GET /v1/repos → [
  {
    "id": "123e4567...",
    "name": "payments-service", 
    "display_name": "Payments Service",
    "status": "completed",
    "file_count": 42
  }
]
```

**RAG Request:**
```
POST /v1/rag
{
  "query": "methods in math_utils.py",
  "repo_id": "123e4567...",  // From dropdown
  "top_k": 5
}
```

### **2. End-to-End Data Flow**

```
"methods in math_utils.py"
       ↓
1. repo_id = request.repo_id ✓ (dropdown)
2. query_embedding = embed_query(query) ✓
3. code_chunks = vector_search(
     query_embedding, 
     metadata_filter={"doc_type": "code"},
     top_k=5
   ) ✓
       ↓
4. seed_canonical_ids = {
     chunk.metadata["canonical_id"] 
     → {"math_utils.py", "math_utils.py#add"}
   }
       ↓
5. strategy = select_traversal_strategy(query)
   → [traverse_defines]  ("methods" keyword)
       ↓
6. graph = get_cached_graph(repo_id)  // In-memory
7. expanded_nodes = traverse_defines(graph, "math_utils.py")
   → [method1_node, method2_node, ...]
       ↓
8. all_canonical_ids = seed + expanded
9. document_ids = canonical_ids_to_document_ids(all_canonical_ids)
10. chunks = fetch_chunks_for_documents(document_ids)
       ↓
[EXISTING PIPELINE UNCHANGED ✓]
11. RetrievalPlan → execute → agent_chunks → LLM
```

### **3. New Components**

```
src/core/config.py:
├── DEFAULT_REPO_ID (fallback)

src/retrieval/codebase_utils.py:
├── canonical_ids_to_document_ids(repo_id, canonical_ids) → Set[document_id]
├── get_cached_graph(repo_id) → CodebaseGraph

src/retrieval/traversal_selector.py:
├── select_traversal_strategies(query) → List[Callable]

rag_orchestrator/src/core/service.py:
├── resolve_repo_id(request_repo_id, query) → str
└── Updated run_rag() orchestration
```

***

## **Rationale**

### **Why Query Param + Repo List API?**

**Rejected Alternatives:**
```
❌ Hardcoded repo_id: Breaks multi-repo future, manual config
❌ UUID textbox: Users can't remember "123e4567..."
❌ LLM router: Adds latency/cost to every query (future M2)
```

**Selected:**
```
✅ Dropdown UX: Human-readable repo names
✅ Explicit control: User selects repo context
✅ Future-proof: Same API works for multi-repo + LLM routing
✅ Zero runtime cost: No extra LLM calls
```

### **Why Vector → Canonical ID?**
```
✅ Leverages existing vector pipeline
✅ canonical_id already in chunk metadata
✅ Handles semantic variations ("utils module", "math utils functions")
✅ No new DB queries for seeds
```

### **Why Keyword Traversal Selection?**
```
✅ Deterministic (no LLM cost)
✅ Covers 80% use cases: "methods in", "what calls", "what does X call"
✅ Easy to extend/debug
✅ Path to LLM strategy selection (M2)
```

***

## **Implementation Plan**

### **Phase 1: ingestion_service**
```
1. Add GET /v1/repos endpoint
2. Query distinct(repo_id) + ingestion status
3. Return human-readable metadata
```

### **Phase 2: Gradio UI**
```
1. Add repo dropdown + refresh button
2. Pass selected repo_id to /v1/rag
3. Auto-select most recent complete repo
```

### **Phase 3: rag_orchestrator**
```
1. resolve_repo_id() with fallbacks
2. canonical_ids_to_document_ids() utility
3. get_cached_graph() (in-memory)
4. traversal_selector.py (keyword rules)
5. service.py orchestration
```

### **Phase 4: Test**
```
✅ "methods in math_utils.py" → all DEFINES relationships
✅ "what calls add()" → incoming CALL edges  
✅ Existing doc queries still work (vector-only)
✅ RetrievalPlan.expansion_metadata populated
```

***

## **Consequences**

### **Positive**
- **Immediate Value:** Graph-aware code queries work out-of-box
- **Preserves Abstractions:** Existing pipeline unchanged
- **Scalable:** Same API supports multi-repo evolution
- **Observable:** `RetrievalPlan.to_dict()` shows expansion paths
- **User-Friendly:** Dropdown UX, no UUID memorization

### **Negative**
- Requires ingestion_service `/v1/repos` endpoint
- Gradio UI changes needed
- Single in-memory graph cache (service restart = reload)

### **Neutral**
- Vector store must support `metadata_filter`
- Keyword rules need periodic tuning

***

## **Alternatives Considered**

### **Alternative 1: Hardcoded Repo ID**
```
❌ Manual config after ingestion
❌ Breaks multi-repo future
❌ No UX for repo selection
```

### **Alternative 2: LLM Router**
```
⚠️ Adds latency/cost to every query
⚠️ Non-deterministic
✅ Future direction (M2)
```

### **Alternative 3: Query Parsing Only**
```
❌ File-based only (no repo awareness)
❌ Brittle regex patterns
```

***

## **Risks & Mitigations**

```
Risk: Vector store lacks metadata_filter
Mitigation: Fallback to all chunks → client-side doc_type filter

Risk: No repos ingested
Mitigation: resolve_repo_id() raises clear error + Gradio guidance

Risk: Graph cache memory pressure
Mitigation: Single repo + lazy loading (M1 scope)
```

***

## **Success Criteria**

```
✅ [ ] GET /v1/repos returns repo metadata
✅ [ ] Gradio dropdown shows "Payments Service (complete)"  
✅ [ ] "methods in math_utils.py" → lists all methods via DEFINES
✅ [ ] "what calls add()" → incoming CALL edges
✅ [ ] Existing document queries unchanged
✅ [ ] RetrievalPlan.expansion_metadata populated
✅ [ ] Sources trace to correct document_id
```

***

## **Future Evolution**

```
M2: LLM-powered traversal strategy selection
M3: Multi-repo federated search  
M4: Redis-backed graph cache
M5: Query rewriting for cross-repo reasoning
M6: GraphRAG-style community summarization
```

***

## **Final Position**

**We adopt the Hybrid Vector+Graph RAG pipeline with Repo Selection via Query Parameter + Repo List API.**

This decision:
- Delivers immediate graph-aware code intelligence
- Preserves all existing RAG abstractions  
- Provides clear multi-repo evolution path
- Maintains excellent Gradio UX
- Aligns with ADR-030/044 unified graph architecture

***

# **End of ADR-045**

***

