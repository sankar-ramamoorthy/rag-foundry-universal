---

## ✅ **Corrected & final testing model** MS3

### 🧪 CI (GitHub Actions / local pytest without Docker)

* ❌ Docker
* ❌ Postgres
* ❌ Ollama
* ❌ Real embeddings
* ✅ **Pure unit tests only**
* ✅ Mock boundaries where needed
* ✅ Fast, deterministic

---

### 🧪 Integration tests (local / dev only)

✅ Docker available
✅ Postgres + pgvector
✅ **Ollama (real embeddings)**
❌ No mock embedder
❌ No synthetic embeddings
✅ End-to-end ingestion realism

This is the **correct** interpretation of your intent.

> Integration tests are *truth tests*, not speed tests.

---

## Why this is actually the right call

Your system has a **very specific risk profile**:

* pgvector dimensionality must match embedder output
* embedding provider behavior matters (batching, floats, normalization)
* ingestion → embedding → persistence → retrieval must be coherent

Mocking or synthesizing embeddings **hides real failures** like:

* wrong dimension
* wrong dtype
* serialization issues
* provider drift

So yes — **integration tests should use Ollama**.

CI is where mocks belong.
Integration tests are where *reality* belongs.

---

## What this means concretely

### 1️⃣ `docker-compose.test.yml` (integration)

* Must include:

  * Postgres (pgvector)
  * ingestion_service
  * vector_store_service
* Must assume:

  * Ollama running on **host**
* Must **not** include Ollama container

You already noted the key detail 👇

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

That is exactly right.

---

### ✅ Correct mental contract

| Layer             | Embeddings | DB         | Docker |
| ----------------- | ---------- | ---------- | ------ |
| Unit tests        | ❌ mocked   | ❌          | ❌      |
| Integration tests | ✅ Ollama   | ✅ pgvector | ✅      |
| Dev / demo        | ✅ Ollama   | ✅ pgvector | ✅      |

No overlap, no confusion.

---

## Subtle but important implication (you caught this instinctively)

> “integration tests will not run in CI”

That is **not a weakness**.

That is:

* intentional
* explicit
* documented
* professional

Many serious systems do exactly this.

You can later add:

* nightly jobs
* manual workflows
* “run integration tests” Makefile targets

But **not** CI-by-default.

---


---

## One final reassurance


* *code that must always run*
* *code that must reflect reality*


---
Alembic & Integration Testing Notes

Alembic migrations are configured to require DATABASE_URL
No database URL is hardcoded in alembic.ini
Integration tests assume:

Docker
Postgres + pgvector
Ollama running on host (host.docker.internal)
Integration tests are explicitly skipped in CI
Schema ingestion_service is created automatically by Alembic
Alembic version table lives in the same schema

ps note for future we may need to add this in migrations\env.py
#to Guard autogenerate in CI
#If you ever run alembic revision --autogenerate in CI, #add:
if os.environ.get("CI") == "true":
    context.configure(
        compare_type=False,
        compare_server_default=False,
    )


Below is the **exact sequence** for **PowerShell on Windows**.

---

## ✅ One-time prerequisites (verify once)

### 1️⃣ Docker Desktop running

```powershell
docker version
```

### 2️⃣ Ollama running on host

```powershell
ollama list
```

(If this works, `http://localhost:11434` is alive — Docker will reach it via `host.docker.internal`.)

---

## 🧪 MS2-IS4: Exact execution sequence

### 📍 From repo root (`rag-foundry-docgraph`)

---

### **Step 1 — Start integration test stack**

```powershell
docker compose -f docker-compose.test.yml up -d --build
```

What this does:

* starts **Postgres + pgvector**
* builds + starts **ingestion_service**
* waits for DB healthcheck
* does **not** start Ollama (correct)

---

### **Step 2 — Verify containers are healthy**

```powershell
docker ps
```

You should see at least:

* `ingestion-db-test`
* `ingestion_service`

Status should be `healthy` (or running for ingestion_service).

---

### **Step 3 — Run Alembic migrations (inside ingestion_service container)**

This is critical for **MS2-IS4**.

```powershell
docker compose -f docker-compose.test.yml exec ingestion_service `
  alembic upgrade head
```

Expected:

* schema `ingestion_service` exists
* `document_nodes` table exists
* pgvector extension enabled (via migrations)

If this fails → **that’s the bug MS2-IS4 is meant to catch**.

---

### **Step 4 — Run integration tests from host**

Still from repo root:

```powershell
uv run pytest ingestion_service -m "integration"
```

✔ Uses:

* Dockerized Postgres
* Real pgvector
* Real Ollama embeddings
* Your `conftest.py` DB session

❌ Skips unit tests
❌ Skips CI-only tests

---

## 🧼 Optional cleanup (recommended)

When done:

```powershell
docker compose -f docker-compose.test.yml down -v
```

Removes:

* containers
* test volumes
* clean slate next time

---

## 🔎 If something fails — fast diagnostics

### Check DB tables

```powershell
docker compose -f docker-compose.test.yml exec postgres psql `
  -U ingestion_user -d ingestion_test
```

```sql
\dt ingestion_service.*;
```

---

### Check ingestion_service logs

```powershell
docker logs ingestion_service
```

---

## 

| Step              | Runs where | Purpose                 |
| ----------------- | ---------- | ----------------------- |
| docker compose up | Docker     | Reality (DB + pgvector) |
| alembic upgrade   | Docker     | Schema truth            |
| pytest            | Host       | Code correctness        |

---

 expanding  current `testing.md` to include MS3 updates (DocumentRelationship table, migrations, ORM, etc.) while keeping all  prior details. :

---

# DOCS\testing.md

---

## ✅ Corrected & final testing model

### 🧪 CI (GitHub Actions / local pytest without Docker)

* ❌ Docker
* ❌ Postgres
* ❌ Ollama
* ❌ Real embeddings
* ✅ **Pure unit tests only**
* ✅ Mock boundaries where needed
* ✅ Fast, deterministic

---

### 🧪 Integration tests (local / dev only)

✅ Docker available
✅ Postgres + pgvector
✅ Ollama (real embeddings)
❌ No mock embedder
❌ No synthetic embeddings
✅ End-to-end ingestion realism

This is the **correct** interpretation of your intent.

> Integration tests are *truth tests*, not speed tests.

---

## Why this is the right call

Your system has a **specific risk profile**:

* pgvector dimensionality must match embedder output
* Embedding provider behavior matters (batching, floats, normalization)
* Ingestion → embedding → persistence → retrieval must be coherent

Mocking or synthesizing embeddings **hides real failures** like:

* wrong dimension
* wrong dtype
* serialization issues
* provider drift

Hence, **integration tests should use Ollama**.

CI is where mocks belong. Integration tests are where *reality* belongs.

---

## What this means concretely

### 1️⃣ `docker-compose.test.yml` (integration)

* Must include:

  * Postgres (pgvector)
  * ingestion_service
  * vector_store_service

* Must assume:

  * Ollama running on **host**

* Must **not** include Ollama container

You already noted the key detail 👇

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

### ✅ Mental contract

| Layer             | Embeddings | DB         | Docker |
| ----------------- | ---------- | ---------- | ------ |
| Unit tests        | ❌ mocked   | ❌          | ❌      |
| Integration tests | ✅ Ollama   | ✅ pgvector | ✅      |
| Dev / demo        | ✅ Ollama   | ✅ pgvector | ✅      |

No overlap, no confusion.

---

## Subtle but important implication

> “Integration tests will not run in CI”

That is **not a weakness**, it is:

* intentional
* explicit
* documented
* professional

Nightly jobs or manual workflows can run integration tests later, but **not CI-by-default**.

---

## Alembic & Integration Testing Notes (MS2 → MS3)

* Alembic migrations require `DATABASE_URL`.

* No DB URL is hardcoded in `alembic.ini`.

* Integration tests assume:

  * Docker
  * Postgres + pgvector
  * Ollama running on host (`host.docker.internal`)

* Schema `ingestion_service` is created automatically by Alembic.

* Alembic version table lives in the same schema.

* MS3 added `document_relationships` table with FKs to `document_nodes`.

> Note for future: if `alembic revision --autogenerate` runs in CI, add this to `env.py`:

```python
if os.environ.get("CI") == "true":
    context.configure(
        compare_type=False,
        compare_server_default=False,
    )
```

---

## PowerShell: Exact execution sequence

### ✅ One-time prerequisites

1. Docker Desktop running:

```powershell
docker version
```

2. Ollama running on host:

```powershell
ollama list
```

> If this works, `http://localhost:11434` is alive — Docker will reach it via `host.docker.internal`.

---

### 🧪 Step 1 — Start integration test stack

```powershell
docker compose -f docker-compose.test.yml up -d --build
```

* starts **Postgres + pgvector**
* builds + starts **ingestion_service**
* waits for DB healthcheck
* does **not** start Ollama (correct)

---

### 🧪 Step 2 — Verify containers

```powershell
docker ps
```

Should show at least:

* `ingestion-db-test`
* `ingestion_service`

Status: `healthy` (or `running` for ingestion_service).

---

### 🧪 Step 3 — Run Alembic migrations

From repo root:

```powershell
docker compose -f docker-compose.test.yml exec ingestion_service `
  alembic -x db_url=$env:DATABASE_URL upgrade head
```

Expected:

* schema `ingestion_service` exists
* tables: `document_nodes`, `vector_chunks`, `document_relationships`
* pgvector extension enabled

If this fails → **integration test setup bug**.

---

### 🧪 Step 4 — Run integration tests

From repo root:

```powershell
uv run pytest ingestion_service -m "integration"
```

✔ Uses:

* Dockerized Postgres
* Real pgvector
* Real Ollama embeddings
* Your `conftest.py` DB session

❌ Skips unit tests
❌ Skips CI-only tests

---

### 🧼 Optional cleanup

```powershell
docker compose -f docker-compose.test.yml down -v
```

Removes:

* containers
* test volumes
* clean slate next time

---

### 🔎 Fast diagnostics

**Check DB tables**:

```powershell
docker compose -f docker-compose.test.yml exec postgres psql `
  -U ingestion_user -d ingestion_test
```

```sql
\dt ingestion_service.*;
```

**Check ingestion_service logs**:

```powershell
docker logs ingestion_service
```

---

### 🧩 Summary Table

| Step              | Runs where | Purpose                 |
| ----------------- | ---------- | ----------------------- |
| docker compose up | Docker     | Reality (DB + pgvector) |
| alembic upgrade   | Docker     | Schema truth            |
| pytest            | Host       | Code correctness        |

---

This fully documents **MS2 → MS3 integration** workflow, including DocumentRelationships.

---

