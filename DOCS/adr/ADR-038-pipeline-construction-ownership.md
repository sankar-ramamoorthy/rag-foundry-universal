
# 📘 ADR-038

## **ADR-038: Centralized IngestionPipeline Construction via Core Factory**

### Status

Accepted

### Date

2026-02-15

### Decision Owner

Ingestion Service Architecture

---

## 1. Context

The ingestion service supports multiple ingestion entrypoints:

* File ingestion (`/v1/ingest/file`)
* Repository ingestion (`/v1/codebase/ingest-repo`)

Both ingestion flows require instantiating `IngestionPipeline`, which depends on:

* `validator`
* `embedder`
* `vector_store`

Initially, pipeline construction logic existed inside the API module `ingest.py` as `_build_pipeline()`.
To unblock repository ingestion, the same construction logic was duplicated inside `codebase_ingest.py`.

This resulted in infrastructure construction occurring inside multiple API modules.

---

## 2. Problem

The system exhibited the following architectural issues:

### 2.1 Layer Violation

The API layer was constructing infrastructure dependencies such as:

* Embedding provider configuration
* Vector store integration
* Infrastructure wiring

This violates the intended layered architecture:

```
API → Core → Infrastructure
```

Instead, the system behaved as:

```
API → Infrastructure
```

---

### 2.2 Duplication

Pipeline construction logic was duplicated across endpoints, creating risk of:

* Configuration drift
* Inconsistent provider selection
* Divergent embedding behavior
* Maintenance overhead

---

### 2.3 Dependency Injection Integrity

`IngestionPipeline` requires explicit dependency injection.

Allowing endpoints to manually instantiate it increases the risk that:

* Required dependencies are omitted
* Incorrect defaults are assumed
* Test configuration diverges from production configuration

---

## 3. Decision

Pipeline construction is moved to the Core layer.

A new module is introduced:

```
src/core/pipeline_factory.py
```

With a public factory function:

```python
def build_pipeline(provider: str) -> IngestionPipeline
```

All ingestion entrypoints must use this factory.

The API layer must not construct infrastructure components directly.

---

## 4. Architectural Principles Enforced

### 4.1 Layered Architecture

Infrastructure wiring belongs in Core, not API.

### 4.2 Single Responsibility Principle

* API handles request orchestration
* Core handles application logic and wiring
* Infrastructure handles integrations

### 4.3 Single Source of Truth

Embedding configuration must exist in one location.

### 4.4 Explicit Dependency Injection

`IngestionPipeline` continues to require explicit dependencies.
Factory centralizes dependency assembly.

---

## 5. Consequences

### Positive

* Removes duplication
* Prevents configuration drift
* Improves maintainability
* Improves testability
* Enables future ingestion types

### Negative

* Introduces one additional module
* Requires minor refactor

---

## 6. Migration Plan

1. Create `pipeline_factory.py`
2. Move pipeline construction logic into `build_pipeline`
3. Update:

   * `ingest.py`
   * `codebase_ingest.py`
4. Remove duplicated helper functions
5. Verify integration tests

---

## 7. Future Considerations

This decision enables:

* Introduction of an `IngestionOrchestrator`
* Background job abstraction
* Event-driven ingestion
* Clear separation between orchestration and infrastructure wiring

---

# Summary

ADR-038 stabilizes pipeline construction architecture.
