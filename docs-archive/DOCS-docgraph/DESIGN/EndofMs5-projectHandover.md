
# 🔹 Project Handover: MS5 RAG System

## 1️⃣ Project Overview

**Project Name:** MS5 RAG System
**Purpose:** Build a modular, deterministic Retrieval-Augmented Generation (RAG) system. The system can answer natural language questions using chunks retrieved from a vector store, combined with a generative LLM.

**Goals:**

1. Accept a user query.
2. Embed the query using a configurable embedding service.
3. Retrieve top-k relevant document chunks from a vector store (via HTTP API).
4. Build a deterministic retrieval plan (including seed documents and optional expanded documents).
5. Flatten and filter retrieved chunks for LLM consumption, enforcing per-document and total token limits.
6. Call a configurable LLM service with the retrieved context to generate an answer.
7. Return the answer along with the source documents used.

**Core Principles Achieved:**

* **Determinism:** Document and chunk order is stable across runs.
* **Provenance:** Each chunk keeps its `document_id`, `chunk_id`, `score`, and `metadata`.
* **HTTP-first retrieval:** No local vector store is required; system consumes HTTP search results directly.
* **Extensibility:** Modular components allow alternative embedders, LLMs, and chunk filters.
* **Token Budgeting:** Context length is controlled to prevent excessive LLM input.

---

## 2️⃣ Completed Components

1. **Configuration Management** (`core/config.py`)

   * Fully functional with environment overrides and cached settings.
   * Provides endpoints for vector store and LLM service, embedding settings.

2. **Data Types** (`retrieval/types.py`)

   * `RetrievedChunk`: immutable chunk with ID, document, text, score, metadata.
   * `RetrievedContext`: immutable grouping of chunks by document.

3. **Retrieval Plan Execution** (`retrieval/execute_plan.py`)

   * Consumes a `RetrievalPlan` + preloaded `RetrievedChunk`s.
   * Ensures chunks are strictly bounded by the plan.
   * Logs debug info if `debug=True`.
   * No scoring, ranking, or cross-document similarity logic is performed here (clean separation of concerns).

4. **Chunk Flattening / Agent Preparation** (`retrieval/agent_adapter.py`)

   * Converts `RetrievedContext` into a flat, deterministic list of chunks.
   * Enforces max chunks per document, total chunks, and optional token budgets.
   * Supports optional filtering and custom token counting.

5. **Full RAG Pipeline** (`core/service.py`)

   * Asynchronous `run_rag()` function.
   * Steps:

     1. Embed query.
     2. Retrieve top-k seed documents via HTTP vector search.
     3. Wrap raw results into `RetrievedChunk`s and group by document.
     4. Build and execute `RetrievalPlan`.
     5. Prepare chunks for agent / LLM.
     6. Enforce token limits.
     7. Call LLM service.
     8. Return `RAGResult` with `answer` and `sources`.
   * Handles exceptions and logs HTTP/LLM failures.

6. **Integration Notes**

   * No local vector store dependency; relies on HTTP API.
   * Embedding and LLM services are configurable.
   * Designed for deterministic, reproducible retrieval + generation.

---

## 3️⃣ Remaining / Incomplete

1. **Tests**

   * Unit and integration tests are not yet implemented.
   * Test coverage should include:

     * `execute_retrieval_plan` chunk boundary enforcement.
     * `prepare_chunks_for_agent` filtering, token limits, and ordering.
     * Full RAG pipeline with mock HTTP vector store & LLM responses.

2. **Optional Features Not Yet Implemented**

   * Document expansion logic in `RetrievalPlan` (currently, `expanded_document_ids` is always empty).
   * Scoring/ranking or cross-document reasoning.
   * Token counting for more accurate LLM budgeting (currently, simple word split is used in `service.py`).

---

## 4️⃣ How to Use / Developer Jump-in

**Quick Start Example:**

```python
import asyncio
from rag_orchestrator.src.core.service import run_rag

async def main():
    result = await run_rag("Explain transformers in simple terms")
    print("Answer:", result.answer)
    print("Sources:", result.sources)

asyncio.run(main())
```

**Key Concepts for New Developers:**

* `RetrievedChunk` → fundamental atomic retrieval unit.
* `RetrievedContext` → grouped chunks by document.
* `RetrievalPlan` → defines which documents/chunks are allowed.
* `execute_retrieval_plan()` → retrieves chunks strictly according to plan.
* `prepare_chunks_for_agent()` → flattens and filters chunks for LLM.
* `run_rag()` → high-level entry point combining embedding, retrieval, chunk prep, and LLM call.

**Debugging Tips:**

* Pass `debug=True` to `execute_retrieval_plan` or `prepare_chunks_for_agent` to see internal logging.
* Logs include chunk IDs, document IDs, scores, and text previews.
* Vector search and LLM calls are logged at info/error level.

---

## 5️⃣ Architecture Diagram (Text)

```
[User Query]
      |
      v
[Embedder Service] -> query vector
      |
      v
[Vector Store HTTP API] -> top-k seed docs/chunks
      |
      v
[RetrievedChunk / RetrievalPlan] -> execute_retrieval_plan
      |
      v
[Flattened Chunks] -> prepare_chunks_for_agent
      |
      v
[LLM Service] -> final answer
      |
      v
[RAGResult(answer, sources)]
```

---

## 6️⃣ Key Design Principles

* **Separation of concerns**: retrieval, chunk flattening, and LLM are separate.
* **Deterministic output**: same query + data → same chunk order.
* **Provenance-preserving**: chunks maintain full source info.
* **Configurable services**: vector store, embeddings, LLM can be swapped.
* **Extensible pipeline**: future expansion logic can be added in `RetrievalPlan`.

---

## ✅ Summary

* MS5 RAG system is **fully functional** for basic queries with HTTP-based vector retrieval and LLM answer generation.
* All core types, execution paths, and chunk preparation are implemented.
* Remaining tasks: **tests** and optional **document expansion / scoring logic**.
* Developer picking up tomorrow can immediately run `run_rag()` and inspect retrieved chunks and logs.

---
