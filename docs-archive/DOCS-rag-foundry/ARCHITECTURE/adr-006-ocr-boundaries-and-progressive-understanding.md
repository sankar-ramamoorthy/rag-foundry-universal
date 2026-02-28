---

# 📘 ADR-006: OCR Boundaries and Progressive Understanding
This ADR defines OCR boundaries and applies to all ingestion implementations, including future OCR engines

## Status

**Accepted**

---

## Context

The ingestion service supports image ingestion via OCR as part of the
Agentic-RAG platform. As the platform evolves to support:

* system documentation understanding
* UI screenshot ingestion
* help desk and production support
* documentation generation
* reinforcement of good engineering practices

it is critical to clearly define **what OCR is responsible for** — and,
equally importantly, **what it is not responsible for**.

Without explicit boundaries, OCR risks becoming overloaded with concerns
such as interpretation, layout semantics, visual reasoning, or document
understanding, leading to:

* non-deterministic ingestion
* brittle pipelines
* expensive reprocessing
* unclear source authority
* erosion of trust in support outputs

This ADR establishes **non-negotiable architectural boundaries** for OCR
within the ingestion system.

---

## Decision

We adopt the following principles as **locked design decisions** for the
ingestion service.

These decisions are not subject to future debate without a superseding ADR.

---

## 1️⃣ OCR Output Is Raw, Not Authoritative

**Decision**

OCR output is treated as **raw extracted text**, not as authoritative or
canonical document content.

**Implications**

* OCR text represents a *lossy transformation* from pixels to symbols.
* Downstream systems may reinterpret, augment, or override OCR output.
* OCR output is never assumed to be semantically correct or complete.

**Rationale**

OCR exists to reduce entropy (pixels → text), not to establish meaning.
Authoritative understanding occurs later in the pipeline (retrieval,
reasoning, synthesis).

---

## 2️⃣ Screenshots Are First-Class Sources

**Decision**

Screenshots are treated as **first-class source artifacts**, not as generic
images.

**Implications**

* Screenshot-derived text is never silently merged with prose documentation.
* Provenance is always preserved, including:

  * source type (screenshot)
  * ingestion timestamp
  * original artifact identity (filename / hash)
  * environment or system metadata when available
* Screenshots may be more authoritative than written documentation in
  operational contexts.

**Rationale**

In production and support workflows, screenshots often represent the
*ground truth state* of a system at a moment in time.

---

## 3️⃣ OCR Engines Are Explicitly Selected, Never Auto-Switched

**Decision**

OCR engines are selected **explicitly via configuration or request override**.
The ingestion pipeline does not dynamically or heuristically switch OCR
engines.

**Implications**

* No confidence-based fallback
* No image-complexity heuristics
* No silent retries across engines
* OCR behavior is deterministic and reproducible

**Rationale**

Automatic OCR switching introduces non-determinism, complicates debugging,
and undermines trust in support and audit workflows. Explicit selection
preserves predictability and traceability.

---

## 4️⃣ Vision-Language Models Are Query-Time Only

**Decision**

Vision-Language (VL) models are **never used at ingestion time**.

**Implications**

* No visual reasoning during ingestion
* No captioning, explanation, or interpretation of images
* No semantic enrichment derived from VL models during ingestion
* Ingestion remains deterministic and model-agnostic

**Rationale**

VL models are interpretive by nature and evolve rapidly. Using them at
ingestion time would force costly reprocessing and entangle stored data with
specific model behavior. VL models belong at **query-time**, where reasoning
and explanation are appropriate.

---

## 5️⃣ PaddleOCR Is a Fallback Extractor, Not an Intelligence Upgrade

**Decision**

PaddleOCR (CPU) may be added as an **optional OCR backend** but is treated
strictly as an alternative text extractor.

**Implications**

* PaddleOCR does not introduce layout semantics, document structure, or
  intelligence
* No schema changes are required to support PaddleOCR
* PaddleOCR is used explicitly, never implicitly
* PaddleOCR does not change ingestion guarantees

**Rationale**

PaddleOCR improves text extraction quality for certain image types (e.g.,
dense UIs, tables), but does not alter the role of OCR as a raw extraction
step.

---

## Consequences

### Positive

* Clear separation between extraction and understanding
* Deterministic, debuggable ingestion
* Stable schemas and APIs
* Strong provenance and auditability
* Future flexibility without re-ingestion

### Negative

* Some advanced OCR features (layout, confidence, VL reasoning) are deferred
* Additional interpretation logic must live downstream

These tradeoffs are intentional and aligned with long-term platform goals.

---

## Alignment With Platform Principles

This ADR reinforces the platform’s broader architectural values:

* **Explicit over implicit**
* **Determinism over cleverness**
* **Traceability over convenience**
* **Evolution without data invalidation**

---

## Summary

OCR is a **first-mile extraction mechanism**, not a source of truth or
understanding.

The hope is that by locking these boundaries now, the ingestion service remains simple,
stable, and trustworthy — while enabling richer interpretation and reasoning
at the correct layer of the system.

---
