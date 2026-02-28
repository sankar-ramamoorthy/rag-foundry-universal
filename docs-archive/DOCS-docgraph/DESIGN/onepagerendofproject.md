---

# 🔹 MS5 RAG System – Developer Cheat Sheet

## 1️⃣ Quick Overview

**Purpose:** Retrieve relevant document chunks via HTTP vector search, prepare them deterministically, and query an LLM for an answer.

**Entry Point:**

```python
from rag_orchestrator.src.core.service import run_rag
```

**Returns:** `RAGResult(answer: str, sources: List[str])`

---

## 2️⃣ Core Components

| Module                       | Role                                                                 |
| ---------------------------- | -------------------------------------------------------------------- |
| `core/config.py`             | Centralized settings for vector store, LLM, embeddings.              |
| `retrieval/types.py`         | Data types: `RetrievedChunk`, `RetrievedContext`.                    |
| `retrieval/execute_plan.py`  | Executes `RetrievalPlan` → enforces allowed chunks.                  |
| `retrieval/agent_adapter.py` | Flattens `RetrievedContext` → agent-ready chunks with token limits.  |
| `core/service.py`            | Full RAG pipeline: embed → retrieve → plan → flatten → LLM → return. |

**Important Functions:**

* `execute_retrieval_plan(plan, retrieved_chunks_by_document, debug)` → returns `RetrievedContext`.
* `prepare_chunks_for_agent(retrieved_context, document_order, max_chunks_per_doc, ...)` → returns list of dicts for LLM.

---

## 3️⃣ Running a Query

```python
import asyncio
from rag_orchestrator.src.core.service import run_rag

async def main():
    result = await run_rag("Explain transformers in simple terms")
    print(result.answer)
    print(result.sources)

asyncio.run(main())
```

**Optional Parameters:**

* `top_k` – number of chunks to retrieve from vector store (default: 20)
* `max_chunks_per_doc` – limit per document (default: 5)
* `max_total_tokens` – context token limit (default: 2048)
* `chunk_filter_fn` – custom filter function

---

## 4️⃣ Debugging Tips

* Set `debug=True` when calling `execute_retrieval_plan` or `prepare_chunks_for_agent`.
* Logs will show:

  * Seed document IDs
  * Chunk IDs and scores
  * Total chunks prepared
  * Token counts
* Vector search & LLM failures are logged at `ERROR`.

---

## 5️⃣ Known Limitations / TODOs

1. **Tests:** None implemented yet. Focus areas:

   * Chunk selection, filtering, and token limits
   * Retrieval plan enforcement
   * Full RAG flow with mock vector/LLM services
2. **Document Expansion:** Currently, only seed documents are used.
3. **Advanced Token Counting:** Simple word split used; could be replaced with tokenizer.

---

## 6️⃣ Recommended Next Steps

1. **Verify Pipeline:**

   * Run `run_rag()` with a test query.
   * Inspect `sources` to confirm provenance.
2. **Implement Tests:**

   * Unit tests for `execute_plan` and `agent_adapter`.
   * Integration test for `run_rag()` using a mocked HTTP client.
3. **Optional Enhancements:**

   * Implement document expansion in `RetrievalPlan`.
   * Improve token budgeting with tokenizer-based counting.
   * Add logging/metrics for chunk scoring and LLM usage.

---

## 7️⃣ Notes for Tomorrow

* You **don’t need conversation history**; all necessary context is in code and config.
* Focus first on getting `run_rag()` to return valid results with logs.
* Use the `debug` flags liberally to inspect chunk processing and token counts.
* Environment variables from `.env` override defaults; check `VECTOR_STORE_URL` and `LLM_SERVICE_URL`.

---

This sheet plus the full project code should allow a developer to pick up immediately and safely continue work.

---
