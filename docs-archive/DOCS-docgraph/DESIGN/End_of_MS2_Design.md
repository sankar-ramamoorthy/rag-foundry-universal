# Design Notes — rag-foundry-docgraph

This document captures **design intent**, **constraints**, and **non-goals** as of **Milestone 2**.

It exists to prevent accidental architectural drift.

---

## Design Principles

1. **Documents before chunks**
2. **Explicit structure over implicit behavior**
3. **Persistence before intelligence**
4. **Predictability over cleverness**

Every design choice in Milestone 2 reinforces these principles.

---

## Why DocumentNodes Exist

Traditional RAG systems treat documents as:

> “a loose bag of chunks”

This causes:

* loss of provenance
* brittle retrieval
* poor explainability
* no place for relationships

`DocumentNode` solves this by acting as:

* a **semantic container**
* a **relationship endpoint**
* a **stable identity**

Even when retrieval ignores it (for now).

---

## DocumentNode — Responsibilities

A `DocumentNode`:

* represents a logical document
* owns document-level metadata
* groups vector chunks
* anchors future relationships

A `DocumentNode` **does not**:

* perform retrieval
* rank results
* embed content
* execute reasoning

---

## VectorChunk — Responsibilities

A `VectorChunk`:

* stores embedded text
* participates in similarity search
* belongs to exactly one DocumentNode

VectorChunks remain intentionally simple.

---

## ORM & Persistence Model

The ORM mirrors the database exactly.

* No polymorphism
* No inheritance tricks
* No hidden joins

### Relationships

* `DocumentNode → VectorChunk` : one-to-many
* `VectorChunk → DocumentNode` : many-to-one

This simplicity is intentional.

---

## Alembic & Migrations

* All schema changes are Alembic-managed
* pgvector is enabled explicitly
* Schema is namespaced (`ingestion_service`)
* Migrations are environment-driven via `DATABASE_URL`

Autogeneration is supported but constrained to avoid noise.

---

## Testing Philosophy

### Why integration tests use real embeddings

Mock embeddings hide the most dangerous failures:

* dimension mismatch
* dtype errors
* serialization issues
* provider drift

Integration tests are **truth tests**, not performance tests.

---

## Explicit Non-Goals (Milestone 2)

The following are intentionally **out of scope**:

* relationship traversal
* graph-aware retrieval
* document reranking
* reasoning chains
* agent behavior

These are deferred to later milestones.

---

## Forward Compatibility

Milestone 2 enables (but does not implement):

* document-to-document relationships
* multi-hop retrieval
* hierarchical reasoning
* explainable retrieval paths

All future intelligence builds on this foundation.

---

## Final Note

If you are reading this and wondering:

> “Why isn’t DocumentNode used yet?”


That is the design.
Structure comes before behavior.
