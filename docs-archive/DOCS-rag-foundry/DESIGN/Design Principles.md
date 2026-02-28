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
