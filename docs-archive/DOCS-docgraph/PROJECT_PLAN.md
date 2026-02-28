# Project Plan — rag-foundry-docgraph

**Created:** 2026-01-31  

---

## 1. Project Overview

**Purpose:**  
`rag-foundry-docgraph` is an evolution of `rag-foundry`, focused on **document-level knowledge modeling and structured retrieval**. The goal is to improve **deterministic RAG behavior**, reduce **prompt bloat**, and provide **clear, auditable context reasoning**.

**Key Improvements Over `rag-foundry`:**
- Introduce **DocumentNodes** as first-class retrieval units.
- Add **explicit relationships** between documents.
- Implement **structured retrieval plans** instead of flat top-k chunk selection.
- Maintain **deterministic, testable, and debuggable behavior**.
- Keep agent behavior optional or out of scope for now.

---

## 2. Goals & Success Metrics

**Goals:**
1. Implement a **document-level semantic layer** above chunk embeddings.
2. Provide a **graph structure** of relationships between documents.
3. Enable **controlled, predictable context assembly**.
4. Maintain **full compatibility** with existing ingestion pipelines.

**Success Metrics:**
- Each query uses only relevant documents + chunks.
- Prompt length is predictable and bounded.
- Fewer contradictory answers in RAG outputs.
- Every document included in context is traceable to a retrieval rule.
- Clear separation between **conceptual layer** (document summaries) and **evidence layer** (chunks).

---

## 3. Milestones

| Milestone | Description | Status |
|-----------|-------------|--------|
| M1 | Project planning, documentation, ADRs | In Progress |
| M2 | DocumentNodes table and migrations (no behavior change) | Planned |
| M3 | Document relationships & retrieval plan (graph layer) | Planned |
| M4 | Context assembly logic & testing | Planned |
| M5 | Optional agent integration (future) | Planned |

---

## 4. Dependencies

- **PostgreSQL** with `pgvector` extension.
- **Python 3.11+** (or current version in `rag-foundry`).
- **Docker** / **Docker Compose** for services.
- Python libraries:
  - `sqlalchemy`
  - `alembic`
  - `pytest`
  - `numpy`
  - `faiss` or other vector DB optional
- Optional LLM APIs (Claude, OpenAI, etc.) for validation/testing.

---

## 5. Folder Structure

```text
rag-foundry-docgraph/
├─ docs/                 # Project documentation
│  ├─ PROJECT_PLAN.md    # This file
│  └─ adr/               # Architecture Decision Records
├─ migrations/           # Alembic migrations for Postgres
├─ ingestion_service/    # Ingestion pipeline
├─ llm_service/          # LLM interface
├─ rag_orchestrator/     # RAG orchestration logic
├─ shared/               # Shared utilities
├─ vector_store_service/ # Vector DB interface
├─ tests/                # Unit and integration tests
├─ docker-compose.yml
├─ pyproject.toml
└─ README.md
````

---

## 6. Architecture Decision Records (ADR)

**Proposed ADRs for Milestone 1:**

1. **ADR-001:** Choice of `DocumentNode` as first-class retrieval unit.
2. **ADR-002:** Separation of **document summary embeddings** from **chunk embeddings**.
3. **ADR-003:** Use of **directed, typed relationships** for controlled context expansion.
4. **ADR-004:** Strategy for deterministic, reproducible context assembly.

> ADRs will live in `docs/adr/` and each will have a dedicated markdown file.

---


---

### 🔄 Project Plan Amendment (Post-MS4 Clarification)

**Date:** 2026-02-XX
**Reason:** Architectural clarity after MS4 implementation

During MS3–MS4, the system architecture evolved to explicitly separate **retrieval planning** from **retrieval execution**. This distinction was not fully articulated in the original milestone descriptions but has become foundational to the system’s design.

The project plan is amended to reflect this clarification.

---

### 🔹 Updated Milestone Definitions

| Milestone          | Refined Description                                                              |
| ------------------ | -------------------------------------------------------------------------------- |
| **MS3**            | Persisted document relationships (graph structure only, no behavior change)      |
| **MS4**            | **Retrieval planning** — relationship-aware, deterministic, bounded, inspectable |
| **MS5**            | **Retrieval execution & context assembly** driven strictly by RetrievalPlan      |
| **MS6 (Optional)** | Agent / orchestration integration (non-core, future work)                        |

---

### 🔹 Clarified Architectural Contract

The retrieval pipeline is now explicitly divided into two phases:

1. **Retrieval Planning**

   * Determines *which documents are eligible*
   * Uses relationships, rules, and constraints
   * Produces a serializable `RetrievalPlan`
   * No embeddings, no chunk access

2. **Retrieval Execution**

   * Consumes a `RetrievalPlan`
   * Fetches chunks only from eligible documents
   * Performs semantic ranking and scoring
   * Assembles bounded LLM context

This separation ensures:

* Deterministic behavior
* Auditable reasoning
* Controlled context growth
* Safe future extensibility

---

### 🔹 Project Success Definition (Updated)

The project is considered **functionally complete** when:

* Relationships influence retrieval **via planning**
* Execution respects the plan strictly
* Retrieval remains bounded, deterministic, and explainable
* Agents reason over *structured context*, not raw recall

---

## Do we *need* to do this?

Technically: **no**
Practically: **yes**

Because:

* Future-you will thank you
* New contributors won’t misinterpret MS4 vs MS5
* The plan now matches the **actual architecture**
* You’ve captured the key insight from the GraphRAG post:

  > *planning is the behavior change — execution just follows orders*

---

