---

# Service Summary – 2026/01/21

This document provides a **high-level overview of all core and shared services** in the Agentic-RAG Platform. It is intended for developers, architects, and integrators to understand the **responsibilities, interactions, and boundaries** of each service.

---

## Core Services Overview

| Service                        | Role                                      | Responsibilities                                                                                                                                                                                                                        | Upstream / Downstream Relationships                                                    |
| ------------------------------ | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **Ingestion Service**          | Raw content processing & vectorization    | - Accepts documents, text, and images<br>- Extracts content & builds document graphs<br>- Chunks content deterministically<br>- Generates embeddings<br>- Persists vectors to Vector Store Service                                      | Downstream: Vector Store Service / RAG Orchestrator<br>Upstream: Source content        |
| **Vector Store Service (VSS)** | Vector persistence & similarity search    | - Stores embeddings in PostgreSQL using `pgvector`<br>- Batch insertion & deletion by ingestion ID<br>- Supports similarity search (`top_k`)<br>- Minimal ingestion tracking                                                            | Upstream: Ingestion Service<br>Downstream: RAG Orchestrator                            |
| **RAG Orchestrator**           | Retrieval-Augmented Generation controller | - Accepts RAG queries<br>- Embeds queries using shared embedders<br>- Performs vector search via Vector Store Service<br>- Assembles retrieval context<br>- Invokes LLM Service<br>- Returns structured answers with source attribution | Upstream: User queries / LLM Service / Vector Store Service<br>Downstream: LLM Service |
| **LLM Service**                | Language model invocation                 | - Provider-agnostic LLM interface<br>- Generates responses from prompt + context<br>- Minimal prompt formatting<br>- Stateless, horizontally scalable                                                                                   | Upstream: RAG Orchestrator<br>Downstream: None (response only)                         |

---

## Shared Services / Libraries

**Location:** `shared/`
**Purpose:** Stateless, side-effect-free utilities used across multiple services.

| Module              | Role                                                                    |
| ------------------- | ----------------------------------------------------------------------- |
| `shared/chunks.py`  | Atomic `Chunk` objects holding content and metadata                     |
| `shared/chunkers/`  | Chunking strategies (fixed, sentence, paragraph)                        |
| `shared/embedders/` | Embedding abstraction: `BaseEmbedder`, `OllamaEmbedder`, `MockEmbedder` |
| `shared/models/`    | Cross-service data models (e.g., `VectorMetadata`)                      |

**Rules / Guarantees:**

* Stateless, service-agnostic, deterministic
* No persistence, orchestration, or FastAPI routes
* Enables consistent data contracts and unit testing

---

## Data Flow Summary

### ASCII Architecture Diagram

```
           ┌────────────────────┐
           │   Raw Content /    │
           │  Documents / Text  │
           └─────────┬──────────┘
                     │
                     ▼
           ┌────────────────────┐
           │  Ingestion Service │
           │  (Extract → Graph  │
           │   → Chunk → Embed) │
           └─────────┬──────────┘
                     │
                     ▼
           ┌────────────────────┐
           │ Vector Store       │
           │ Service (VSS)     │
           │ Persist & Search  │
           └─────────┬──────────┘
                     │
                     │   Vector search / top_k
                     ▼
           ┌────────────────────┐
           │ RAG Orchestrator   │
           │ (Query Embedding   │
           │  → Search → Context│
           │  → LLM Invoke)     │
           └─────────┬──────────┘
                     │
                     │ Prompt + context
                     ▼
           ┌────────────────────┐
           │    LLM Service     │
           │  (Stateless Gen)  │
           └─────────┬──────────┘
                     │
                     ▼
           ┌────────────────────┐
           │  User Response w/  │
           │  Sources / Answer  │
           └────────────────────┘
```

---

## Key Design Principles

* **Separation of Concerns:** Each service owns a distinct responsibility.
* **Statelessness:** Services like LLM and Vector Store are stateless beyond their persistence layer.
* **Determinism & Provenance:** Chunks, embeddings, and ingestion metadata are traceable and reproducible.
* **Extensibility:** Modular architecture allows new extractors, embedders, or LLM providers.
* **Testability:** Mocked components (embedders, chunkers) enable isolated unit tests.
* **Clear Ownership:** Orchestration and reasoning live exclusively in RAG Orchestrator.

---

## Configuration Guidelines

* Environment-driven configuration for all services
* Examples:

| Variable           | Service                    | Purpose                      |
| ------------------ | -------------------------- | ---------------------------- |
| `DATABASE_URL`     | Vector Store / Ingestion   | PostgreSQL DSN               |
| `VECTOR_DIMENSION` | Vector Store / Ingestion   | Embedding vector dimension   |
| `LLM_PROVIDER`     | LLM Service / Orchestrator | Default LLM provider         |
| `VECTOR_STORE_URL` | RAG Orchestrator           | Vector Store endpoint        |
| `OLLAMA_BASE_URL`  | Ingestion / LLM            | Embedding / LLM API endpoint |

---

## Service Relationships

| Service              | Calls / Uses                                            |
| -------------------- | ------------------------------------------------------- |
| Ingestion Service    | Vector Store Service (persist embeddings)               |
| Vector Store Service | None (passive store)                                    |
| RAG Orchestrator     | Vector Store Service (search), LLM Service (generate)   |
| LLM Service          | None (invoked by orchestrator)                          |
| Shared Libraries     | Used by all services for chunks, embeddings, and models |

---

## Summary Notes

* **Ingestion Service:** The pipeline entry point for all content.
* **Vector Store Service:** Immutable vector storage, similarity search.
* **RAG Orchestrator:** Single source of orchestration, reasoning, and context assembly.
* **LLM Service:** Stateless, provider-agnostic generation endpoint.
* **Shared Libraries:** Foundational, reusable primitives for chunks, embeddings, and metadata.

This summary consolidates **service ownership, flow, and responsibilities** in one reference point for the platform.

---
