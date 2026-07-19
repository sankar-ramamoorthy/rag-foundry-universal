
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                          REPO QUERY - FULL DATA FLOW                                     ║
║                    (Gradio UI → RAG Orchestrator → Services)                             ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  BROWSER / GRADIO UI                                                                     │
│  ingestion_service/src/ui/gradio_app.py                                                  │
│                                                                                           │
│  1a. demo.load() fires on page load          1b. User clicks "Refresh Repos"             │
│       └── refresh_repos()                         └── refresh_repos()                    │
│               │                                                                           │
│               └── GET http://ingestion_service:8001/v1/repos                             │
│                       │                                                                   │
│                       ▼                                                                   │
│               ← List[RepoSummary]                                                         │
│               → populates repo_dropdown                                                   │
│                                                                                           │
│  2. User selects repo, enters query, clicks "Ask Graph RAG"                              │
│       └── submit_rag_query(query, repo_id, top_k, provider, model)                       │
│               │                                                                           │
│               └── POST http://rag_orchestrator:8004/v1/rag                               │
│                       body: {query, repo_id, top_k, provider, model}                     │
└───────────────────────────────────┬─────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  RAG ORCHESTRATOR  :8004                                                                  │
│  rag_orchestrator/src/core/service.py  →  run_rag()                                      │
│                                                                                           │
│  STEP 1: RESOLVE REPO                                                                     │
│  resolve_repo_id_http(repo_id)                                                            │
│       └── GET ingestion_service:8001/v1/repos                                             │
│               │                                                                           │
│               ▼  [ingestion_service]                                                      │
│               repos.py router → db_utils.list_complete_repos()                            │
│               → JOIN DocumentNode + IngestionRequest WHERE status='complete'              │
│               → COUNT nodes, COUNT distinct files                                         │
│               ← List[RepoSummary]                                                         │
│               │                                                                           │
│               ▼  [back in rag_orchestrator]                                               │
│               validate repo_id exists & is complete                                       │
│               → resolved_repo_id                                                          │
│                                                                                           │
│  STEP 2: EMBED QUERY                                                                      │
│  embed_query(query, embedder)                                                             │
│       └── local embedder (Ollama or configured provider)                                  │
│               ← query_embedding: List[float]                                              │
│                                                                                           │
└───────────────────────────────────┬─────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  hybrid_retrieve()  [service.py]                                                          │
│                                                                                           │
│  STEP 3: VECTOR SEARCH                                                                    │
│       └── POST vector_store:8003/v1/vectors/search                                        │
│               body: {query_vector, k, metadata_filter: {doc_type: "code"}}               │
│               (falls back without metadata_filter if no results)                          │
│               ← [{chunk_id, text, score, document_id, metadata:{canonical_id,...}}]      │
│               → seed_chunks: List[RetrievedChunk]                                         │
│               → seed_canonical_ids = extract_canonical_ids_from_chunks(seed_chunks)      │
│                    └── reads chunk.metadata["canonical_id"] for each chunk               │
│                                                                                           │
│  STEP 4: LOAD / FETCH GRAPH  (if seed_canonical_ids not empty)                           │
│  get_cached_graph(repo_id)  [codebase_utils.py]                                           │
│       │                                                                                   │
│       ├── HIT:  return _repo_graphs[repo_id]  (in-memory cache)                          │
│       │                                                                                   │
│       └── MISS: load_graph_for_repo(repo_id)  [codebase_queries.py]                      │
│                   │                                                                        │
│                   └── GET ingestion_service:8001/v1/graph/repos/{repo_id}                │
│                           │                                                                │
│                           ▼  [ingestion_service]                                          │
│                           graph.py router                                                 │
│                           → db_utils.get_full_graph_for_repo(repo_id)                    │
│                               ├── SELECT * FROM document_nodes WHERE repo_id=?           │
│                               └── SELECT * FROM document_relationships WHERE repo_id=?   │
│                           ← {                                                             │
│                               "nodes": {canonical_id → node_dict},                       │
│                               "relationships": {from_cid → [{to_cid, relation_type}]}    │
│                             }                                                             │
│                           │                                                               │
│                           ▼  [back in rag_orchestrator]                                   │
│                           build CodebaseGraph in memory:                                  │
│                           ├── for each node → Node(canonical_id, file_path, lineno)      │
│                           └── for each edge → graph.add_edge(from, to, relation_type)    │
│                               sets Node.out_edges and Node.in_edges                       │
│                           → cached in _repo_graphs[repo_id]                              │
│                                                                                           │
│  STEP 5: GRAPH TRAVERSAL                                                                  │
│  select_traversal_strategies(query, seed_canonical_ids)  [traversal_selector.py]         │
│       └── keyword match on query:                                                         │
│               "method/function/class/in" → [traverse_defines(depth=1)]                   │
│               "callers/called by"        → [traverse_incoming_calls(depth=1)]             │
│               "calls/call"               → [traverse_calls(depth=1)]                      │
│               "import"                   → [traverse_incoming_imports(depth=1)]           │
│               default                    → [traverse_defines, traverse_calls]             │
│                                                                                           │
│  execute_traversals(graph, start_cid, strategies)  [traversal_selector.py]               │
│       └── for each strategy:                                                              │
│               bfs_traversal(graph, start_cid, ...)  [codebase_queries.py]                │
│               ├── traverse_calls()           CALL edges,   forward,  BFS                 │
│               ├── traverse_defines()         DEFINES edges,forward,  BFS                 │
│               ├── traverse_incoming_calls()  CALL edges,   reverse,  BFS                 │
│               └── traverse_incoming_imports()IMPORT edges, reverse,  BFS                 │
│               ← List[Node]  (deduplicated by canonical_id)                               │
│               → expanded_canonical_ids                                                    │
│                                                                                           │
│  STEP 6: RESOLVE ALL CANONICAL IDS → DOCUMENT IDS                                        │
│  canonical_to_document_map_http(repo_id, seed_cids ∪ expanded_cids) [service.py]        │
│       └── GET ingestion_service:8001/v1/graph/repos/{repo_id}/nodes                      │
│               params: canonical_ids=cid1,cid2,...                                         │
│               │                                                                            │
│               ▼  [ingestion_service]                                                       │
│               graph.py router                                                             │
│               → db_utils.get_document_nodes_by_canonical_ids(repo_id, canonical_ids)     │
│               → SELECT * FROM document_nodes                                              │
│                   WHERE repo_id=? AND canonical_id IN (...)                               │
│               ← [{document_id, canonical_id, ...}]                                        │
│               │                                                                            │
│               ▼  [back in rag_orchestrator]                                               │
│               → all_document_ids: Set[str]                                                │
│               → missing_doc_ids = all_document_ids - seed_doc_ids                        │
│                                                                                           │
│  STEP 7: FETCH CHUNKS FOR EXPANDED DOCS                                                   │
│       └── for each doc_id in missing_doc_ids:                                             │
│               POST vector_store:8003/v1/vectors/search-by-doc                             │
│               body: {document_id, k=10}                                                   │
│               ← [{chunk_id, text, score}]                                                 │
│               → appended to retrieved_chunks_by_document                                  │
│                                                                                           │
│               ← retrieved_chunks_by_document: Dict[doc_id → List[RetrievedChunk]]        │
│               ← retrieval_plan_dict: {seed_cids, expanded_cids, doc counts}              │
│                                                                                           │
└───────────────────────────────────┬─────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  BACK IN run_rag()  [service.py]                                                          │
│                                                                                           │
│  STEP 8: PLAN + RANK CHUNKS                                                               │
│  execute_retrieval_plan(plan, retrieved_chunks_by_document)  [execute_plan.py]            │
│       └── applies RetrievalPlan constraints, ordering, dedup                             │
│           ← ranked List[RetrievedChunk]                                                   │
│                                                                                           │
│  STEP 9: PREPARE FOR LLM                                                                  │
│  prepare_chunks_for_agent(...)  [agent_adapter.py]                                        │
│       └── apply max_chunks_per_doc, filter_chunk fn, ordering                            │
│           ← agent_chunks: List[Dict]                                                      │
│                                                                                           │
│  STEP 10: TOKEN BUDGET                                                                    │
│       └── walk agent_chunks, accumulate token count (word-based approximation)           │
│           stop when > max_total_tokens (default 4096)                                     │
│           → context_str: str                                                              │
│                                                                                           │
│  STEP 11: LLM CALL                                                                        │
│       └── POST llm_service/generate                                                       │
│               body: {context: context_str, query: query}                                  │
│               params: {provider, model}  (if provided)                                    │
│               ← {response: "...answer text..."}                                           │
│                                                                                           │
└───────────────────────────────────┬─────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  RESPONSE BACK TO GRADIO                                                                  │
│                                                                                           │
│  RAGResult {                                                                              │
│      answer:         str           ← from LLM                                             │
│      sources:        List[str]     ← document_ids of chunks used                         │
│      repo_id:        str                                                                  │
│      retrieval_plan: Dict {                                                               │
│          seed_canonical_ids,   expanded_canonical_ids,                                   │
│          seed_docs,            expanded_docs,           total_docs                        │
│      }                                                                                    │
│  }                                                                                        │
│                                                                                           │
│  submit_rag_query() formats into:                                                         │
│      "🎯 Repository: ...                                                                  │
│       Answer: ...                                                                         │
│       Sources: ..."                                                                       │
│  → displayed in rag_output Textbox                                                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════
SERVICE MAP
═══════════════════════════════════════════════════════════════════

  :8001  ingestion_service    /v1/repos
                              /v1/graph/repos/{id}            ← full graph load
                              /v1/graph/repos/{id}/nodes      ← canonical→doc_id lookup
                              /v1/graph/repos/{id}/relationships

  :8003  vector_store         /v1/vectors/search              ← semantic search
                              /v1/vectors/search-by-doc       ← fetch by doc_id

  :8004  rag_orchestrator     /v1/rag                         ← entry point

  llm_service                 /generate                       ← answer generation

  :7860  gradio_app           browser UI
