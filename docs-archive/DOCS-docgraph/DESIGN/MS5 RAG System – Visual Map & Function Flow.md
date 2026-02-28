+-------------------+
|   User Query      |
|  "Explain X..."   |
+---------+---------+
          |
          v
+-------------------+
|   run_rag(query)  |  <- entry point
|  core/service.py  |
+---------+---------+
          |
          v
+-------------------+
| Embed Query       |  (embed_query via get_embedder)
| → query_embedding |
+---------+---------+
          |
          v
+-------------------+
| Vector Store HTTP |  (raw search via httpx)
| → raw_results     |
+---------+---------+
          |
          v
+-------------------+
| Infer Seed Docs   |  (deterministic document IDs)
| seed_document_ids |
+---------+---------+
          |
          v
+-------------------+
| Build RetrievalPlan|
| seed + expanded   |
+---------+---------+
          |
          v
+-------------------+
| execute_retrieval_plan |
| enforcement: only allowed chunks |
| → RetrievedContext       |
+---------+---------+
          |
          v
+-------------------+
| prepare_chunks_for_agent |
| flatten chunks          |
| enforce per-doc & total |
| token limits, filtering |
| → agent_chunks          |
+---------+---------+
          |
          v
+-------------------+
| Token Budget Enforcement |
| max_total_tokens        |
| context_str built        |
+---------+---------+
          |
          v
+-------------------+
| Call LLM Service  |  (HTTP POST to LLM_SERVICE_URL)
| context + query   |
+---------+---------+
          |
          v
+-------------------+
| Return RAGResult  |
| answer + sources  |
+-------------------+
