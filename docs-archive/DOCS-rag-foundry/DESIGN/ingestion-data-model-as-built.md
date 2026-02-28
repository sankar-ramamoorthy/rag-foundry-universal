### DOCS/DESIGN/ingestion-data-model-as-built.md


---

# Ingestion Data Model – As Built

**Date:** 2026-01-21
**Status:** Authoritative (Current State)
**Scope:** Ingestion, Chunking, Vector Persistence, Provenance
**Non-Goals:** Future design, agentic RAG, GraphRAG, attribution improvements

---

## 1. Purpose and Scope

This document describes the **current ingestion data model as implemented** in the RAG Foundry platform.

It captures how **documents, chunks, vectors, and provenance** are represented today across the Ingestion Service and Vector Store Service, based on:

* production code
* database schemas
* real persisted data

This document is intentionally **descriptive, not prescriptive**.

> It reflects the system *as built*, not as aspirationally designed.

---

## 2. Core Concepts and Definitions

### Document

A **Document** represents a single ingestion unit (e.g. file, image, bytes payload).
In the current system, a Document is **not a standalone persisted entity**.

**Document identity is represented by an ingestion request.**

---

### Ingestion Request

An **Ingestion Request** is the authoritative, persisted representation of a Document.

* Stored in `ingestion_service.ingestion_requests`
* Identified by a stable `ingestion_id` (UUID)
* Owns lifecycle state and document-level metadata

> **Document == Ingestion Request**

---

### Chunk

A **Chunk** is a semantically meaningful slice of extracted content produced during ingestion.

* Generated deterministically by chunkers
* Identified by a `chunk_id` (UUID)
* May represent sentences, paragraphs, or fixed-size text
* Does not directly reference a Document

Chunks are **ephemeral in memory** and **persist only via vector records**.

---

### Vector

A **Vector** is the persisted semantic representation of a Chunk.

* Stored in `ingestion_service.vectors`
* Contains an embedding plus associated metadata
* Acts as the persistence boundary between ingestion and retrieval

---

### Document Graph

A **Document Graph** is a transient structure built during ingestion to model relationships between extracted artifacts (text, images, pages).

* Exists only in-memory
* Used for chunk assembly
* Not persisted
* Not queryable downstream

---

## 3. Ingestion Request (Document-Level Model)

### Storage

`ingestion_service.ingestion_requests`

| Column                                  | Purpose                                                     |
| --------------------------------------- | ----------------------------------------------------------- |
| `ingestion_id`                          | Stable document identifier                                  |
| `source_type`                           | High-level source classification (file, image, bytes, etc.) |
| `ingestion_metadata`                    | Document-level metadata (e.g. filename)                     |
| `status`                                | Lifecycle state                                             |
| `created_at / started_at / finished_at` | Timestamps                                                  |

### Key Properties

* This table is the **only persisted document-level entity**
* All chunks and vectors relate to a document **indirectly** via `ingestion_id`
* Lifecycle tracking is **document-scoped**, not chunk-scoped

---

## 4. Chunk Model (Current State)

### In-Memory Representation

```python
@dataclass
class Chunk:
    chunk_id: str
    content: Any
    metadata: Dict[str, Any]
    ocr_text: Optional[str]
```

### Characteristics

* `chunk_id` is generated per chunk (UUID)
* Chunks are produced by strategy-specific chunkers
* Chunk metadata is minimal and strategy-oriented
* Chunks do **not** embed document identity directly

Chunks are **not persisted as first-class records**.

---

## 5. Vector Records (Persistence Boundary)

### Storage

`ingestion_service.vectors`

| Column            | Description                     |
| ----------------- | ------------------------------- |
| `vector`          | pgvector embedding              |
| `ingestion_id`    | Indirect document reference     |
| `chunk_id`        | Chunk identifier                |
| `chunk_index`     | Chunk ordering within ingestion |
| `chunk_strategy`  | Strategy used                   |
| `chunk_text`      | Text content of chunk           |
| `source_metadata` | JSON metadata                   |
| `provider`        | Embedding provider              |

---

### 5.1 What `source_metadata` Represents

Real persisted examples show `source_metadata` containing:

```json
{
  "provider": "ollama",
  "chunk_text": "...",
  "source_type": "file",
  "chunker_name": "text_chunker",
  "chunk_strategy": "sentence",
  "chunker_params": {
    "chunk_size": 200,
    "overlap": 20
  }
}
```

**This metadata is process-oriented**, not provenance-oriented.

It captures:

* how a chunk was produced
* which strategy and parameters were used

---

### 5.2 What `source_metadata` Does NOT Represent

`source_metadata` does **not** include:

* document name or title
* filename
* page number
* artifact ID
* document graph node identity
* stable document reference

> Document identity exists relationally (via `ingestion_id`), not embedded in chunk metadata.

---

### 5.3 Duplication Note

`chunk_text` exists:

* as a dedicated column
* duplicated inside `source_metadata`

This reflects historical convenience rather than semantic intent.

---

## 6. Document Graph (Transient Assembly Structure)

### Purpose

During ingestion, a Document Graph is constructed to:

* model relationships between extracted artifacts
* associate images with nearby text
* preserve ordering and locality
* support structured chunk assembly (e.g. PDFs)

### Lifecycle

* Built during ingestion
* Used by chunk assemblers
* Discarded after chunk generation

### Persistence

* Graph nodes and edges are **not stored**
* Artifact IDs are **not persisted**
* Page-level relationships are **not recoverable downstream**

> The Document Graph is an ingestion-time assembly aid, not a stored knowledge representation.

---

## 7. Provenance and Attribution (Current Capabilities)

### 7.1 What Is Supported

* Document-level provenance via `ingestion_id`
* Chunk-level traceability via vector records
* Deterministic reproduction of embeddings

---

### 7.2 What Is Not Supported

* Page-level attribution
* Artifact-level attribution
* Graph-aware retrieval
* Answer-level causal attribution
* Auditable citation from LLM output

These limitations are structural and arise from:

* non-persisted document graphs
* chunk-only retrieval
* context concatenation in RAG orchestration

---

## 8. Implications for RAG Orchestration

Under current contracts:

* The RAG Orchestrator retrieves **chunks**, not documents
* Context assembly concatenates `chunk_text`
* Chunk identity is lost during prompt construction
* Returned “sources” are informational labels, not evidence

> Source attribution is therefore coarse-grained and non-auditable by design.

This is a **contractual limitation**, not a data availability issue.

---

## 9. Summary: Current State Snapshot

* Document identity exists and is stable (`ingestion_requests`)
* Chunk identity exists but is indirect
* Document graphs are transient and non-persisted
* Vector records are the sole persistence boundary
* Provenance is relational, not embedded
* Attribution is limited by orchestration contracts

This document establishes the **baseline reality** against which future architectural decisions, ADRs, and design proposals can be evaluated.

---
