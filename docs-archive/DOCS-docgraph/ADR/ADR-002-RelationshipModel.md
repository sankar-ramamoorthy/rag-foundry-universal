# ADR-002: Explicit Relationship Model Between DocumentNodes

**Status:** Proposed  
**Milestone:** MS1  
**Issue:** MS1-IS3-ADR-002  
**Date:** 2026-01-31  

---

## Context

Currently, `rag-foundry` uses **flat semantic similarity** for retrieval:

- Chunks are retrieved solely by embeddings.
- There is **no explicit representation of relationships** between documents.
- The orchestrator cannot distinguish **why a document is connected to another**.
- Expansion of context is unbounded and may include irrelevant chunks.

**Problem:**  
Without explicit relationships:

1. Context assembly is **non-deterministic**.  
2. Intent of connections (e.g., explanation vs implementation) is **lost**.  
3. Debugging retrieval and reasoning chains is difficult.  

---

## Decision

Introduce a **lightweight, explicit relationship model** between `DocumentNode`s:

### `DocumentRelation` Entity

| Field | Type | Description |
|-------|------|-------------|
| `from_document_id` | UUID / TEXT | Source document in the relationship |
| `to_document_id` | UUID / TEXT | Target document being referenced |
| `relation_type` | TEXT | Type of relationship (e.g., `explains`, `implements`, `decision_for`, `example_of`, `supersedes`, `references`) |

### Key Principles

1. **Keep it dumb**: No embeddings, no recursive traversal, no agent reasoning.  
2. **Typed edges**: Make the relationship **explicit and auditable**.  
3. **Directed graph**: Allows controlled context expansion.  
4. **Database-backed**: Simple PostgreSQL table; queried only by orchestrator.  
5. **Automatic or manual**: Some edges can be inferred during ingestion, others curated manually.  

---

## Consequences

**Pros:**

- Introduces **intent** into retrieval (“this document explains another”).  
- Context expansion can be **bounded** by relationship type and hops.  
- Supports future enhancements like **GraphRAG-style retrieval** without changing current behavior.  
- Improves **debuggability** and **traceability**.

**Cons / Trade-offs:**

- Slight schema complexity (new table and edges).  
- Relationships must be maintained as documents are updated.  
- Initial ingestion may need additional logic to populate edges.  

---

## Next Steps

1. Define **database table and Alembic migration** for `DocumentRelation`.  
2. Implement basic ingestion hooks for populating relationships (optional for MS2).  
3. Keep retrieval logic unchanged for now; this ADR only documents the model.  

---

## References

- [GraphRAG Conceptual Notes](https://www.example.com) *(internal reference)*  
- Milestone 2 plan: DocumentNodes + relationships implementation.
