No code yet, no refactors, no speculation — this is a **contract document**.

---

# MS2 – Core Text Ingestion

**Architecture & Guardrails**

## 1. Purpose of MS2

MS2 implements the **core text ingestion logic** for the RAG-Ingestion-Engine service.

This milestone moves ingestion from *request acceptance* to *fully persisted vectorized content*, while preserving the system’s role as a **standalone, black-box ingestion service**.

MS2 does **not** attempt to build a full RAG system. It focuses only on the ingestion side of that boundary.

---

## 2. Architectural Positioning

* This repository remains **independent** from the larger Agentic-RAG-Platform
* Ingestion is treated as a **black box**
* Integration with downstream systems happens **only via contracts**
* No cross-repo imports
* No shared runtime state

The ingestion service may later expose:

* HTTP APIs (FastAPI)
* MCP interfaces (future)
* Optional memory extensions (future, additive)

None of those change MS2 scope.

---

## 3. High-Level Ingestion Flow (MS2)

```
Input Text
   ↓
Validation
   ↓
Chunking
   ↓
Embedding
   ↓
Vector Store Persistence
```

Key characteristics:

* Deterministic
* Testable headless (no API)
* Provider-agnostic
* Replaceable components via interfaces

---

## 4. Core Layering Rules

### 4.1 Core Logic (`core/`)

* Pure Python
* No FastAPI imports
* No database session ownership
* No UI knowledge
* All dependencies injected

### 4.2 API Layer

* Orchestrates calls into core
* Owns HTTP concerns only
* Never owns business logic

### 4.3 UI Layer (Gradio)

* Thin, disposable
* No ingestion logic
* No DB access
* No long-term guarantees

---

## 5. Explicit Guardrails (Non-Negotiable)

### ❌ Out of Scope for MS2

* Authentication / authorization
* Multi-tenancy
* Streaming ingestion
* SQLAlchemy 2.0 migration
* Typed ORM (`Mapped[]`, `DeclarativeBase`)
* mypy
* CI/CD expansion
* Production hardening
* LLM orchestration

### ❌ Forbidden Patterns

* UI calling DB directly
* Embedding providers hardcoded into pipeline
* Vector store leaking ORM models
* Core logic depending on FastAPI
* “Helpful” refactors to MS1 code

---

## 6. Embeddings & Vector Stores

### Embeddings

* Must be abstracted behind a base interface
* Mock provider required
* External providers optional
* Deterministic behavior required for tests

### Vector Stores

* Exactly one concrete store for MS2
* Chosen via documented decision
* Must support metadata:

  * `ingestion_id`
  * `chunk_id`
* Must be swappable later

---

## 7. State & Persistence Rules

* `ingestion_requests` table remains the source of truth for ingestion status
* MS2 may extend usage, but not redesign schema
* Migrations remain **manual**
* No auto-migrate on startup

---

## 8. Testing Expectations

MS2 must be testable at three levels:

1. **Unit**

   * Chunking
   * Embeddings (mock)
   * Vector store writes
2. **Integration**

   * End-to-end ingestion (no API)
3. **Runtime**

   * Dockerized execution
   * pytest via `uv`

---

## 9. Issue-First Development Contract

* No work without an Issue
* Each Issue maps to a branch
* Acceptance criteria define “done”
* MS2 issues:

  * IS1 → IS8 (canonical)

---

## 10. Definition of Done for MS2

MS2 is complete when:

* Text ingestion produces persisted vectors
* Core pipeline runs without FastAPI
* API only orchestrates
* UI is thin and disposable
* Ingestion remains a black box

---

## Acceptance Criteria (IS1-MS2-01)

* [ ] `DOCS/DESIGN/ms2.md` exists
* [ ] Scope and non-goals explicitly documented
* [ ] Layering rules unambiguous
* [ ] No conflict with MS1 decisions
* [ ] All future MS2 issues reference this document

---

### ✅ Next Step


> **IS2-MS2 – Ingestion Pipeline Skeleton (Core Orchestration)**
