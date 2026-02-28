# DOCS/SERVICES/RAG_ORCHESTRATOR.md dated 2026/01/21


---

## RAG Orchestrator

**Category:** Core Orchestration Service
**Role:** Retrieval-Augmented Generation Controller
**Status:** Stable (Post-MVP foundation)

---

## Overview

The **RAG Orchestrator** is the **central coordination service** for retrieval-augmented generation workflows.

It owns the **end-to-end RAG process**:

1. Query embedding
2. Vector search
3. Context assembly
4. LLM invocation
5. Response shaping and attribution

All other services exist to support this orchestration.

---

## Responsibilities

### What the RAG Orchestrator **does**

* Accepts user RAG queries
* Converts queries into embeddings
* Performs vector search via the Vector Store Service
* Assembles retrieval context
* Invokes the LLM Service
* Returns answers with source attribution

### What the RAG Orchestrator **does NOT do**

* ❌ Content ingestion
* ❌ Chunking strategies
* ❌ Embedding model training
* ❌ Vector persistence
* ❌ Direct LLM provider integration
* ❌ UI concerns

---

## Service API

### `POST /v1/search`

Retrieval-only endpoint (no LLM invocation).

#### Request

```json
{
  "question": "string",
  "top_k": 5
}
```

#### Response

```json
{
  "results": [
    {
      "text": "Retrieved chunk text",
      "source": "document | pdf | image | unknown"
    }
  ]
}
```

---

### `POST /v1/rag`

Full retrieval-augmented generation pipeline.

#### Request

```json
{
  "query": "string",
  "top_k": 5,
  "provider": "optional",
  "model": "optional"
}
```

#### Response

```json
{
  "answer": "Generated answer text",
  "sources": ["pdf", "text", "unknown"]
}
```

---

## RAG Execution Flow

### Step 1: Query Embedding

* Uses shared embedding abstractions
* Wraps the query in a temporary `Chunk`
* Produces a single embedding vector

---

### Step 2: Vector Search

* Calls Vector Store Service via HTTP
* Requests top-k similar vectors
* Expects metadata-rich results

The orchestrator does **not** interpret vector similarity — it trusts the store.

---

### Step 3: Context Assembly

* Extracts `metadata.chunk_text` from search results
* Concatenates results deterministically
* Handles malformed or missing metadata gracefully

No summarization or reasoning occurs at this stage.

---

### Step 4: LLM Invocation

* Sends assembled context and query to LLM Service
* Passes provider/model overrides transparently
* Does not perform prompt engineering beyond basic formatting

---

### Step 5: Response Shaping

* Extracts the generated answer
* Collects source attribution from metadata
* Returns a structured RAG response

---

## Configuration

Configuration is environment-driven and cached.

### Key Settings

| Variable             | Description                   |
| -------------------- | ----------------------------- |
| `VECTOR_STORE_URL`   | Vector Store service base URL |
| `LLM_SERVICE_URL`    | LLM Service base URL          |
| `EMBEDDING_PROVIDER` | Embedding provider            |
| `OLLAMA_BASE_URL`    | Ollama API endpoint           |
| `OLLAMA_EMBED_MODEL` | Embedding model               |
| `OLLAMA_BATCH_SIZE`  | Embedding batch size          |

---

## Error Semantics

* Vector store failures propagate as HTTP errors
* LLM service failures propagate as HTTP errors
* Partial failures result in degraded but valid responses
* No retries are performed implicitly

---

## Design Guarantees

The RAG Orchestrator guarantees:

* Deterministic pipeline execution
* Clear ownership of orchestration logic
* No persistence of user queries or responses
* No hidden state or memory
* Explicit service boundaries

---

## Extension Guidelines

### Appropriate Extensions

* Advanced context ranking
* Prompt templating
* Multi-step retrieval
* Reranking models
* Agent-style workflows
* Tool calling
* Streaming responses

### Inappropriate Extensions

* Vector storage logic
* LLM provider SDKs
* Embedding implementations
* Chunking heuristics

---

## Relationship to Other Services

| Service              | Role                       |
| -------------------- | -------------------------- |
| Ingestion Service    | Supplies indexed content   |
| Vector Store Service | Similarity search          |
| LLM Service          | Text generation            |
| Shared Libraries     | Data models and primitives |

---

## Architectural Role

The RAG Orchestrator is the **brain** of the platform.

It is the only service allowed to:

* Make decisions
* Control execution flow
* Compose AI behavior

All intelligence flows through it.

---

### ✅ Status

This document reflects the **current authoritative behavior** of the RAG Orchestrator. 20260121

---

