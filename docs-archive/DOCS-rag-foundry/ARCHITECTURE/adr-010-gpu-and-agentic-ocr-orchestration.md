# 1️⃣ ADR-010 (Proposed): Future GPU and Agentic OCR Orchestration

#DOCS/ARCHITECTURE/adr-010-gpu-and-agentic-ocr-orchestration.md

# ADR-010: Future GPU and Agentic OCR Orchestration

**Status:** Proposed
**Date:** 2026-01-XX
**Deciders:** Project Maintainers
**Related ADRs:** ADR-006, ADR-009
**Supersedes:** None

---

## Context

The ingestion system currently supports OCR via:

- **In-process Tesseract OCR** (default, CPU-only)
- **Planned external OCR services** for heavyweight engines (ADR-009)

As ingestion matures, future OCR needs may include:

- GPU-accelerated OCR engines
- Vision-language OCR pipelines
- Multi-stage or agent-driven OCR workflows
- Cost-aware or latency-aware OCR routing

These capabilities introduce orchestration, scheduling, and policy concerns that
should **not** leak into the ingestion service.

---

## Problem Statement

Advanced OCR workloads introduce challenges that the ingestion service is not
designed to manage:

- GPU resource contention
- Engine-specific hardware requirements
- Multi-step OCR pipelines
- Retry, fallback, and ensemble strategies
- Cost vs accuracy trade-offs

Embedding this logic inside ingestion would increase coupling and risk.

---

## Decision

**OCR orchestration will be delegated to external OCR services.**

The ingestion service will:

- Treat OCR as a **black-box text extraction dependency**
- Remain agnostic to GPU usage, orchestration, or agentic logic
- Interact only through a stable OCR service API contract

Advanced OCR services may internally implement:

- GPU scheduling
- Agentic decision-making
- Multi-model ensembles
- Progressive refinement pipelines

---

## Architecture Direction (Future)

```

Ingestion Service
|
|  (OCR request: image bytes)
v
OCR Gateway / OCR Service
|
|-- GPU OCR Engine
|-- Vision-Language Model
|-- Agentic Router
|
v
Extracted Text

```

The ingestion service **never**:

- Selects GPU vs CPU
- Chooses OCR models
- Coordinates OCR stages
- Retries OCR intelligently

---

## Rationale

This separation:

- Preserves ingestion simplicity
- Enables independent scaling and evolution of OCR
- Supports heterogeneous hardware (CPU/GPU/TPU)
- Aligns with agentic system boundaries
- Avoids premature orchestration logic

---

## Consequences

### Positive

- Clean responsibility boundaries
- Future-ready for ML-heavy OCR
- Easier experimentation with OCR strategies
- Reduced blast radius for OCR failures

### Negative

- Additional services to operate
- Slight latency increase for remote OCR
- Requires explicit API contracts

---

## Non-Goals

This ADR does **not** define:

- A concrete GPU scheduler
- A specific agent framework
- OCR model selection policies
- Billing or cost optimization

Those decisions are deferred to OCR service implementations.

---

## Review Trigger

Revisit this ADR when:

- GPU OCR is required in production
- OCR accuracy becomes a bottleneck
- Agentic OCR is introduced
- OCR costs become material

---

## Summary

> **The ingestion service remains simple.
> OCR orchestration becomes an external, evolvable concern.**

This ADR future-proofs OCR without over-engineering the present system.
