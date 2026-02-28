
**DOCS/DESIGN/current_ingestion_data_model.md**

# Dated 2026/01/29

⚠️ Superseded
This document reflects an earlier conceptual model of ingestion.
See ingestion-data-model-as-built.md for the authoritative current state
---

## Engineering Design Document

### Current Ingestion Data Model: Document vs Chunk

---

## 1. Purpose

This document describes the **current, as-built ingestion data model** in the RAG-Foundry platform, with a specific focus on how **documents**, **artifacts**, **graphs**, and **chunks** are represented, processed, and persisted.

The goal is to:

* Establish a shared, precise understanding of ingestion semantics
* Eliminate ambiguity around the meaning of “document” in the system
* Serve as a baseline reference for future architectural evolution

This document is **descriptive**, not prescriptive.

---

## 2. Scope

This document covers:

* The Ingestion Service (v3)
* Artifact extraction and document graph construction
* Chunk creation, embedding, and persistence
* The boundary between transient processing structures and persisted data

This document explicitly does **not** cover:

* Retrieval or RAG orchestration behavior
* LLM prompting or generation
* Future enhancements or design proposals

---

## 3. High-Level Summary

At present:

* **Documents are not persisted as first-class entities**
* **Chunks are the only persisted semantic unit**
* Document structure exists only transiently during ingestion
* Document graphs model **layout and artifact relationships**, not knowledge
* All downstream retrieval and reasoning is necessarily **chunk-centric**

---

## 4. Conceptual Layers in Ingestion

The ingestion pipeline implicitly operates across three conceptual layers:

### 4.1 Artifact Layer (Transient)

Artifacts represent extracted components of a source document, such as:

* Text blocks
* Images
* Pages

Artifacts are produced by document extractors and are **ephemeral**.

They are uniquely identified by:

* `source_file`
* `page_number`
* `order_index`
* `artifact_type`

Artifacts exist only during ingestion.

---

### 4.2 Document Graph Layer (Transient)

A **DocumentGraph** is constructed from extracted artifacts to capture **structural and layout relationships** within a single source document.

#### Characteristics

* Intra-document only (no cross-document links)
* Deterministic
* Page-scoped
* Artifact-level

#### Supported relationships

* `text_to_page`
* `image_to_text`
* `image_to_page`

#### Purpose

The document graph exists to:

* Preserve layout context
* Associate images with nearby text
* Enable structured chunk assembly

The document graph is **discarded after chunking** and is not persisted or exposed downstream.

---

### 4.3 Chunk Layer (Persisted)

Chunks are the **first persisted semantic unit** in the ingestion pipeline.

A chunk:

* Represents a bounded unit of text (or OCR output)
* Is generated deterministically
* Has a globally unique `chunk_id`
* Carries optional metadata
* Is embedded and stored for retrieval

Chunks are produced via configurable chunking strategies:

* Fixed character
* Sentence-based
* Paragraph-based

---

## 5. Chunk as the Primary Data Model

Chunks are the **authoritative ingestion output**.

### 5.1 Chunk Properties

Each chunk includes:

* `chunk_id` (UUID)
* `content` (text)
* Optional `ocr_text`
* Metadata (currently minimal)

Chunks do **not** explicitly reference:

* A document entity
* A document identifier
* Other chunks

Document context is inferred indirectly via metadata such as:

* `ingestion_id`
* `source_metadata`
* Page information (when available)

---

### 5.2 Chunk Persistence

Chunks are embedded and persisted in the Vector Store as individual rows.

The persisted vector schema includes:

* Chunk text
* Embedding vector
* Chunk strategy
* Chunk index
* Ingestion ID
* Source metadata
* Embedding provider

There is no persisted representation of:

* A document summary
* A document-level embedding
* Document-to-document relationships

---

## 6. Definition of “Document” in the Current System

In the current ingestion architecture, a “document” exists only as:

| Aspect                     | Status |
| -------------------------- | ------ |
| Input source               | ✔️     |
| Ingestion scope            | ✔️     |
| Graph construction context | ✔️     |
| Persisted entity           | ❌      |
| Retrieval unit             | ❌      |
| Attribution unit           | ❌      |

A document is therefore a **procedural concept**, not a persisted data model.

---

## 7. Implications

This design implies that:

* All downstream retrieval is **chunk-first**
* Semantic relevance is determined solely by vector similarity
* Structural and layout information is not available at retrieval time
* Context assembly aggregates chunks without explicit document intent
* Chunk provenance is traceable, but document intent is implicit

These implications are **intentional outcomes of the current design**, not defects.

---

## 8. Design Properties Preserved

The current ingestion data model strongly preserves:

* Determinism
* Provenance and traceability
* Stateless processing stages
* Clear service boundaries
* Testability via mock components
* Provider-agnostic embedding

These properties form the foundation for any future evolution.

---

## 9. Summary

The ingestion pipeline today is **chunk-centric by design**.

Documents:

* Serve as ingestion and processing scaffolding
* Are not persisted
* Are not retrieval units

Chunks:

* Are the sole persisted semantic artifact
* Are the basis for all downstream reasoning
* Carry provenance but not document intent

