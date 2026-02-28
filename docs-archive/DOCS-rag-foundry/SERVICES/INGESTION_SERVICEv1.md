
# Ingestion Service v1

**Service Name:** `ingestion_service`
**Code Path:** `ingestion_service/src`
**Primary Responsibility:** Extract, chunk, embed, and persist content from documents into a vector store for downstream semantic search and retrieval.

---

## Overview

The Ingestion Service is responsible for **transforming raw content into embeddings and storing them** in a vector database. It handles:

* File ingestion (PDFs, text, images)
* Content extraction (text blocks, images, OCR)
* Chunking and metadata annotation
* Embedding generation
* Persistence to a vector store
* Status tracking for ingestion requests

It exposes both **API endpoints** for external ingestion requests and internal **pipeline components** for programmatic use.

---

## Key Components

### 1. Pipeline

**File:** `core/pipeline.py`
**Class:** `IngestionPipeline`

**Responsibilities:**

* Orchestrates the end-to-end ingestion flow:

  1. Validate content
  2. Chunk content
  3. Generate embeddings
  4. Persist chunks and embeddings

* Supports two entry points:

  * `run()`: Full pipeline for raw text
  * `run_with_chunks()`: Pipeline for pre-chunked content (e.g., PDFs)

**Key Features:**

* Adds provenance metadata to each chunk (e.g., chunker used, source type, provider)
* Ensures the number of embeddings matches the number of chunks
* Works with a pluggable embedder and vector store

---

### 2. Chunk Model

**File:** `core/chunks.py`
**Class:** `Chunk`

Represents a piece of content ready for embedding.
**Fields:**

* `chunk_id`: Unique identifier
* `content`: Text or other content
* `metadata`: Dictionary for provenance and additional info
* `ocr_text`: Optional OCR text for image-based chunks

---

### 3. Extractors

**Files:** `core/extractors/base.py`, `core/extractors/pdf.py`
**Classes:** `DocumentExtractor`, `PDFExtractor`

**Responsibilities:**

* Transform raw files (PDF, images) into ordered **artifacts**
* Support multiple artifact types: `text`, `image`
* Track provenance: source file, page number, order index
* **PDFExtractor** extracts:

  * Text blocks with bounding boxes
  * Embedded images
* Designed to be stateless and deterministic

---

### 4. Embedders

**Files:** `core/embedders/*`
**Key Classes:**

* `BaseEmbedder` (interface)
* `MockEmbedder` (deterministic, for testing)
* `OllamaEmbedder` (production, calls Ollama API)

**Responsibilities:**

* Generate embedding vectors for `Chunk` objects
* Support multiple providers via `factory.get_embedder()`
* Handle batching, API calls, and errors

---

### 5. Vector Store Integration

**File:** `core/http_vectorstore.py`
**Class:** `HttpVectorStore`

**Responsibilities:**

* Persist chunks and embeddings to a remote vector store service
* Provide operations:

  * Batch insert (`add_vectors`)
  * Similarity search (`similarity_search`)
  * Delete by ingestion ID (`delete_by_ingestion_id`)
* Adds chunk metadata to vector store records

---

### 6. Status Management

**File:** `core/status_manager.py`
**Class:** `StatusManager`

**Responsibilities:**

* Track ingestion requests in the database (`IngestionRequest` model)
* Maintain request lifecycle: `accepted → running → completed/failed`
* Record timestamps and errors for auditing and retries

---

### 7. Configuration and Database

**Files:** `core/config.py`, `core/database_session.py`, `core/models.py`

* `Settings`: Pydantic settings for environment configuration
* Database session factory for SQLAlchemy
* `IngestionRequest` model for tracking requests in Postgres

---

## API Layer

**Files:** `api/v1/ingest.py`
**Responsibilities:**

* Exposes ingestion endpoints:

  * Accept new ingestion requests
  * Trigger pipeline execution
* Returns status and ingestion ID for tracking

---

## UI (Optional)

**File:** `ui/gradio_app.py`

* Gradio-based UI for manual document ingestion
* Allows users to upload documents, view chunking and embeddings

---

## Data Flow

```
[Raw Document] --> [Extractor] --> [Chunker] --> [Embedder] --> [Vector Store]
                                    ↑
                              [Status Manager]
```

* Extractor produces **artifacts** with provenance
* Chunker transforms text/artifacts into **chunks** with metadata
* Embedder converts chunks into **vectors**
* Vector store persists **embeddings** for semantic search
* Status manager tracks **request lifecycle**

---

## Design Notes

* Fully decoupled components for extensibility (extractors, chunkers, embedders)
* Stateless extractors; embedder and vector store are externalized
* Provenance tracking is consistent across chunks and embeddings
* Supports both **raw text** and **pre-chunked ingestion** (PDFs, OCR)

---
