## rag-foundry-coderag\DOCS\adr\ADR-030-unified-artifact-graph.md
---

# ADR-030: Adopt Unified Artifact Graph with Repository Isolation

**Status:** Accepted
**Date:** 2026-02-12
**Supersedes:** None (first native ADR in this repo lineage)

---

## Context

This repository is evolving from a document-centric RAG system into a unified knowledge graph capable of representing:

* Documents
* Code artifacts (modules, classes, functions, methods, tests)
* Architectural Decision Records (ADRs)
* Relationships between all artifact types

The system must preserve the following architectural invariants:

1. Deterministic ingestion
2. No LLM usage during ingestion
3. Stable canonical identity for all artifacts
4. Rebuild-safe indexing
5. Cross-artifact traversal capability
6. Clear provenance tracking

As codebase intelligence support is added, a structural decision must be made regarding graph representation.

---

## Decision

We will adopt a **Unified Artifact Graph** model.

### Core Model

* All artifacts are stored in `document_nodes`
* All relationships are stored in `document_relationships`
* Artifact specialization is represented via:

```
artifact_type TEXT NOT NULL
```

No separate code-specific entity tables will be introduced.

---

### Repository Isolation

We will introduce:

```
repo_id UUID NOT NULL
```

to ensure repository isolation and prevent canonical ID collisions across multiple repositories.

All artifacts are uniquely identified by:

```
(repo_id, canonical_id)
```

Primary uniqueness constraint:

```
UNIQUE (repo_id, id)
```

All queries, traversals, and rebuild operations must be scoped by `repo_id`.

---

## Canonical Identity Model

Artifact IDs follow a deterministic structural format:

```
<relative_path>#<symbol_path>
```

Examples:

```
payments/stripe.py
payments/stripe.py#StripeClient
payments/stripe.py#StripeClient.charge
auth.py#login_user
```

Rules:

* No UUIDs for artifact identity
* No ingestion-order dependency
* IDs must be rebuild-stable
* IDs must be unique within a repository
* Global uniqueness is achieved via `(repo_id, id)`

Identity is derived solely from structural location in source.

(Full identity semantics are defined in ADR-031.)

---

## Deterministic Rebuild Rule

The ingestion process for a repository must be rebuild-safe.

On repository re-index:

1. All artifacts and relationships for `repo_id` are deleted.
2. The repository is fully reprocessed.
3. The resulting graph (IDs + relationships) must be identical to any previous ingestion of the same source state.

Incremental indexing is explicitly deferred to a future milestone.

Artifact identity must not depend on:

* Database-generated values
* UUIDs
* Timestamps
* Ingestion order
* Runtime state

If a rebuild produces different IDs or relationship topology for the same repository state, the ingestion implementation is incorrect.

---

## Rationale

### 1. Cross-Artifact Traversal

A unified graph enables:

* Code → Document linking
* Code → ADR linking
* Document → Code traceability
* Test coverage modeling
* Architectural impact analysis

Multiple graph tables would complicate traversal logic and introduce unnecessary join complexity.

---

### 2. Deterministic Ingestion

A unified schema ensures:

* A single ingestion model
* A single provenance model
* Consistent rebuild semantics
* Reduced risk of subsystem drift

Determinism is easier to enforce in a unified model than across parallel graph systems.

---

### 3. Architectural Simplicity

Alternative models introduce:

* Schema duplication
* Multiple traversal engines
* Divergent relationship logic
* Increased long-term maintenance burden

Unified graphs centralize graph reasoning and reduce conceptual fragmentation.

---

## Alternatives Considered

### Alternative 1 — Separate Graph Tables per Artifact Type

Example:

* `document_nodes`
* `code_entities`
* `adr_nodes`
* `test_nodes`

**Rejected because:**

* Introduces cross-graph joins
* Complicates traversal logic
* Encourages schema divergence
* Duplicates relationship modeling
* Harder to extend consistently

---

### Alternative 2 — Dedicated Graph Database (e.g., Neo4j)

**Rejected because:**

* Introduces operational complexity
* Splits persistence layer
* Requires dual storage models (vector + graph)
* Adds infrastructure overhead
* PostgreSQL is sufficient for current scale

Premature graph database adoption was deemed unnecessary.

---

### Alternative 3 — Embed Code Graph in JSONB Only

Store entire repository graph inside a single JSONB document.

**Rejected because:**

* No relational traversal
* No indexing support
* No efficient multi-hop queries
* Violates query-time graph reasoning goals

---

### Alternative 4 — Separate Code Intelligence Product

Maintain document RAG and code intelligence as independent systems.

**Rejected because:**

* Prevents cross-artifact reasoning
* Duplicates ingestion pipelines
* Splits architectural direction
* Adds long-term cognitive overhead

---

## Known Tradeoffs

### 1. Table Growth

Code graphs are significantly denser than document graphs.

Mitigation:

Add composite indexes such as:

```
(repo_id, artifact_type)
(repo_id, id)
```

Monitor row growth early.

Future partitioning by `repo_id` remains an option.

---

### 2. Graph Density

Code introduces high-connectivity edges:

* CALLS
* IMPORTS
* EXTENDS
* IMPLEMENTS
* TESTS
* COVERS

This increases traversal cost.

Mitigation:

* Depth-limited traversal
* Relationship-type filtering
* Future query caching

---

### 3. Metadata Drift

Metadata is stored in JSONB.

Risk:

* Inconsistent shapes
* Silent schema evolution

Mitigation:

* Document metadata schema per `artifact_type`
* Validate metadata during ingestion
* Avoid semantic enrichment in metadata

---

### 4. Static Analysis Limitations

Python is dynamic.

The CALLS graph represents:

* Static structural approximation
* Not runtime certainty

This limitation is accepted and documented.

---

## Consequences

### Positive

* Unified reasoning engine
* Clean extensibility
* Deterministic rebuild model
* Cross-domain linking
* Reduced schema fragmentation

### Negative

* Larger central tables
* Higher graph density
* Increased indexing requirements
* Slightly higher onboarding complexity

These tradeoffs are acceptable.

---

## Future Evolution

If graph density or performance becomes problematic:

* Partition tables by `repo_id`
* Add materialized traversal views
* Introduce query caching
* Extract code intelligence into a separate product if justified by scale

Current scale does not justify premature optimization.

---

## Final Position

We formally adopt the Unified Artifact Graph architecture with repository isolation.

This design:

* Aligns with system invariants
* Maximizes long-term flexibility
* Minimizes architectural fragmentation
* Preserves deterministic ingestion
* Enables cross-artifact intelligence

---

## Why This ADR Is Important

This ADR is the architectural anchor for the repository.

If future discussions arise such as:

* “Should we split code into separate tables?”
* “Should we introduce a graph database?”
* “Should we generate UUID-based artifact IDs?”

This document provides the governing rationale.

If performance issues arise, they must be evaluated against this decision with empirical data.

---

