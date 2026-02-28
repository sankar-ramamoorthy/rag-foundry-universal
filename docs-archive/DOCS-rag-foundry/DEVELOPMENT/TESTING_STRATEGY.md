# RAG-Ingestion-Engine: Testing Strategy

This document outlines the **testing strategy** for the `RAG-Ingestion-Engine` service, including unit tests, integration tests, and CI considerations. It also provides guidance on scripts available for convenience.

---

## Table of Contents

1. [Testing Categories](#testing-categories)
   - [Unit / Pure Tests (No DB)](#1-unit--pure-tests-no-db)
   - [Docker / Local Integration Tests](#2-docker--local-integration-tests)
   - [CI / Integration Tests](#3-ci--integration-tests)
2. [Running Tests Manually](#running-tests-manually)
3. [Using Helper Scripts](#using-helper-scripts)
4. [Post-Test Cleanup](#post-test-cleanup)
5. [Notes](#notes)

---

## Testing Categories

### 1️⃣ Unit / Pure Tests (No DB)

* **Purpose:** Test code in isolation without a database.
* **Database:** None (mocks `psycopg` / `PgVectorStore`).
* **Marker:** `not docker`

**Command:**

```bash
uv run pytest -m "not docker"
````

✅ Fast, safe, no environment setup required.

---

### 2️⃣ Docker / Local Integration Tests

* **Purpose:** Test Postgres interactions inside Docker.
* **Database:** Dockerized Postgres service (`postgres`).
* **Marker:** `docker`

**Setup & Commands:**

```bash
# Start test containers
docker compose -f docker-compose.test.yml up -d

# Run DB migrations inside the container
docker compose -f docker-compose.test.yml exec ingestion_service \
    uv run alembic -x db_url=$env:DATABASE_URL upgrade head

# Run integration tests
docker compose -f docker-compose.test.yml exec ingestion_service \
    uv run pytest -m "docker"
```

✅ Tests run against the containerized DB using:
`DATABASE_URL=postgresql://ingestion_user:ingestion_pass@postgres:5432/ingestion_test`

---

### 3️⃣ CI / Integration Tests

* **Purpose:** Run integration tests in CI environments (optional).
* **Database:** CI-provided Postgres or Docker.
* **Marker:** `integration`

**Command inside container or CI runner:**

```bash
uv run pytest -m "integration"
```

---

## Running Tests Manually

You can run individual tests, check tables, or verify migrations directly:

```bash
# Run a single test
docker compose -f docker-compose.test.yml exec ingestion_service \
    uv run pytest tests/api/test_ingest_integration.py::test_ingest_returns_accepted -vv

# Check SQL tables
docker compose -f docker-compose.test.yml exec postgres \
    psql -U ingestion_user -d ingestion_test -c "\dn"

docker compose -f docker-compose.test.yml exec postgres \
    psql -U ingestion_user -d ingestion_test -c "\d ingestion_service.vectors"

docker compose -f docker-compose.test.yml exec postgres \
    psql -U ingestion_user -d ingestion_test -c "SELECT * FROM ingestion_service.vectors;"
```

---

## Using Helper Scripts

For convenience, helper scripts are provided in `scripts/`:

| Script Name            | Purpose                                         |
| ---------------------- | ----------------------------------------------- |
| `unit_tests.sh`        | Run unit tests (`not docker`)                   |
| `integration_tests.sh` | Run full integration tests (`docker`)           |
| `reset_docker.sh`      | Reset Docker containers, volumes, and images    |
| `reset_prod.sh`        | Reset and bring up production Docker containers |
| `run_migrations.sh`    | Run Alembic migrations inside container         |
| `sql_check.sh`         | Sanity-check SQL tables                         |

**Example Usage:**

```bash
# Run all unit tests
./scripts/unit_tests.sh

# Run integration tests
./scripts/integration_tests.sh
```

> ⚠️ Scripts are **convenience shortcuts**. Full commands are documented above for transparency and learning.

---

## Post-Test Cleanup

After tests, always clean up containers and volumes:

```bash
docker compose -f docker-compose.test.yml down -v
```

Optional: remove orphan volumes/images if needed:

```bash
rm -rf ./volumes/ingestion*
docker rmi agentic-rag-ingestion-ingestion_service:latest
```

---

## Notes

* **Unit tests** do not require `DATABASE_URL`.
* **Docker / integration tests** rely on `tests/conftest_db.py` for DB fixtures.
* Use **pytest markers** (`not docker`, `docker`, `integration`) to separate test types and speed up local development.
* Commands are provided for **both manual execution and script automation**.
* Keep this document updated whenever test workflows or scripts change.

---

## References

* [DESIGN_PRINCIPLES.md](../DESIGN/DESIGN_PRINCIPLES.md)
* [INGESTION_SERVICE_GUIDE.md](../USAGE/INGESTION_SERVICE_GUIDE.md)
* [OCR Architecture Notes](../ARCHITECTURE/OCR_ARCHITECTURE.md)
* [ADRs](../ADRS/)

---
