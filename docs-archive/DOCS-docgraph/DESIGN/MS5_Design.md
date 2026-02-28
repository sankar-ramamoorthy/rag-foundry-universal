
## DOCS/DESIGN/MS5_Design.md

---

# MS5 Design — Retrieval Execution & Context Assembly

## Milestone

**Milestone 5 — Retrieval Execution (Plan → Chunks)**

---

## Purpose

Milestone 5 completes the **GraphRAG control loop** by executing a previously constructed **RetrievalPlan**.

If MS4 answers:

> *“Which documents are allowed to participate in retrieval?”*

Then MS5 answers:

> *“How do we fetch and assemble evidence from only those documents?”*

This milestone **does not introduce new reasoning**.
It strictly **executes intent** already captured in the plan.

---

## Architectural Principle

> **Planning decides. Execution obeys.**

MS5 enforces a hard boundary:

* **Retrieval planning** determines *eligibility*
* **Retrieval execution** performs *mechanical retrieval*

Any violation of this boundary is considered a **bug**.

---

## Design Goals

1. Execute RetrievalPlans **deterministically**
2. Enforce **document-level eligibility**
3. Preserve **existing semantic retrieval behavior**
4. Produce **auditable, bounded context**
5. Keep execution logic **graph-agnostic**

---

## Non-Goals (Explicit)

MS5 does **not** introduce:

* Relationship traversal
* Planning logic
* Ranking heuristics beyond existing vector similarity
* Cross-document reasoning
* Agent autonomy

MS5 **cannot modify or reinterpret** a RetrievalPlan.

---

## Retrieval Execution Pipeline (MS5)

```
RetrievalPlan
  │
  ▼
Eligible Document Set
  │
  ▼
Chunk Retrieval (vector similarity)
  │
  ▼
Per-Document Chunk Sets
  │
  ▼
Context Assembly
```

---

## Inputs & Outputs

### Input

**RetrievalPlan** (from MS4):

* `seed_document_ids`
* `expanded_document_ids`
* `constraints` (depth, traversal flags)
* `expansion_metadata` (for explainability)

---

### Output

A **structured retrieval result**, conceptually:

```text
RetrievedContext:
  document_id: D1
    chunks:
      - chunk_id
      - text
      - score

  document_id: D2
    chunks:
      - chunk_id
      - text
      - score
```

Notes:

* Chunks are grouped **by document**
* Ordering is stable and explainable
* No chunk exists without a document parent

---

## Execution Rules (Hard Guarantees)

| Rule                   | Enforcement                   |
| ---------------------- | ----------------------------- |
| Only planned documents | Filter by RetrievalPlan       |
| No implicit expansion  | No new document IDs           |
| Deterministic          | Same plan → same result       |
| Bounded                | Chunk limits enforced         |
| Auditable              | Document → chunk traceability |

If a document is **not** in the plan, it is **invisible** to execution.

---

## Service Responsibilities

### RAG Orchestrator (Primary Owner)

* Accepts a `RetrievalPlan`
* Coordinates:

  * vector store queries
  * chunk retrieval
* Produces structured retrieval output

---

### Vector Store Service

* Remains **unchanged**
* Provides:

  * similarity search
  * chunk metadata
* Is **not relationship-aware**

---

### Ingestion Service

* Owns:

  * document nodes
  * relationships
* Not involved at execution time

---

## Context Assembly Strategy

MS5 assembles context using **existing logic**, with one new constraint:

> **All chunk retrieval is scoped to eligible documents only.**

Assembly rules:

* Group chunks by document
* Preserve ordering (e.g. by score)
* Enforce per-document or global limits
* Produce explainable structure

No prompt formatting decisions are made here.

---

## Failure Modes & Safeguards

| Risk                       | Safeguard               |
| -------------------------- | ----------------------- |
| Chunks from unrelated docs | Plan-enforced filtering |
| Silent behavior change     | Explicit MS5 phase      |
| Over-retrieval             | Hard limits             |
| Hidden coupling            | No planning imports     |

---

## Testing Strategy (MS5)

### Unit Tests (CI-safe)

* Mock RetrievalPlan
* Mock vector store responses
* Assert:

  * filtering correctness
  * deterministic output
  * no leakage

---

### Integration Tests (Docker-only)

* Real Postgres + pgvector
* Real chunk data
* Assert:

  * only planned docs produce chunks
  * expansion effects visible
  * stable result set

No Ollama required.

---

## Compatibility Guarantees

* If RetrievalPlan contains only seeds → MS3-equivalent behavior
* No breaking changes to ingestion
* No changes to vector storage schema

---

## Relationship to Prior Milestones

| Milestone | Role                      |
| --------- | ------------------------- |
| MS2       | DocumentNodes             |
| MS3       | Relationships (structure) |
| MS4       | Retrieval planning        |
| **MS5**   | **Retrieval execution**   |

This completes the **GraphRAG core loop**.

---

## Summary

MS5 turns **structured intent** into **bounded evidence**.

It enforces discipline:

* no guessing
* no drift
* no prompt bloat

At the end of MS5:

* Retrieval is **relationship-aware**
* Execution is **predictable**
* Context is **explainable**
* reason over **designed knowledge**, not accidents

---

