# ADR-001: DocumentNode as First-Class Retrieval Unit

**Status:** Proposed  
**Milestone:** MS1  
**Issue:** MS1-IS2-ADR-001  
**Date:** 2026-01-31  

---

## Context

In the current `rag-foundry` system:

- Chunks of text are the atomic retrieval unit.
- Documents exist implicitly but are not tracked as explicit entities.
- Retrievals often mix unrelated chunks from multiple documents.
- LLM prompts are polluted with irrelevant or stale context.
- Debugging or tracing why a chunk was included is difficult.

**Problem:**  
Without a conceptual layer above chunks, agents (or RAG orchestrators) **cannot reason over document intent**. The system suffers from:

1. **Cross-document semantic bleed** — unrelated chunks influence reasoning.  
2. **Prompt pollution** — more tokens used than necessary.  
3. **Untraceable context** — no clear link from chunk to its source intent.

---

## Decision

Introduce a **`DocumentNode`** entity as a **first-class retrieval unit**:

- Each document ingested is represented by a `DocumentNode`.
- Fields of `DocumentNode`:

| Field | Type | Description |
|-------|------|-------------|
| `document_id` | UUID / TEXT | Unique identifier for the document |
| `title` | TEXT | Document title or short description |
| `summary` | TEXT | LLM-generated summary of the document content |
| `summary_embedding` | VECTOR | Embedding of the summary for semantic search |
| `source` | TEXT | Original file, URL, or ingestion source |
| `ingestion_id` | UUID | Foreign key linking to the ingestion request |
| `doc_type` | TEXT | Categorization (e.g., design, decision, reference) |

**Key Principles:**

1. **Embed the summary, not the full document**, to keep embeddings small and stable.  
2. **Chunk embeddings still exist**, but they are **secondary**; document-level retrieval comes first.  
3. This introduces a **conceptual layer** for retrieval without changing the ingestion or RAG orchestrator behavior.  

---

## Consequences

**Pros:**

- Clear, traceable retrieval unit for reasoning and debugging.  
- Reduces prompt bloat and irrelevant context.  
- Easier to introduce relationships between documents later.  

**Cons / Trade-offs:**

- Slight increase in ingestion complexity (summary generation + embeddings).  
- Existing retrieval logic needs to account for the new layer eventually (but no behavior change yet).  

---

## Next Steps

1. Define the **database table and Alembic migration** for `DocumentNode`.  
2. Create **unit tests for document ingestion** with summaries and embeddings.  
3. Leave chunk-level retrieval unchanged (for now).  

---

## References

- [GraphRAG Conceptual Notes](https://www.example.com) *(internal reference)*  
- Milestone 2 plan: Document Nodes implementation.  
