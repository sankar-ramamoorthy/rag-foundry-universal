# DOCS/SERVICES/SHARED_SERVICES.md  Dated 2026/01/21

---

## SHARED Services

**Category:** Shared Libraries (Internal)
**Scope:** Cross-service, non-owning code
**Status:** Stable foundation

---

## Overview

The `shared/` package contains **pure, stateless, dependency-light libraries** used across multiple microservices in the RAG platform.

It is **not a service**, does **not own workflows**, and must never become a “god module”.

Its purpose is to:

* Prevent duplication of foundational logic
* Enforce consistent data contracts across services
* Provide deterministic, testable primitives

---

## What Belongs in `shared/`

Code in `shared/` must meet **all** of the following criteria:

1. **Service-agnostic**
2. **Stateless**
3. **Side-effect free** (except explicit external calls like embedding)
4. **Callable from multiple services**
5. **Has no knowledge of orchestration or business flow**

If a module violates any of these rules, it does **not** belong in `shared/`.

---

## Current Module Overview

### `shared/chunks.py`

Defines the fundamental `Chunk` data structure.

**Responsibilities:**

* Represents a unit of content
* Carries raw content and metadata
* Acts as the atomic unit for chunking and embedding

**Non-responsibilities:**

* Persistence
* Retrieval
* Interpretation

---

### `shared/chunkers/`

Provides chunking strategies for content preprocessing.

#### Key Concepts

* `BaseChunker`: Abstract interface
* `TextChunker`: Concrete implementation
* `ChunkerFactory`: Strategy selection logic

#### Supported Strategies

* Fixed character windows
* Sentence-based chunking
* Paragraph-based chunking

#### Important Constraint

Chunkers:

* Do **not** know where chunks are stored
* Do **not** perform embedding
* Do **not** depend on ingestion workflows

---

### `shared/embedders/`

Defines the embedding abstraction layer.

#### Components

* `BaseEmbedder`: Interface
* `OllamaEmbedder`: Real embedding provider
* `MockEmbedder`: Deterministic test embedder
* `factory.py`: Provider selection
* `query.py`: Thin helper for query embedding

#### Design Guarantees

* Embedders operate only on `Chunk` objects
* No persistence
* No retrieval logic
* Mock embedder guarantees deterministic outputs for tests

---

### `shared/models/`

Contains shared data models that represent **cross-service contracts**.

#### `VectorMetadata`

Defines the canonical metadata schema attached to vector records, including:

* Ingestion identity
* Chunk identity
* Chunk strategy
* Source metadata
* Provider identity

This model is critical for:

* Traceability
* Debugging
* RAG source attribution

---

## What Does NOT Belong in `shared/`

The following are explicitly forbidden in `shared/`:

* ❌ FastAPI routes
* ❌ Database access
* ❌ Environment-based configuration
* ❌ Orchestration logic
* ❌ Service-to-service HTTP calls
* ❌ Business rules
* ❌ Stateful caches

If a module requires **settings**, it belongs in a service.

---

## Dependency Rules

### Allowed Dependencies

* Standard library
* Lightweight third-party libraries (e.g. `requests`)
* Data models
* Type hints

### Forbidden Dependencies

* FastAPI
* SQLAlchemy / database drivers
* HTTP clients for inter-service communication
* Service-specific configuration loaders

---

## Testing Expectations

Modules in `shared/` must be:

* Unit-testable in isolation
* Deterministic where possible
* Usable with mock implementations

The presence of `MockEmbedder` is **intentional** and sets the pattern for future shared abstractions.

---

## Evolution Guidelines

### When to add to `shared/`

Add code to `shared/` only if:

* Two or more services need it
* It expresses a stable abstraction
* It can be tested independently

### When to extract from `shared/`

If a module:

* Gains configuration
* Requires orchestration context
* Starts making architectural decisions

…it must be moved into a service.

---

## Architectural Role

`shared/` is the **bedrock layer** of the platform.

It exists to:

* Enforce consistency
* Enable testability
* Reduce accidental coupling

It must remain **boring, predictable, and conservative**.

---

### ✅ Status

This document reflects the **current and intended role** of the `shared/` package. 2026/01/21

---

