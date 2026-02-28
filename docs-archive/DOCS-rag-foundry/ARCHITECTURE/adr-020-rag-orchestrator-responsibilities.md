# DOCS/ARCHITECTURE/adr-020-rag-orchestrator-responsibilities.md

# ADR-020: RAG Orchestrator Responsibilities and Service Boundaries

**Status:** Accepted
**Context:** 2026-01-21
**Related ADRs:** ADR-005 (Vector Store), ADR-006 (OCR Boundaries), ADR-009 (Service Isolation)

---

## Context

The system consists of multiple microservices handling ingestion, vector storage, embeddings, LLM access, and orchestration. Without clear boundaries, responsibilities could drift, resulting in duplicated logic, tight coupling, and unclear ownership of RAG workflows.

The goal is to define **clear ownership** for the RAG Orchestrator service.

---

## Decision

1. **Centralization of Orchestration**
   The RAG Orchestrator is the **sole service** responsible for:

   * Accepting user RAG queries
   * Embedding queries
   * Querying the vector store
   * Assembling context
   * Invoking the LLM Service
   * Returning answers with source attribution

2. **Separation of Concerns**

   * **Ingestion Service** → Handles content ingestion, chunking, embedding storage
   * **Vector Store Service** → Handles vector similarity search
   * **LLM Service** → Handles text generation
   * **Shared Libraries** → Provides models, chunkers, and embedders

3. **Pipeline Guarantees**

   * Deterministic execution flow
   * No persistence of user queries or results
   * Explicit error propagation from downstream services
   * No implicit retries

4. **Extension Policy**

   * Orchestrator may extend context ranking, prompt templates, or multi-step retrieval
   * Orchestrator may **not** implement vector storage, chunking, or LLM provider SDKs

---

## Consequences

* Clear ownership reduces drift and future bugs
* Enables independent evolution of supporting services
* Makes the orchestrator the **trusted source of RAG logic**
* Other services remain stateless and modular

---

This ADR **formalizes** the service boundaries we discussed in `RAG_ORCHESTRATOR.md` and ensures future contributors have a clear reference.

---
