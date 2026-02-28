# DOCS/DESIGN/document_ingestion_architecture.md

---

# Document Ingestion Architecture & Design

## Overview

This document describes the architecture and design principles of the **Agentic RAG Ingestion Pipeline**, with a focus on:

* Extraction
* Document graph construction
* Chunk assembly
* Chunking strategies
* Determinism and provenance

The system is intentionally designed as a **layered, deterministic pipeline** where each stage has a single responsibility and is independently testable.

---

## Core Design Principles

### 1. Separation of Concerns

Each stage in the ingestion pipeline does exactly one job:

| Stage          | Responsibility                                |
| -------------- | --------------------------------------------- |
| Extractor      | Parse raw bytes into ordered artifacts        |
| Document Graph | Capture semantic and structural relationships |
| Chunk Assembly | Convert artifacts into chunkable units        |
| Chunking       | Split content into LLM-ready chunks           |
| Embedding      | Vectorize chunks                              |
| Persistence    | Store vectors and metadata                    |

No stage leaks responsibilities into another.

---

### 2. Determinism by Construction

The system is designed so that:

* The same input bytes always produce the same artifacts
* The same artifacts always produce the same graph
* The same graph always produces the same chunks
* Chunk IDs and metadata are stable across runs

This is critical for:

* Reproducibility
* Debuggability
* Incremental re-ingestion
* Trust in embeddings

---

### 3. Immutability of Facts

Extracted artifacts are immutable. Once something is extracted, it is treated as a **fact about the document**, not an opinion or interpretation.

---

## Mental Model (End-to-End)

```
Raw document bytes
        ↓
Extractor
  (what exists?)
        ↓
ExtractedArtifact[]
  (immutable facts)
        ↓
DocumentGraph
  (relationships)
        ↓
ChunkAssembler
  (semantic grouping)
        ↓
Chunks
  (LLM-ready units)
        ↓
Embedder → Vector Store
```

Each arrow represents a **one-way transformation**.
No stage mutates upstream data.

---

## Extractors

### `DocumentExtractor` (Abstract Base Class)

```python
class DocumentExtractor(ABC):
    @abstractmethod
    def extract(self, file_bytes: bytes, source_name: str) -> List[ExtractedArtifact]:
        ...
```

#### Why it is abstract

`DocumentExtractor` is intentionally not implemented because extraction is **format-specific**:

* PDF
* DOCX
* HTML
* Image (OCR)
* Audio (ASR)

Each format has fundamentally different parsing logic, but downstream stages should not care.

This abstraction guarantees that **all extractors produce the same internal model**, regardless of source format.

---

### `ExtractedArtifact`

```python
@dataclass(frozen=True)
class ExtractedArtifact:
    type: Literal["text", "image"]
    source_file: str
    page_number: int
    order_index: int
    text: Optional[str]
    image_bytes: Optional[bytes]
```

#### Design rationale

* **Frozen / immutable**
  Prevents accidental mutation across pipeline stages.
* **Order-aware**
  `order_index` preserves reading order.
* **Provenance-aware**
  Page numbers and source file are always known.
* **Internal-only**
  Not persisted or exposed via APIs.

Artifacts answer one question only:

> “What exists in the document, and where?”

They do **not**:

* chunk
* embed
* infer meaning
* apply heuristics

---

## Document Graph

The `DocumentGraph` captures relationships between artifacts.

### Why a graph?

Documents are not flat:

* Images relate to text
* Text belongs to pages
* Future: tables, captions, footnotes

The graph allows us to express these relationships explicitly.

### Current relations

* `text_to_page`
* `image_to_text`
* `image_to_page` (fallback)

The graph is:

* deterministic
* order-preserving
* free of layout heuristics (for now)

---

## Chunk Assembly

### Role of `PDFChunkAssembler`

The assembler bridges **document understanding** and **chunking strategy**.

Responsibilities:

* Select only chunkable artifacts (text)
* Preserve lineage (artifact IDs, pages, images)
* Delegate chunking to real chunkers
* Produce deterministic chunk IDs

The assembler **does not decide how to chunk text**.
It decides **what text is eligible to be chunked**.

---

## Chunking

### Chunkers (`BaseChunker`, `TextChunker`)

Chunkers are responsible for **how text is split**, not where it came from.

Examples:

* Fixed character chunking
* Sentence-based chunking
* Paragraph-based chunking

Chunkers:

* are stateless
* can be swapped dynamically
* are selected via `ChunkerFactory`

---

### `ChunkerFactory`

```python
ChunkerFactory.choose_strategy(content)
```

This allows:

* Heuristic-based chunking
* Future LLM-driven chunking
* Content-aware decisions

Chunking strategy is recorded in chunk metadata for auditability.

---

## Chunks

### `Chunk`

```python
@dataclass
class Chunk:
    chunk_id: str
    content: Any
    metadata: Dict[str, Any]
```

Chunks are:

* The **unit of embedding**
* The **unit of retrieval**
* Fully traceable back to source artifacts

Each chunk contains:

* `chunk_strategy`
* `chunker_name`
* `chunker_params`
* `artifact_ids`
* `page_numbers`
* `associated_image_ids`

---

## Deterministic Chunk IDs

Chunk IDs follow this pattern:

```
{artifact_id}:chunk:{index}
```

This guarantees:

* Stability across runs
* Easy debugging
* Precise traceability

---

## Why Chunking Is Not Done in Extractors

Chunking depends on:

* Model constraints
* Retrieval strategy
* Use case
* Content length

Extractors must remain **pure parsers**.

If extractors chunked text:

* You would hard-code model assumptions
* You would lose flexibility
* You would violate separation of concerns

---

## Extensibility

This design supports future extensions without rewrites:

* OCR integration
* Layout-aware chunking
* Cross-page text merging
* Caption-aware image chunks
* Multimodal chunking
* Agent-driven chunk strategy selection

All without changing:

* Extractors
* Graph models
* Pipeline contracts

---

## Summary

This ingestion architecture is designed to be:

* Deterministic
* Explainable
* Testable
* Extensible
* Model-agnostic

Each layer answers one question, and no more.

> **Extraction finds facts.
> Graphs define relationships.
> Chunkers decide meaning.**

---
