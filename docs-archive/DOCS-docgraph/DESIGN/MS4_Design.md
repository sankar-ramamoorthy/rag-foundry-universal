## DOCS/DESIGN/MS4_Design.md.

---

# MS4 Design — Relationship-Aware Retrieval Planning

## Milestone

**Milestone 4 — Retrieval Plan (Behavior Change Begins)**

---

## Purpose

Milestone 4 introduces the **first intentional behavior change** to retrieval in `rag-foundry-docgraph`.

Up to MS3, document relationships existed only as persisted structure.
In MS4, relationships begin to **influence retrieval planning**, while **retrieval execution remains unchanged**.

This milestone establishes a **clear planning layer** that decides *what* documents are eligible for retrieval — without changing *how* content is fetched, ranked, or embedded.

---

## Design Goals

1. Introduce relationship awareness **without graph traversal**
2. Preserve existing semantic retrieval behavior
3. Keep all behavior:

   * deterministic
   * inspectable
   * testable
4. Create a foundation for future graph-based retrieval

---

## Non-Goals (Explicit)

MS4 **does not** introduce:

* Recursive graph traversal
* Multi-hop expansion
* Relationship-based ranking or scoring
* Automatic LLM-driven traversal
* Cycle detection
* Query rewriting

Any appearance of these would be considered **scope creep**.

---

## Architectural Positioning

### Retrieval Pipeline (As of MS4)

```
Query
  │
  ▼
Semantic Retrieval
  │   (vector similarity, unchanged)
  ▼
Seed DocumentNodes
  │
  ▼
Relationship-Aware Planning   ← NEW (MS4)
  │
  ▼
Retrieval Plan
  │
  ▼
Chunk Retrieval & Ranking
  │   (unchanged)
  ▼
LLM Context Assembly
```

---

## Core Concept: Retrieval Planning

### Definition

**Retrieval Planning** is a pre-execution phase that produces a structured description of *which documents may be consulted* during retrieval.

It does **not**:

* fetch chunks
* rank results
* score relevance

---

## Retrieval Plan Structure (Conceptual)

A retrieval plan is a **pure data object**.

Example:

```text
RetrievalPlan:
  seed_documents:
    - document_id: D1
    - document_id: D2

  expanded_documents:
    - document_id: D3
      via: explains
      from: D1

  constraints:
    max_relationship_depth: 1
    traversal_enabled: false
```

### Design Notes

* Expansion is **1-hop only**
* Directionality matters (outgoing only)
* Relationship metadata is preserved for explainability

---

## Relationship Expansion Rules

| Rule      | Description                                   |
| --------- | --------------------------------------------- |
| Direction | Outgoing relationships only                   |
| Depth     | Exactly one hop                               |
| Types     | All relation types allowed (no filtering yet) |
| Ordering  | No implied ranking                            |
| Failure   | Missing relationships → no expansion          |

This keeps behavior **predictable and bounded**.

---

## Data Sources

MS4 uses only **existing persisted data**:

* `document_nodes`
* `document_relationships`
* `vector_chunks`

No new tables are introduced.

---

## Service Boundaries

### Ingestion Service

* Owns:

  * DocumentNode
  * DocumentRelationship
* Provides:

  * CRUD access to relationships
  * Read access for retrieval planning

### Retrieval Logic

* Consumes:

  * RetrievalPlan
* Remains:

  * Semantically driven
  * Graph-agnostic

---

## Testing Strategy (MS4)

### Unit Tests (CI)

* Test:

  * planning logic in isolation
  * relationship expansion rules
* No DB
* No Docker

### Integration Tests (Local Only)

* Validate:

  * relationships influence candidate document set
  * no traversal beyond one hop
* Uses:

  * Docker
  * Postgres + pgvector
* No Ollama required for planning tests

---

## Failure Modes & Safeguards

| Risk                   | Mitigation                 |
| ---------------------- | -------------------------- |
| Accidental traversal   | Hard-coded depth limit     |
| Silent behavior change | Explicit planning stage    |
| Performance blow-up    | Bounded expansion          |
| Hidden logic           | Plan object is inspectable |

---

## Compatibility Guarantees

* If no relationships exist → behavior matches MS3
* Existing semantic retrieval code remains untouched
* All changes are additive and reversible

---

## Relationship to ADRs

| ADR     | Alignment                           |
| ------- | ----------------------------------- |
| ADR-001 | DocumentNode remains retrieval unit |
| ADR-002 | Relationships now consulted         |
| ADR-003 | Semantic retrieval still primary    |
| ADR-004 | Explicit relationships activated    |
| ADR-005 | Governs MS4 behavior                |

---

## Future Extensions (Out of Scope)

* Relationship weighting
* Traversal depth > 1
* Hybrid semantic + graph scoring
* LLM-guided traversal
* Query-specific traversal rules

These are intentionally deferred.

---

## Summary

MS4 introduces **relationship-aware retrieval planning** as a controlled, minimal behavior change.

It activates document structure **without sacrificing determinism**, setting the stage for future graph-aware retrieval while preserving system stability.

---


## Behavioral Guardrails & Explicit Constraints (MS4-IS6)

This section makes the MS4 behavior change **explicit and safe** for future developers.

### Key Invariants

- **Expansion depth**: always 1-hop
- **Directionality**: outgoing relationships only
- **Deterministic**: same input → same plan
- **No recursive traversal**: cycles and multi-hop expansion are disallowed
- **Planner is read-only**: does not perform DB writes
- **No ranking or scoring**: influences only candidate selection
- **Inspectability**: `RetrievalPlan` objects can be serialized and examined

### Developer Guidance

- Retrieval execution logic remains **unchanged**
- Planner is a **pre-execution phase**
- Unit tests cover all planner behaviors
- Integration tests validate DB-backed expansion end-to-end
- Any future modifications that violate these invariants are considered **scope creep**

### Summary

MS4 introduces a **deterministic, bounded, test-covered** retrieval planning phase:

- Relationships influence **what may be retrieved**
- Execution **how** documents are retrieved remains unchanged
- Ensures safe, predictable behavior and a clear foundation for future graph-aware retrieval

