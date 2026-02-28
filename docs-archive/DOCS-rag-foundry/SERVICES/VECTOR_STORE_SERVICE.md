---

# Vector Store Service   DOCS\SERVICES\VECTOR_STORE_SERVICE.md

## Overview

The **Vector Store Service (VSS)** is responsible for **persisting, retrieving, and managing vector embeddings** produced by the Ingestion Service. It provides a **PostgreSQL-backed vector store** (using `pgvector`) and exposes a REST API for batch insertion, similarity search, and deletion of vectors.

It **does not perform chunking, embedding generation, or LLM reasoning** — these are handled upstream by the Ingestion Service or external embedding providers.

---

## Responsibilities

1. **Vector Persistence**

   * Stores vectors with metadata in PostgreSQL using the `PgVectorStore`.
   * Supports batch insertion of vectors (`/v1/vectors/batch`).
   * Persists all relevant provenance data:

     * `ingestion_id`
     * `chunk_id`
     * `chunk_index`
     * `chunk_strategy`
     * `chunk_text`
     * `source_metadata`
     * `provider`

2. **Similarity Search**

   * Returns the top `k` most similar vectors for a query vector (`/v1/vectors/search`).
   * Uses **pgvector `<->` operator** for fast nearest-neighbor search.

3. **Vector Deletion**

   * Deletes all vectors associated with a specific `ingestion_id` (`/v1/vectors/by-ingestion/{ingestion_id}`).

4. **Ingestion Request Tracking**

   * Minimal ingestion tracking via `/v1/ingestions` endpoints.
   * Stores ingestion requests with timestamps and metadata.
   * Tracks ingestion lifecycle (`pending → running → completed/failed`).

5. **Schema Validation**

   * Validates the presence of the `ingestion_service.vectors` table and `vector` column at startup.
   * Provides fail-fast errors if the schema is missing or incompatible.

---

## Architecture

```
+---------------------+
|  Ingestion Service  |
|  (Document Graph,   |
|   Chunking, Embed)  |
+---------+-----------+
          |
          | Vector embeddings
          v
+---------------------+
| Vector Store Service|
|                     |
|  PgVectorStore      |
|  - PostgreSQL       |
|  - pgvector         |
|                     |
|  API Endpoints:     |
|   /v1/vectors       |
|   /v1/ingestions    |
+---------------------+
```

---

## API Endpoints

### Ingestions

* **POST /v1/ingestions**

  * Register a new ingestion request.
  * **Request:** `ingestion_id`, `source_type`, `metadata`
  * **Response:** status

### Vectors

* **POST /v1/vectors/batch**

  * Batch insert vectors with metadata.
  * **Request:** List of `VectorRecordAPI`
  * **Response:** `status` and `count`

* **POST /v1/vectors/search**

  * Search for similar vectors.
  * **Request:** `query_vector`, `k`
  * **Response:** List of top `k` vectors with metadata

* **DELETE /v1/vectors/by-ingestion/{ingestion_id}**

  * Delete all vectors for a given ingestion ID.

---

## Core Components

| Module                               | Responsibility                                                          |
| ------------------------------------ | ----------------------------------------------------------------------- |
| `core/vectorstore/base.py`           | Abstract base class `VectorStore` defining interface for vector stores. |
| `core/vectorstore/pgvector_store.py` | PostgreSQL-backed implementation using `pgvector`.                      |
| `core/config.py`                     | Provides settings and dependency injection for `PgVectorStore`.         |
| `api/v1/ingestions.py`               | API endpoints for managing ingestion requests.                          |
| `api/v1/vectors.py`                  | API endpoints for managing vectors.                                     |
| `db/migrations/`                     | Alembic migrations for `ingestion_requests` and `vectors` table.        |

---

## Database Schema

### `ingestion_service.vectors`

| Column          | Type        | Notes                               |
| --------------- | ----------- | ----------------------------------- |
| id              | SERIAL PK   | Unique row ID                       |
| vector          | vector(768) | Embedding vector (pgvector)         |
| ingestion_id    | UUID        | Link to ingestion request           |
| chunk_id        | TEXT        | ID of the source chunk              |
| chunk_index     | INT         | Chunk index in the document         |
| chunk_strategy  | TEXT        | Strategy used for chunking          |
| chunk_text      | TEXT        | Text of the chunk                   |
| source_metadata | JSONB       | Arbitrary metadata about the source |
| provider        | TEXT        | Embedding provider used             |

### `ingestion_service.ingestion_requests`

| Column             | Type      | Notes                            |
| ------------------ | --------- | -------------------------------- |
| ingestion_id       | UUID PK   | Unique ingestion request ID      |
| source_type        | TEXT      | Source type (PDF, DOCX, etc.)    |
| ingestion_metadata | JSON      | Optional metadata                |
| status             | TEXT      | pending/running/completed/failed |
| created_at         | TIMESTAMP | Creation time                    |
| started_at         | TIMESTAMP | Start time                       |
| finished_at        | TIMESTAMP | Finish time                      |

---

## Configuration

Environment variables (via `.env` or Docker):

* `DATABASE_URL` – PostgreSQL DSN
* `VECTOR_DIMENSION` – Dimension of embedding vectors (default: 768)
* `EMBEDDING_PROVIDER` – e.g., `ollama`, `mock`
* `OLLAMA_BASE_URL` – URL for Ollama embedding API
* `OLLAMA_EMBED_MODEL` – Model name for embedding
* `OLLAMA_BATCH_SIZE` – Batch size for embedding calls

---

## Notes

* **PgVectorStore** is **strictly typed** and validated at startup to prevent runtime errors.
* Embeddings are **immutable** once inserted.
* Current ingestion tracking is lightweight; full ingestion lifecycle logic is expected to be driven by orchestration pipelines.
* The service is designed to be **stateless** aside from the database; it can scale horizontally behind a load balancer.

---


