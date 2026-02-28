---

# DOCS/ARCHITECTURE/DESIGN_PRINCIPLES.md


# Design Principles

**Status:** Binding (unless superseded by ADR)
**Scope:** RAG-Ingestion-Engine
**Audience:** Contributors, reviewers, downstream integrators

---

## Purpose

This document captures the **core design principles** that guide all
implementation decisions in RAG-Ingestion-Engine.

These principles exist to:

- Preserve long-term system clarity
- Prevent accidental scope creep
- Reduce rework caused by premature intelligence
- Ensure ingestion remains stable as downstream systems evolve

If a proposed change violates one of these principles, it **must** be
justified via a new ADR.

---

## 1. Ingestion Is a Black Box

The ingestion service is treated as a **black-box producer** of artifacts.

- Downstream systems interact only via explicit contracts (API, schema, MCP)
- No downstream service may depend on ingestion internals
- Internal refactors must not affect external behavior

**Rationale:**
Black-box boundaries enable independent iteration and replacement without
platform-wide refactors.

---

## 2. Extraction ≠ Understanding

Ingestion **extracts signals**; it does not interpret them.

- OCR extracts text, not meaning
- Chunking structures content, not semantics
- Embeddings encode similarity, not truth

All understanding, reasoning, and interpretation occurs **downstream at query time**.

**Rationale:**
Understanding is model-dependent and evolves rapidly. Extraction must remain
stable across time.

---

## 3. Determinism Over Cleverness

Ingestion favors:

- Explicit configuration
- Reproducible behavior
- Predictable outcomes

Over:

- Heuristics
- Auto-detection
- Dynamic model or engine switching

**Rationale:**
In operational and support contexts, debuggability and trust matter more than
marginal accuracy gains.

---

## 4. Provenance Is Non-Negotiable

Every artifact produced by ingestion must be traceable to its source.

This includes:

- Original content (file, text, screenshot)
- Source type
- Ingestion timestamp
- Ingestion ID
- Chunk ID

Artifacts are never silently merged or rewritten.

**Rationale:**
Support, audit, and production workflows depend on knowing *where* information
came from.

---

## 5. Screenshots Are First-Class Inputs

Screenshots are not “just images.”

- They often represent ground-truth system state
- They may be more authoritative than documentation
- Their provenance must be preserved

OCR output derived from screenshots is treated as **raw extracted text**, never
as canonical documentation.

---

## 6. Explicit Over Implicit Configuration

All major ingestion behavior must be explicitly configured:

- OCR engine selection
- Embedding provider
- Vector store behavior

No silent fallbacks.
No auto-switching.
No hidden defaults.

**Rationale:**
Implicit behavior erodes trust and complicates debugging.

---

## 7. Ingestion-Time Intelligence Is Forbidden

The ingestion pipeline must not:

- Perform vision-language reasoning
- Infer intent
- Generate captions or summaries
- Apply document semantics
- Encode model-specific interpretations

Vision-language models and reasoning engines are **query-time only**.

---

## 8. Stable Data Outlives Models

Stored ingestion artifacts must remain valid even if:

- Models change
- Chunking strategies evolve
- Embedding dimensions change
- OCR engines are replaced

Re-ingestion should be optional, never mandatory.

---

## 9. Tooling Must Support the Principles

Tooling choices (Python version, type checker, DB access style, OCR libraries)
must support:

- Determinism
- Static analyzability
- Low cognitive overhead
- Predictable runtime behavior

Convenience tooling that undermines these goals is rejected.

---

## Summary

RAG-Ingestion-Engine is intentionally **boring**.

Its job is to faithfully capture raw signals and preserve them over time —
not to be clever, insightful, or adaptive.

Those capabilities belong elsewhere.

When in doubt:

> Prefer clarity over capability.
> Prefer stability over sophistication.
> Prefer extraction over interpretation.
```

---

# 2️⃣ `DOCS/USAGE/INGESTION_SERVICE_GUIDE.md`

**Full file — drop in as-is**

````md
# Ingestion Service Guide

**Service:** RAG-Ingestion-Engine
**Audience:** Developers, integrators, operators

---

## Overview

This document explains **how to use** the RAG-Ingestion-Engine service in
local development, testing, and Docker-based environments.

It focuses on **observable behavior** and **supported workflows**, not internal
implementation details.

---

## Running the Service (Docker)

### Start the production stack

From the repository root:

```bash
docker compose build --no-cache
docker compose up
````

Services exposed:

* **FastAPI**: [http://localhost:8001](http://localhost:8001)
* **Swagger UI**: [http://localhost:8001/docs](http://localhost:8001/docs)
* **Gradio UI (optional)**: [http://localhost:7860](http://localhost:7860)

---

## API Usage

### Submit ingestion request

**POST** `/v1/ingest`

```json
{
  "source_type": "file",
  "metadata": {
    "project": "example",
    "user": "alice"
  }
}
```

**Response**

```json
{
  "ingestion_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted"
}
```

Ingestion is asynchronous. The API guarantees acceptance, not completion.

---

### Check ingestion status

**GET** `/v1/ingest/{ingestion_id}`

Returns the current lifecycle state of the ingestion request.

---

## OCR Usage Notes

* OCR is applied only to image-based inputs
* OCR output is raw extracted text
* No layout, bounding boxes, or semantics are produced
* OCR engine selection is explicit (configuration or request override)

Refer to:

* `DOCS/DESIGN/OCR_ARCHITECTURE.md`
* `DOCS/ARCHITECTURE/adr-006-ocr-boundaries-and-progressive-understanding.md`

---

## Embeddings & Vector Storage

* Embeddings are optional and provider-agnostic
* Vector persistence uses PostgreSQL + pgvector
* Vector queries are SQL-based (no ORM abstraction)

Stored vectors include:

* chunk text
* chunk metadata
* ingestion ID
* provider name

---

## Development & Testing

### Unit Tests (No Docker, No DB)

Purpose: fast, isolated testing.

```bash
uv run pytest -m "not docker"
```

No database or Docker services required.

---

### Docker Integration Tests

Purpose: validate Postgres and vector persistence.

```bash
docker compose -f docker-compose.test.yml build --no-cache
docker compose -f docker-compose.test.yml up -d

docker compose -f docker-compose.test.yml exec ingestion_service \
  uv run alembic -x db_url=$DATABASE_URL upgrade head

docker compose -f docker-compose.test.yml exec ingestion_service \
  uv run pytest -m "docker"
```

---

### Useful Verification Commands

Inspect schemas:

```bash
docker compose -f docker-compose.test.yml exec postgres \
  psql -U ingestion_user -d ingestion_test -c "\dn"
```

Inspect vectors:

```bash
docker compose -f docker-compose.test.yml exec postgres \
  psql -U ingestion_user -d ingestion_test -c "\d ingestion_service.vectors"
```

---

## Code Quality

Before committing:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run pyright
pre-commit run --all-files
```

All checks must pass cleanly.

---

## Operational Notes

* Ingestion is deterministic by design
* No ingestion-time reasoning occurs
* Stored artifacts remain valid across model upgrades
* Re-ingestion is optional, not mandatory

---

## Related Documents

* Design principles: `DOCS/ARCHITECTURE/DESIGN_PRINCIPLES.md`
* OCR design: `DOCS/DESIGN/OCR_ARCHITECTURE.md`
* ADRs: `DOCS/ARCHITECTURE/`
