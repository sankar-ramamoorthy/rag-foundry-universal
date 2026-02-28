
---

# DOCS\ARCHITECTURE\adr-021-llm-service-responsibilities.md

## ADR-021: LLM / Semantic Service Responsibilities

### Status  2026/01/21

Proposed

### Context

The RAG Foundry project uses a dedicated **LLM / semantic service** to handle natural language generation, semantic search, and embeddings. Currently, the service wraps external or local LLMs (e.g., Ollama, OpenAI) and exposes a simple HTTP interface.

We need a clear contract and responsibilities for this service to:

* Ensure consistent API for downstream services (e.g., RAG Orchestrator)
* Keep LLM engines replaceable
* Support future multi-provider or streaming functionality

### Decision

The **LLM / semantic service** will have the following responsibilities:

1. **Text Completion & Query Generation**

   * Expose a `/generate` endpoint that accepts a context and query.
   * Optionally allow provider/model override.
   * Return structured JSON with at least:

     ```json
     {
       "provider": "ollama",
       "model": "Qwen3:1.7b",
       "response": "generated text"
     }
     ```
   * Service does **not** validate correctness of LLM output; it is a *best-effort text generator*.

2. **Provider-Agnostic Layer**

   * Abstracts away specific LLM backends.
   * Supports multiple providers through configuration (default `ollama`).
   * Switching providers does **not** impact RAG Orchestrator contract.

3. **Statelessness**

   * Each request is independent; no session state is maintained.
   * Streaming or async extensions may be added in the future.

4. **Error Handling**

   * Service must return HTTP 500 for internal failures.
   * Unknown provider or misconfiguration raises an explicit error.
   * Does **not retry** or cache requests internally.

5. **Health and Diagnostics**

   * `/health` endpoint returns:

     ```json
     {
       "status": "ok",
       "default_provider": "ollama",
       "ollama_model": "Qwen3:1.7b"
     }
     ```

6. **Future Extensions (Non-Binding)**

   * Async streaming responses
   * Batched query support
   * Confidence scoring / explanation for LLM outputs
   * Multi-model orchestration

### Rationale

* Centralizes LLM usage to a single service — avoids duplicate code across orchestrator or ingestion services.
* Decouples RAG orchestration from LLM provider specifics.
* Supports testing and mocking via a well-defined endpoint.
* Mirrors ADR-020 philosophy for orchestrator:

  * Clear responsibility boundaries
  * Replaceable components
  * Minimal assumptions about internal logic

### Consequences

* Downstream services like RAG Orchestrator can call `/generate` synchronously or asynchronously without caring about provider implementation.
* Any breaking change in LLM service API requires a **new endpoint or version prefix**, preserving backward compatibility.
* Testing strategy can be clearly scoped:

  * Unit tests for `generate_completion` logic
  * Endpoint tests using HTTP client or FastAPI `TestClient`

---

### Summary

The **LLM / semantic service** is a *replaceable, provider-agnostic, stateless microservice* responsible for text generation and semantic queries. It provides a minimal, stable API to allow orchestration and ingestion services to remain engine-independent. Future extensions may include streaming, batching, and confidence scoring.

---

