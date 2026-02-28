# Ingestion ↔ Retrieval Expectations

**Status:** Informational / Contract-Aligned
**Scope:** Interaction between Ingestion and Retrieval domains

---

## Relationship Overview

- Ingestion is a black-box producer of retrieval-ready artifacts.
- Retrieval is a consumer of ingestion outputs.
- There is no direct coupling between the two services.

Ingestion prepares data for retrieval but does not participate in query-time logic.

---

## Ingestion Guarantees

The ingestion service guarantees:

- Stable `document_id` identifiers
- Deterministic `chunk_id` identifiers
- Preservation of raw extracted text
- Preservation of OCR output
- Preservation of document metadata
- Idempotent ingestion (based on content hash)

Ingestion may optionally:
- Generate embeddings
- Store embeddings
- Recompute embeddings

These behaviors are configurable and not guaranteed.

---

## Retrieval Assumptions

Retrieval may assume:

- Chunks are addressable by `document_id`
- Chunk content is immutable post-ingestion
- Metadata is queryable
- Re-embedding is possible if models change

Retrieval must not assume:

- A specific chunking strategy
- A specific embedding model
- The presence of embeddings
- Knowledge of ingestion’s internal schema

---

## Data Access Patterns

Preferred access patterns:

1. API-based access
   Retrieval queries ingestion endpoints for metadata or artifacts.

2. Database read-only access
   Retrieval may read from ingestion-owned schemas.
   Write access is not permitted.

---

## Evolution & Failure Tolerance

- Chunking strategies may evolve over time.
- Existing chunks remain valid.
- Mixed generations of chunks must be tolerated.

This enables safe iteration without re-ingestion of all content.
