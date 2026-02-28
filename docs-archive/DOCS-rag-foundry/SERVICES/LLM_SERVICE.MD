---

# LLM Service  2026/01/21

**Category:** Core Microservice
**Role:** Language Model Invocation Layer
**Status:** Stable (Post-MVP foundation)

---

## Overview

The **LLM Service** is a dedicated microservice responsible for **invoking large language models** and returning generated responses.

It provides a **thin, provider-agnostic HTTP interface** for text generation and is intentionally **stateless**.
All retrieval, context construction, orchestration, and decision-making logic lives outside this service.

This service exists to:

* Decouple LLM provider details from upstream services
* Allow controlled evolution of model providers and invocation logic
* Provide a stable, testable boundary for text generation

---

## Responsibilities

### What the LLM Service **does**

* Accepts:

  * A **prompt context** (pre-assembled text)
  * A **user query**
* Builds a final prompt
* Invokes a configured LLM provider
* Returns the generated response
* Exposes health and configuration visibility

### What the LLM Service **does NOT do**

* ❌ Retrieval or vector search
* ❌ Chunking or embedding
* ❌ Prompt orchestration or reasoning chains
* ❌ Conversation state or memory
* ❌ Tool calling or agent logic
* ❌ Persistence of prompts or responses

All of the above are **explicitly owned by upstream services** (e.g. RAG Orchestrator).

---

## Service API

### `POST /generate`

Generate a completion from the configured LLM provider.

#### Request Body

```json
{
  "context": "string (optional, default: empty)",
  "query": "string (required)"
}
```

* `context`: Pre-assembled supporting text (e.g. retrieved chunks)
* `query`: The user’s question or instruction

#### Query Parameters

| Name     | Type   | Required | Description                        |
| -------- | ------ | -------- | ---------------------------------- |
| provider | string | No       | Overrides the default LLM provider |
| model    | string | No       | Overrides the default model        |

#### Response

```json
{
  "provider": "ollama",
  "model": "Qwen3:1.7b",
  "response": "Generated text output"
}
```

#### Error Behavior

* Provider errors return HTTP `500`
* Unsupported providers raise a validation error
* Upstream HTTP failures propagate as server errors

---

### `GET /health`

Lightweight health and configuration endpoint.

#### Response

```json
{
  "status": "ok",
  "default_provider": "ollama",
  "ollama_model": "Qwen3:1.7b"
}
```

This endpoint is used for:

* Docker health checks
* Service dependency validation
* Debugging configuration issues

---

## Prompt Construction

The service constructs a simple, deterministic prompt:

```
Context:
{context}

Question:
{query}
```

**Important:**
Prompt engineering is intentionally minimal.
Any advanced prompt composition must occur upstream.

---

## Configuration

Configuration is provided exclusively via environment variables.

| Variable          | Description          | Default                             |
| ----------------- | -------------------- | ----------------------------------- |
| `LLM_PROVIDER`    | Default LLM provider | `ollama`                            |
| `OLLAMA_BASE_URL` | Ollama API base URL  | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL`    | Default Ollama model | `Qwen3:1.7b`                        |

---

## Supported Providers

### Ollama (current)

* Uses `/api/generate`
* Non-streaming responses
* One-shot prompt invocation

### Unsupported Providers

Any provider other than `ollama` currently results in an explicit error.

This is intentional.

---

## Architecture Guarantees

The LLM Service guarantees:

* Stateless execution
* No cross-request memory
* Deterministic input → output behavior (subject to model nondeterminism)
* No dependency on vector stores or databases
* Safe horizontal scaling

---

## Extension Guidelines

When extending this service:

### ✅ Allowed

* Adding new providers (e.g. OpenAI, Azure)
* Adding streaming endpoints
* Adding structured response formats
* Improving error classification
* Adding request/response validation

### ❌ Not Allowed

* Retrieval logic
* Embedding logic
* Context construction heuristics
* Conversation state
* Business orchestration

If an extension requires any of the above, it belongs in **RAG Orchestrator**, not here.

---

## Relationship to Other Services

| Service           | Relationship                 |
| ----------------- | ---------------------------- |
| RAG Orchestrator  | Primary caller               |
| Vector Store      | No direct interaction        |
| Ingestion Service | No direct interaction        |
| Shared Libraries  | Configuration and types only |

---

## Testing Expectations

This service should be tested with:

* Provider mocks (HTTP-level)
* Deterministic prompt construction tests
* Health endpoint validation

It does **not** require:

* Integration tests with vector stores
* Embedding tests
* End-to-end RAG tests

---

## Design Rationale

This service exists to enforce a **clean separation** between:

* *Language generation*
* *Knowledge retrieval*
* *System orchestration*

This separation allows each concern to evolve independently while keeping system behavior predictable and debuggable.

---

### ✅ Status

This document reflects the **current, authoritative behavior** of the LLM Service as of 01/21/2026

---

