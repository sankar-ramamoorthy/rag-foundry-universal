#DOCS/DESIGN/OCR_ARCHITECTURE.md
# OCR Architecture & Design Decisions

## Context

As part of **image ingestion**, the ingestion service must support extracting
text from images and feeding that text into the ingestion pipeline:

```

image → OCR → text → chunking → embedding → vector store

````

Multiple OCR engines exist (e.g., Tesseract, PaddleOCR, vision-language OCRs,
cloud OCRs), each with different tradeoffs in accuracy, performance, resource
usage, and operational complexity.

This document records the **design options considered**, the **decisions taken**,
and how the OCR architecture is expected to evolve over time.

---

## Goals

The OCR design must:

- Keep the ingestion service **simple and stable**
- Avoid coupling OCR choices to public API contracts
- Support **incremental adoption** of more advanced OCR engines
- Allow future GPU- or agentic-based OCR without refactoring ingestion
- Remain compatible with Docker-based local development and CI

Non-goals (at this stage):

- GPU scheduling
- Layout-aware OCR (bounding boxes, coordinates)
- Confidence-driven pipeline logic
- OCR result post-processing or enrichment
- Agentic OCR orchestration

---

## Design Evolution (Important)

The OCR architecture has evolved over time as real constraints were encountered.

Earlier iterations favored fully in-process OCR adapters for all engines.
However, experience with heavyweight OCR dependencies led to a **tiered model**
that distinguishes between *lightweight default OCR* and *advanced OCR engines*.

This evolution is intentional and documented via ADRs.

---

## OCR Engine Placement

### Tier 1: In-Process OCR (Default)

**Characteristics**

- Runs inside the ingestion service container
- CPU-only
- Minimal system dependencies
- Deterministic and easy to test

**Current Engine**

- **Tesseract OCR** (default)

**Rationale**

- Small operational footprint
- Stable and well-understood
- Suitable for basic document OCR
- Keeps ingestion self-contained

Tesseract is considered part of the **core ingestion runtime**.

---

### Tier 2: External OCR Services (Advanced / Optional)

**Characteristics**

- Run in **dedicated Docker containers**
- May require GPU acceleration
- Heavy ML dependencies
- Independently deployable and scalable

**Examples (non-exhaustive)**

- PaddleOCR
- PaddleOCR-VL
- EasyOCR
- Vision-language OCR pipelines

**Rationale**

- Avoids bloating the ingestion container
- Prevents native dependency conflicts
- Enables GPU isolation and scheduling
- Supports future agentic or multi-stage OCR

External OCR engines are **not required** for core ingestion operation.

---

## Design Options Considered

### Option 1: One Docker Container per OCR Engine (Initially Rejected, Later Adopted for Tier 2)

**Description**

Each advanced OCR engine runs in its own Docker container with a dedicated API.
The ingestion service calls the OCR service over a stable contract.

**Pros**
- Strong isolation between OCR engines
- GPU-specific containers possible
- Independent scaling and deployment
- Cleaner dependency boundaries

**Cons**
- Increased operational complexity
- More services to deploy and test

**Decision**
✅ **Accepted for advanced OCR engines only**
❌ **Not used for default OCR**

---

### Option 2: OCR as an External Third-Party Service Only

**Description**

All OCR is delegated to external APIs (cloud OCR providers).

**Pros**
- Minimal local dependencies
- No OCR runtime management

**Cons**
- External dependency for core ingestion
- Cost and rate limits
- Harder to test deterministically
- Reduced offline / local dev capability

**Decision**
❌ Rejected

---

### Option 3: Fully In-Process OCR Adapters for All Engines

**Description**

All OCR engines are implemented as internal adapters within the ingestion
service and selected via configuration.

**Pros**
- Simple operational model
- Single service to deploy
- Easy local testing

**Cons**
- Heavy OCR dependencies pollute ingestion runtime
- GPU usage becomes difficult to manage
- Native dependency conflicts likely

**Decision**
❌ Rejected for advanced OCR engines
✅ Retained for Tesseract only

---

## Final Architecture Decision

### Core Principle

> **OCR is a replaceable leaf dependency behind a text-only boundary.**

However, OCR engines are now **tiered by operational cost**:

- **Lightweight OCR stays embedded**
- **Heavy OCR is isolated into services**

This preserves simplicity while enabling growth.

---

## OCR Interface Contract (Internal)

All OCR engines—local or remote—must conform to the same *logical* interface:

```python
class OCRExtractor:
    name: str

    def extract_text(self, image_bytes: bytes) -> str:
        """Return extracted text, or an empty string."""
````

### Guarantees

* Always returns a string
* Empty or unreadable images return `""`
* OCR-specific failures are contained
* The ingestion pipeline never crashes due to OCR internals

---

## External OCR Service Contract

Advanced OCR engines expose a **service-level API contract** documented separately:

```
DOCS/DESIGN/OCR_SERVICE_API_CONTRACT.md
```

Key principles:

* Engine-agnostic
* Text-only output
* No ingestion-specific logic
* Transport-independent (HTTP initially)

The ingestion service treats external OCR as a **best-effort dependency**.

---

## OCR Selection & Defaults

### Default Behavior

* Default OCR engine: **Tesseract**
* Runs in-process
* Requires no external services

### Optional Override

OCR engine selection may be overridden via metadata:

```
{
  "ocr_provider": "tesseract"
}
```

Future values may refer to external OCR services.

If a requested OCR provider is unavailable:

* The request fails fast
* No partial ingestion occurs

---

## Docker Strategy

### Current State

* Single ingestion service container
* Tesseract installed as a system dependency
* CPU-only OCR

### Future State

* Advanced OCR engines run in dedicated containers
* GPU usage isolated from ingestion
* Ingestion communicates via stable OCR service API
* OCR interface remains unchanged

---

## Production Upgrade & Change Management

### Adding a New OCR Engine

* Implement OCR service (external)
* Conform to OCR service API contract
* Deploy independently
* No ingestion pipeline changes required

### Switching Default OCR

* Configuration-only change
* Redeploy ingestion service
* Existing data remains valid

### Rollback

* Disable external OCR usage
* Fall back to Tesseract
* No data corruption or reprocessing required

---

## Failure Semantics

| Scenario                  | Behavior                      |
| ------------------------- | ----------------------------- |
| Text detected             | Normal ingestion              |
| Blank / low-quality image | Empty text → request rejected |
| OCR error                 | Controlled failure            |
| OCR service unavailable   | Clear configuration error     |

In all cases:

* Ingestion lifecycle remains consistent
* Status tracking remains correct

---

## Related Architecture Decisions

* **ADR-006**: OCR Boundaries and Progressive Understanding
* **ADR-009**: Tiered OCR Engines and Service Isolation
* **ADR-010 (Proposed)**: Future GPU and Agentic OCR Orchestration

---

## Summary

This architecture:

* Keeps ingestion **stable and predictable**
* Retains Tesseract as a reliable default
* Isolates heavy OCR dependencies
* Enables GPU and agentic OCR in the future
* Avoids premature complexity while preventing architectural dead-ends

**Simple now. Explicit later. Safe to evolve.**
