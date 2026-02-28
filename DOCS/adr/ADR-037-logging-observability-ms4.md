# ADR-037: Logging & Observability for MS4

## Status
Proposed / Accepted

## Context
Background ingestion may fail or take significant time. Observability is required to debug ingestion, monitor progress, and track metrics.

## Decision
- Use structured logging via Python `logging` module.  
- Include:
  - Ingestion ID  
  - Repository path / URL  
  - Status updates (`accepted`, `running`, `completed`, `failed`)  
  - Error messages and stack traces
- Optionally integrate with metrics and tracing (Prometheus / OpenTelemetry).  
- Logs are emitted during:
  - Repo clone / path check  
  - Graph building  
  - Node & relationship persistence  
  - Vector embedding  
  - Summary dispatch

## Alternatives Considered
1. Minimal logging  
   - Pros: Simple  
   - Cons: Hard to debug ingestion failures
2. External monitoring only  
   - Pros: Centralized  
   - Cons: Requires additional infrastructure

## Consequences
- Improved observability  
- Easier debugging of background ingestion jobs  
- Supports structured monitoring for future RAG pipelines
