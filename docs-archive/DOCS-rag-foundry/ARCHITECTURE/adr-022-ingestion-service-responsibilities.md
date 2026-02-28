---

# ADR-022: Responsibilities of the Ingestion Service

## Status

Proposed

## Context

In our RAG pipeline, multiple services handle document processing, embedding, and retrieval. There is a need to clearly define **what the Ingestion Service (IS) is responsible for** versus other services (like the LLM/semantic service), to avoid overlap, ensure maintainability, and enforce clear interfaces.

---

## Decision

The **Ingestion Service (IS)** is responsible for:

1. **Document Intake and Validation**

   * Accept raw documents (PDFs, text files, images, etc.).
   * Validate file types, encodings, and basic integrity.

2. **Artifact Extraction**

   * Extract structured content into `ExtractedArtifact`s:

     * Native text
     * OCR text
     * Images
   * Include ordering metadata (`order_index`) and page numbers.

3. **Document Graph Construction**

   * Build deterministic `DocumentGraph`s from artifacts.
   * Capture relationships:

     * Text → Page (`text_to_page`)
     * Image → Text (`image_to_text`)
     * Image → Page fallback (`image_to_page`)
   * Serve as canonical representation for downstream chunking and embeddings.

4. **Chunking / Chunk Assembly**

   * Convert document graph text content into `Chunk`s.
   * Preserve metadata:

     * Source file, page numbers, artifact IDs
     * Associated images
     * Chunk strategy, chunker name, chunker parameters
   * Support multiple strategies (simple, sentence, paragraph).

5. **Embedding**

   * Convert chunks into vector embeddings.
   * Use pluggable embedding providers (Ollama, Mock).
   * Handle batching, error handling, and deterministic IDs.

6. **Persistence**

   * Store embeddings, metadata, and ingestion status in the Vector Store.
   * Maintain provenance for retrieval and traceability.

7. **Monitoring / Status Management**

   * Track ingestion request lifecycle:

     * accepted → running → completed/failed
   * Provide timestamps and diagnostic metadata.

---

### Explicit Non-Responsibilities

The **Ingestion Service does NOT**:

* Perform **LLM-driven reasoning or retrieval** at query time.
* Generate summaries, answers, or recommendations.
* Handle real-time user queries beyond ingestion.
* Manage semantic search logic or ranking (delegated to downstream services).

---

## Consequences

* Clear separation of concerns:

  * IS focuses entirely on **data preparation, enrichment, and storage**.
  * Semantic/LLM services focus on **query-time reasoning and retrieval**.
* Deterministic chunk IDs and graph edges improve reproducibility.
* Adding new extractors, chunkers, or embedders does not require changes in the LLM service.
* IS becomes the single source of truth for document-derived content.

---

## References

* `src/core/document_graph/` – Graph building
* `src/core/chunkers/` – Chunk assembly
* `src/core/embedders/` – Embedding interface

---
