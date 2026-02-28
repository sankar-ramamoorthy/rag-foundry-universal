---

# Ingestion Service (v3)

The **Ingestion Service** is responsible for processing raw documents and text sources into semantically enriched, persistent vector representations. It forms the first stage of the RAG (Retrieval-Augmented Generation) pipeline.

---

## Overview

The service provides:

1. **Validation** – Ensures input text is acceptable.
2. **Extraction** – Extracts structured artifacts (text blocks, images) from files (PDFs, etc.).
3. **Graph Assembly** – Builds a document graph capturing relationships between artifacts.
4. **Chunking** – Converts text or OCR content into manageable chunks.
5. **Embedding** – Generates vector embeddings for semantic search.
6. **Persistence** – Stores embeddings in the Vector Store for later retrieval.

---

## Core Components

### 1. **Pipeline**

* **Location:** `src/core/pipeline.py`
* **Class:** `IngestionPipeline`
* **Responsibilities:**

  * Entry points:

    * `run()`: full ingestion (validate → chunk → embed → persist)
    * `run_with_chunks()`: pre-chunked content (embed → persist)
  * Orchestrates all downstream services.
  * Manages metadata for provenance.

---

### 2. **Chunks**

* **Location:** `src/core/chunks.py`
* **Class:** `Chunk`
* **Responsibilities:**

  * Holds chunk content and metadata.
  * Optional OCR text support.
  * Unique `chunk_id` for traceability.

---

### 3. **Configuration**

* **Location:** `src/core/config.py`
* **Class:** `Settings`
* **Responsibilities:**

  * Application settings via environment variables.
  * Vector store URL, embedding provider, Ollama parameters.
  * Cached settings for efficiency.

---

### 4. **Database & Status Management**

* **Database session:** `src/core/database_session.py`
* **Status manager:** `src/core/status_manager.py`
* **Responsibilities:**

  * Track ingestion requests and state transitions (accepted → running → completed/failed).
  * Time-stamped, UTC-aware records.

---

### 5. **Document Extractors**

* **Base interface:** `src/core/extractors/base.py`
* **PDF extractor:** `src/core/extractors/pdf.py`
* **Responsibilities:**

  * Convert raw file bytes into ordered artifacts.
  * Support text and images.
  * Stateless, deterministic, and side-effect-free.

---

### 6. **Document Graph**

* **Builder:** `src/core/document_graph/builder.py`
* **Models:** `src/core/document_graph/models.py`
* **Responsibilities:**

  * Build deterministic artifact graphs.
  * Capture relationships (text → page, image → text/page).
  * Serves as input for chunk assembly.

---

### 7. **Chunkers**

* **Base:** `src/core/chunkers/base.py`
* **Text:** `src/core/chunkers/text.py`
* **Selector/Factory:** `src/core/chunkers/selector.py`
* **PDF Chunk Assembler:** `src/core/chunk_assembly/pdf_chunk_assembler.py`
* **Responsibilities:**

  * Chunk text or OCR content based on strategy.
  * Support multiple strategies: simple, sentence, paragraph.
  * Preserve metadata and artifact associations.
  * `PDFChunkAssembler` converts document graphs into structured chunks.

---

### 8. **Embedders**

* **Base:** `src/core/embedders/base.py`
* **Factory:** `src/core/embedders/factory.py`
* **Implementations:** `ollama.py`, `mock.py`
* **Responsibilities:**

  * Transform chunks into vector embeddings.
  * Plug-and-play providers: Ollama or Mock (for tests).
  * Handles batching and error handling.

---

### 9. **Vector Store Client**

* **Location:** `src/core/http_vectorstore.py`
* **Class:** `HttpVectorStore`
* **Responsibilities:**

  * Persist embeddings and metadata to vector store service.
  * Perform similarity searches.
  * Delete vectors by ingestion ID.
  * HTTP-based client with provider awareness.

---

## Data Flow (Simplified)

```
Raw Document (PDF/Text)
        │
        ▼
  Document Extractor
        │
        ▼
 Document Graph Builder
        │
        ▼
 PDF Chunk Assembler
        │
        ▼
    Chunker Factory
        │
        ▼
      Chunks
        │
        ▼
      Embedder
        │
        ▼
   HttpVectorStore
```

---

## Key Design Principles

* **Determinism:** Graphs and chunk IDs reproducible.
* **Provenance:** Metadata traces source, page, artifact, and chunk.
* **Extensibility:** Supports multiple extractors, chunkers, embedders.
* **Testability:** Mock embedders and chunkers enable deterministic testing.
* **Scalability:** Supports batch embeddings, handles large text gracefully.

---

## Notes

* All modules are decoupled to enable headless or API-driven ingestion.
* Embeddings are the interface point for downstream LLM and semantic services.
* Status transitions and persistence ensure robust monitoring and retry support.

---
