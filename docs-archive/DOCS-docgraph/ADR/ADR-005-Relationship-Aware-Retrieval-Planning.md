---

# ADR-005: Relationship-Aware Retrieval Planning

## Status

**Proposed** (MS4)

---

## Context

Up to **Milestone 3**, retrieval behavior in `rag-foundry-docgraph` is **purely semantic**:

* Vector similarity search operates over chunk embeddings
* DocumentNodes exist as organizational metadata
* DocumentRelationships are persisted but **unused**

This provides a stable, deterministic baseline — but it limits retrieval to **semantic proximity only**, ignoring explicit document structure such as:

* “explains”
* “decision_for”
* “derived_from”

As the system evolves, retrieval must begin to **respect intentional document structure** without introducing uncontrolled graph traversal or opaque behavior.

A key architectural concern is **separation of responsibilities**:

* Retrieval **planning** decides *what* documents are candidates
* Retrieval **execution** decides *how* content is fetched and ranked

This ADR introduces relationship awareness **only at the planning layer**, as the first controlled behavior change.

---

## Decision

Introduce a **Relationship-Aware Retrieval Planning** phase that precedes retrieval execution.

### Core Principles

1. **Planning, not execution**

   * Relationships influence *which documents are considered*
   * They do not affect scoring, ranking, or chunk retrieval yet

2. **One-hop expansion only**

   * Expansion is limited to **direct relationships**
   * No recursion, no traversal depth > 1

3. **Explicit and bounded**

   * Relationship expansion is deterministic
   * Behavior is observable and inspectable

4. **Backward-compatible**

   * Existing vector retrieval logic remains unchanged
   * If no relationships exist, behavior is identical to MS3

---

## Retrieval Planning Model

### Inputs

* Query (text or structured)
* Seed DocumentNodes (from semantic retrieval or explicit IDs)
* Optional allowed `relation_type` filters

---

### Planning Steps (High-Level)

1. **Seed Selection**

   * Identify initial DocumentNodes via semantic retrieval or direct reference

2. **Relationship Expansion**

   * For each seed document:

     * Include **outgoing** relationships only
     * Expand to directly related DocumentNodes (1 hop)

3. **Plan Assembly**

   * Produce a structured retrieval plan containing:

     * seed documents
     * expanded documents
     * relationship metadata (non-semantic)

---

### Outputs

A **Retrieval Plan**, not retrieved content.

Example (conceptual):

```text
RetrievalPlan:
  seed_documents: [D1, D2]
  expanded_documents:
    - D3 (via D1 -> explains)
    - D4 (via D2 -> decision_for)
  constraints:
    max_depth: 1
    traversal: disabled
```

---

## Non-Goals

This ADR explicitly does **not** introduce:

* Graph traversal algorithms
* Multi-hop expansion
* Relationship-based scoring or ranking
* Semantic weighting of relationships
* Cycle detection
* Automatic traversal based on LLM reasoning

These are **intentionally deferred** to future milestones.

---

## Consequences

### Positive

* Enables structure-aware retrieval incrementally
* Preserves determinism and debuggability
* Keeps behavior changes observable and reversible
* Creates a clear extension point for future graph retrieval

### Tradeoffs

* Relationships do not yet influence ranking
* Expansion may increase candidate set size without relevance guarantees
* Requires discipline to avoid accidental traversal creep

---

## Alignment with Existing ADRs

* **ADR-001 (DocumentNode)**
  → DocumentNode remains the unit of retrieval planning

* **ADR-002 (Relationship Model)**
  → Relationships are now *consulted*, not just stored

* **ADR-003 (Retrieval Strategy)**
  → Semantic retrieval remains primary signal

* **ADR-004 (Explicit Document Relationships)**
  → This ADR activates relationships in a controlled, non-traversal way

---

## Future Considerations (Out of Scope)

Potential future extensions include:

* Multi-hop traversal with explicit depth limits
* Relationship-type weighting
* Hybrid semantic + structural scoring
* User- or query-specific traversal rules
* Explainability tooling for graph-based retrieval

None of these are implied or enabled by this ADR.

---

## Summary

**ADR-005 marks the first intentional retrieval behavior change** by introducing relationship-aware planning while preserving execution stability.

It establishes a disciplined foundation for graph-aware retrieval without sacrificing predictability, testability, or architectural clarity.

---
