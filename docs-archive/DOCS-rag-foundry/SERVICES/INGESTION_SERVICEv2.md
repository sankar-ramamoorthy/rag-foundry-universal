---

# Ingestion Service (V2)

## Overview

The **Ingestion Service** is responsible for ingesting documents and other content sources, breaking them into chunks, embedding them, and persisting the embeddings into a vector store. It supports multiple content types, pre-chunked inputs (e.g., PDFs), and configurable embedding providers.

**Key Responsibilities:**

1. Validate input content
2. Chunk content (text, OCR, images)
3. Generate embeddings
4. Persist chunks and embeddings
5. Track ingestion status
6. Build document graphs for structured processing (e.g., PDFs)

**Entry Points:**

* `IngestionPipeline.run()`: Full pipeline for raw text ingestion
* `IngestionPipeline.run_with_chunks()`: Pre-chunked content ingestion (PDFs, OCR outputs)

---

## Architecture

The service is organized into several core components:

```
ingestion_service/
├─ src/core/
│  ├─ pipeline.py          # Orchestrates the ingestion pipeline
│  ├─ chunks.py            # Chunk data model
│  ├─ config.py            # Application configuration
│  ├─ database_session.py  # SQLAlchemy session management
│  ├─ http_vectorstore.py  # Vector store API client
│  ├─ models.py            # SQLAlchemy models (IngestionRequest)
│  ├─ status_manager.py    # Tracks ingestion status
│  ├─ extractors/          # Document extraction interfaces and PDF implementation
│  ├─ embedders/           # Embedding interfaces and providers (Ollama, Mock)
│  ├─ chunkers/            # Chunking strategies (text-based)
│  ├─ chunk_assembly/      # Assemble chunks from document graphs
│  └─ document_graph/      # Models and builder for document graph
```

---

## Components

### 1. **Pipeline (`pipeline.py`)**

The **`IngestionPipeline`** orchestrates the full ingestion workflow:

1. **Validation** via `_validator.validate()`
2. **Chunking** via a selected chunker (`_chunk()` or pre-chunked input)
3. **Embedding** via `_embedder.embed()`
4. **Persistence** to vector store (`_vector_store.persist()`)

**Usage:**

```python
pipeline.run(
    text="Some document content",
    ingestion_id="uuid",
    source_type="article",
    provider="provider_name",
)
```

For pre-chunked content (like PDFs):

```python
pipeline.run_with_chunks(chunks=pre_chunked_list, ingestion_id="uuid")
```

---

### 2. **Chunks (`chunks.py`)**

`Chunk` represents a minimal unit of content for embedding.

```python
@dataclass
class Chunk:
    chunk_id: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    ocr_text: Optional[str] = None
```

* `content`: Actual text or data
* `metadata`: Provenance and chunking information
* `ocr_text`: Optional OCR text if derived from image

---

### 3. **Configuration (`config.py`)**

`Settings` manages environment-driven configuration:

* `DATABASE_URL` → PostgreSQL
* `VECTOR_STORE_SERVICE_URL` → Vector store API
* `EMBEDDING_PROVIDER` → Default embedding provider (`ollama`, `mock`)
* `OLLAMA_*` → Ollama embedding API settings

---

### 4. **Database Session (`database_session.py`)**

Provides lazy SQLAlchemy session and engine creation:

```python
engine = get_engine()
SessionLocal = get_sessionmaker()
```

Used by `StatusManager` for tracking ingestion requests.

---

### 5. **Vector Store Client (`http_vectorstore.py`)**

`HttpVectorStore` manages persistence and retrieval of embeddings:

* `persist(chunks, embeddings, ingestion_id)` → Converts chunks to vectors and POSTs to vector store.
* `similarity_search(query_vector, k)` → Top-K nearest neighbors.
* `delete_by_ingestion_id(ingestion_id)` → Remove all vectors for a given ingestion.

Supports multiple providers and can be swapped for testing (mock).

---

### 6. **Embedders (`embedders/`)**

`BaseEmbedder` defines the interface. Implementations:

* **OllamaEmbedder** → Calls Ollama API to produce embeddings.
* **MockEmbedder** → Deterministic embeddings for testing.

**Factory (`factory.py`)** chooses embedder based on `provider`:

```python
embedder = get_embedder(provider="ollama")
```

---

### 7. **Chunkers (`chunkers/`)**

`BaseChunker` defines the interface for chunking content.

**TextChunker** supports:

* Simple fixed-size chunks
* Sentence-based chunks
* Paragraph-based chunks

**Selector (`selector.py`)** automatically chooses a strategy based on content length.

---

### 8. **Document Extractors (`extractors/`)**

* `DocumentExtractor` → Abstract base
* `PDFExtractor` → Extracts text and images from PDFs
* Extracted artifacts include metadata (`page_number`, `order_index`) and optional OCR text.

---

### 9. **Document Graph (`document_graph/`)**

* **`GraphNode`**: Represents an artifact
* **`GraphEdge`**: Connects artifacts (text→page, image→text, image→page)
* **`DocumentGraphBuilder`**: Builds a deterministic graph from extracted artifacts, preserving layout relationships.

---

### 10. **PDF Chunk Assembler (`chunk_assembly/pdf_chunk_assembler.py`)**

Transforms a `DocumentGraph` into chunks:

* Selects the text source: native text > OCR
* Delegates chunking to `ChunkerFactory`
* Assigns deterministic `chunk_id`s
* Preserves image → text associations in metadata

---

### 11. **Status Management (`status_manager.py`)**

Tracks ingestion lifecycle:

* `create_request()`: New ingestion request
* `mark_running()`, `mark_completed()`, `mark_failed()`
* Stores timestamps and error metadata

---

## Workflow Summary

1. **File ingestion** → `PDFExtractor` (or other extractor)
2. **Graph construction** → `DocumentGraphBuilder`
3. **Chunk assembly** → `PDFChunkAssembler`
4. **Embedding** → `OllamaEmbedder` or `MockEmbedder`
5. **Persistence** → `HttpVectorStore`
6. **Status update** → `StatusManager`

---

## Metadata Provenance

Each chunk and artifact contains rich metadata:

* Source file
* Page numbers
* Artifact IDs
* Associated image IDs
* Chunker strategy and parameters
* OCR text if available

This ensures traceability and deterministic embeddings for search.

---

