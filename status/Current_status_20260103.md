```
status/current_status_20260103.md
```

---

## 📅 **Current Status: IS2-MS2a — Persistent Vector Storage (pgvector)**

### **Date**: **2026-01-03**

---

## 🧭 **Milestone Context**

**IS2-MS2a Goal**
Introduce durable, restart-safe persistence for:

* ingestion requests
* ingestion status
* chunked document vectors

using PostgreSQL + pgvector, with Docker-based integration tests.

This milestone replaces **all in-memory persistence** with **database-backed state**, while keeping the API contract stable.

---

##  **What Is Now Fully Completed**

### 1. **Database-Backed Ingestion Lifecycle**

* Ingestion requests are **persisted in PostgreSQL** (`ingestion_requests` table).
* Status transitions are durable across restarts:

  * `accepted`
  * `running`
  * `completed`
  * `failed`
* `/v1/ingest/{id}` and `/v1/status/{id}`:

  * survive service restarts
  * return correct HTTP semantics:

    * `400` → invalid UUID
    * `404` → unknown ingestion ID
* Status updates are handled via a dedicated `StatusManager`.

✅ **No in-memory ingestion state remains**

---

### 2. **Persistent Vector Storage with pgvector**

* Text is chunked deterministically.
* Each chunk is:

  * embedded
  * persisted as a vector in PostgreSQL using **pgvector**
* Each stored vector includes:

  * `ingestion_id`
  * `chunk_id`
  * `chunk_index`
  * `chunk_strategy`
  * `chunk_text`
  * `source_metadata`
* Schema is defined and versioned via **Alembic migrations**.
* Vectors remain queryable after service restarts.

✅ **MemoryVectorStore is now strictly test/dev-only**

---

### 3. **Vector Store Implementations**

* **`PgVectorStore`**

  * schema validation at startup
  * insert (`add`)
  * similarity search
  * deletion by `ingestion_id`
* **`MemoryVectorStore`**

  * explicitly non-persistent
  * limited to unit tests and local development
  * documented as unsafe for production

---

### 4. **Testing & CI Stability**

####  Test Coverage Achieved

* Unit tests:

  * pipeline behavior
  * chunking
  * embedder contracts
  * memory vector store
* Integration tests (Docker + Postgres):

  * ingestion creation
  * status persistence
  * pgvector schema validation
  * similarity search correctness
  * deletion semantics
* API tests:

  * ingest endpoint
  * status endpoint
  * persistence verification

All of the following now pass cleanly:

```bash
uv run pytest
uv run pytest -m "not docker"
docker compose -f docker-compose.test.yml exec ingestion_service \
  uv run pytest -m docker
```

---

### 5. **Major Issues Identified and Resolved**

These were **non-trivial and important fixes**:

1. **Schema Drift Between Alembic and Tests**

   * Root cause of:

     * `UndefinedColumn: chunk_text`
     * flaky Docker failures
   * Fixed by aligning:

     * Alembic migrations
     * runtime expectations
     * test table creation

2. **psycopg SQL Formatting Trap**

   * `JSONB DEFAULT '{}'` caused:

     ```
     IndexError: tuple index out of range
     ```
   * Root cause: `{}` interpreted as a formatting placeholder
   * Fixed by using escaped literal:

     ```
     DEFAULT '{{}}'
     ```
   * Documented clearly in `conftest_db.py`

3. **Alembic Not Applying Migrations**

   * Diagnosed via:

     * schema inspection
     * test behavior
     * container lifecycle analysis
   * Resolved by:

     * explicit `alembic upgrade head`
     * container reset
     * verification via `\dt ingestion_service.*`

4. **Python 3.12 Datetime Deprecation**

   * Replaced `datetime.utcnow()` with:

     ```python
     datetime.now(UTC)
     ```
   * Eliminated warnings
   * Future-proofed status timestamps

---

##  **System Health Summary**

| Area               | Status               |
| ------------------ | -------------------- |
| API Contract       | ✅ Stable (unchanged) |
| Restart Safety     | ✅ Confirmed          |
| Vector Persistence | ✅ Durable            |
| Docker Tests       | ✅ Stable             |
| Alembic Migrations | ✅ Working            |
| Schema Drift       | ❌ Eliminated         |
| Test Flakiness     | ❌ Eliminated         |

---

##  **What This Means**

**IS2-MS2a is now complete.**

Earlier confidence was premature; the milestone is only now complete after:

* schema alignment
* migration correctness
* test determinism
* runtime/test parity

This is now a **solid, production-grade foundation**.

---

## 🚧 **Known Follow-Ups (Not Part of MS2a)**

These are explicitly **out of scope** for MS2a and will be handled via new issues:

1. **Embedding Integration**

   * Replace mock / dummy embeddings
   * Integrate Ollama (host-based)
   * Add embedding-specific tests

2. **Vector Indexing**

   * IVFFLAT / HNSW indexes
   * performance tuning
   * recall/latency tradeoffs

3. **Failure Semantics**

   * partial ingestion failures
   * retry behavior
   * transactional guarantees

4. **Documentation**

   * architecture
   * schema
   * operational guidance

5. **UI / Gradio Improvements**

   * explicitly deferred to **MS5**

---

##  **Overall Status**

**IS2-MS2a: ✅ DONE **

The system now has:

* durable ingestion tracking
* durable vector storage
* correct lifecycle semantics
* reproducible Docker tests
* no hidden state

We are in an excellent position to move forward with **issues → milestones → next phase execution**.

---

### Next step (recommended):

 **Create and close a final “MS2a Completion” issue**, then open new issues for:

1. Embeddings (Ollama MVP)
2. Vector indexing
3. Failure semantics
4. Documentation
