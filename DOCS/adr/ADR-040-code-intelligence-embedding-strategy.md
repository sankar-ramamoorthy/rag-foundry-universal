* **ADR-038** – Pipeline construction ownership
* **ADR-039** – Artifact-level embedding strategy

Thisis a Formal ADR  **decision boundary document** that:

1. Explains Option 2 vs Option 3 clearly
2. States why Option 2 is chosen now
3. Explicitly defers Option 3
4. Prevents future confusion


---

# 📘 ADR-040

## **ADR-040: Phased Code Intelligence Architecture — Artifact-Level Embedding with Deferred Hybrid Chunk Layer**

### Status

Accepted (Phase 1)
Hybrid Architecture Deferred

### Date

2026-02-15

### Decision Owner

Code Intelligence Architecture

---

# 1. Context

The repository ingestion system builds a structural graph of code artifacts using `RepoGraphBuilder`.

Artifacts include:

* MODULE
* CLASS
* FUNCTION
* METHOD
* CALL

The system must also support semantic retrieval using vector embeddings.

Two architectural approaches were evaluated:

* **Option 2: Artifact-Level Embedding**
* **Option 3: Hybrid Graph + Chunk Layer**

This ADR documents the chosen phased approach.

---

# 2. Architectural Options Considered

---

## Option 2 — Artifact-Level Embedding

### Model

Each artifact node contains:

* Structural metadata
* Relationships
* Source code snippet (`text`)

Embedding unit = artifact.

```
Artifact Node = Embedding Unit
```

### Flow

```
AST → Artifact (with text)
       ↓
Persist Graph
       ↓
Embed artifact.text
```

### Properties

* 1:1 mapping between graph nodes and embedding units
* No separate chunking abstraction
* Simple and deterministic

---

## Option 3 — Hybrid Architecture

### Model

Two independent layers:

1️⃣ Structural Graph (relationships only)
2️⃣ Semantic Chunk Layer (retrieval units)

```
Artifact Node ≠ Embedding Unit
```

Chunks may:

* Subdivide artifacts
* Overlap across logical boundaries
* Be retrieval-optimized rather than AST-aligned

### Flow

```
AST → Structural Graph
        ↓
   Chunk Assembler
        ↓
   Embedding Units
```

---

# 3. Evaluation

| Criteria                  | Option 2 | Option 3  |
| ------------------------- | -------- | --------- |
| Simplicity                | High     | Medium    |
| Implementation Cost       | Low      | High      |
| Retrieval Precision       | Good     | Excellent |
| Multi-language readiness  | Limited  | Strong    |
| Cognitive Load            | Low      | Higher    |
| Premature Complexity Risk | Low      | High      |

---

# 4. Decision

The system will implement **Option 2 (Artifact-Level Embedding)** as Phase 1.

Option 3 (Hybrid Graph + Chunk Layer) is intentionally deferred.

---

# 5. Rationale

### 5.1 Current System Maturity

The system is currently stabilizing:

* Ingestion correctness
* Pipeline construction
* Graph persistence
* Basic embedding integration

Introducing a chunk orchestration layer at this stage would:

* Increase complexity
* Slow stabilization
* Introduce additional abstraction without proven need

---

### 5.2 Immediate Objective

Primary short-term objective:

> Achieve stable, functional semantic retrieval over repository artifacts.

Artifact-level embedding is sufficient to:

* Enable semantic search
* Support initial Code RAG
* Validate retrieval usefulness
* Observe real-world behavior

---

### 5.3 Risk Management

Premature introduction of hybrid chunking would risk:

* Over-engineering
* Increased bug surface area
* Blurred domain boundaries
* Retrieval logic complexity before retrieval metrics exist

---

# 6. Implementation Requirements (Phase 1)

The following must be true:

### 6.1 RepoGraphBuilder

Each artifact must include:

```python
"text": "<source snippet>"
```

### 6.2 Embedding Rules

Embed only:

* MODULE
* CLASS
* FUNCTION
* METHOD

Do not embed:

* CALL nodes
* Synthetic nodes
* Empty artifacts

### 6.3 Metadata Stored with Embedding

Vector metadata must include:

* `canonical_id`
* `artifact_type`
* `relative_path`
* `ingestion_id`

This preserves future traceability.

---

# 7. Explicit Deferral: Hybrid Chunk Layer

The following are deferred:

* Sub-artifact chunking
* Sliding window chunking
* Logical block chunking inside functions
* Hybrid graph + semantic scoring
* Chunk-level re-ranking

---

# 8. Future Trigger Conditions for Option 3

Hybrid architecture will be reconsidered when:

1. Large artifacts degrade retrieval precision
2. Retrieval quality metrics indicate chunk boundary issues
3. Multi-language ingestion becomes mandatory
4. Cross-artifact semantic linking is required
5. Advanced RAG ranking becomes necessary

---

# 9. Architectural Guardrails

To preserve future evolution:

* Artifact IDs must remain stable
* Embedding metadata must reference artifact identity
* Vector schema must not tightly couple to artifact schema
* Graph layer must remain independent of embedding logic

---

# 10. Long-Term Target Architecture

```
API Layer
    ↓
Application Services
    ↓
Structural Graph (Domain Layer)
    ↓
[Future] Chunk Assembly Layer
    ↓
Embedding Pipeline
    ↓
Vector Store
```

---

# 11. Consequences

### Positive

* Fast stabilization
* Reduced complexity
* Predictable ingestion
* Easier debugging
* Clear incremental evolution path

### Negative

* Retrieval granularity limited to artifact boundaries
* Large artifacts may produce suboptimal embeddings
* Hybrid retrieval postponed

---

# 12. Strategic Position

The system evolves in phases:

Phase 1 → Structural + Artifact-Level Embedding
Phase 2 → Retrieval Metrics & Evaluation
Phase 3 → Hybrid Chunk Layer Introduction

This ensures architecture grows based on observed needs rather than assumptions.

---

# Final Positioning

This ADR formally commits the system to:

> Deliver stability first.
> Introduce sophistication only when justified by empirical need.

---
