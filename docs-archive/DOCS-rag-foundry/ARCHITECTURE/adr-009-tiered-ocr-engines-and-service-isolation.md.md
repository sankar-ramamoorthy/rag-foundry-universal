# ADR-009: Tiered OCR Engines and Service Isolation

**Status:** Accepted
**Date:** 2026-01-10
**Deciders:** Project Maintainer  / Sankar
**Related ADRs:**
- ADR-006: OCR Boundaries and Progressive Understanding

---

## Context

The ingestion system supports image ingestion with OCR as a preprocessing step.
OCR output is explicitly treated as **raw, non-authoritative extracted text**
(see ADR-006).

Multiple OCR engines are available with very different characteristics:

- **Tesseract OCR**
  - Lightweight
  - CPU-only
  - Stable system dependency
  - Already integrated and working reliably
- **Modern ML-based OCR engines** (e.g., PaddleOCR, PaddleOCR-VL, EasyOCR)
  - Heavy native and ML dependencies
  - Optional GPU acceleration
  - Long startup times and import-time side effects
  - Significantly more complex runtime requirements

Initial attempts to integrate advanced OCR engines directly into the ingestion
process revealed issues with:
- Local developer environments
- Unit test execution
- CI stability
- Dependency isolation

At the same time, removing Tesseract would reduce the system’s usability and
increase operational complexity unnecessarily.

---

## Decision

The system adopts a **tiered OCR architecture**:

### 1. Default OCR (In-Process)

- **Tesseract remains the default OCR engine**
- Runs **in-process** inside the ingestion service
- Installed as a system dependency in the ingestion Docker image
- Used automatically unless explicitly overridden
- Provides a reliable, low-cost baseline OCR capability

### 2. Advanced OCR Engines (Isolated Services)

- Advanced OCR engines (e.g., PaddleOCR, PaddleOCR-VL, EasyOCR) **must not**
  be imported or initialized inside the ingestion service
- These engines run in **one or more dedicated OCR service containers**
- The ingestion service interacts with them via explicit service boundaries
  (e.g., HTTP or RPC)
- OCR engine selection is explicit and never auto-switched

### 3. Future Flexibility

- The architecture **reserves the right** to move Tesseract into a separate
  OCR service in the future
- Such a change would be handled via a new ADR if and when justified

---

## Rationale

### Why keep Tesseract in-process?
- Already proven stable in local, Docker, and CI environments
- Minimal dependency footprint
- Fast startup and predictable behavior
- Ideal default for text-heavy documents and screenshots

### Why isolate advanced OCR engines?
- Avoids heavy ML dependencies in the ingestion service
- Prevents import-time failures during testing
- Enables GPU usage without impacting ingestion reliability
- Allows independent scaling, versioning, and experimentation
- Aligns with future agentic and MPC-style orchestration

---

## Implications

### Ingestion Service
- Always has a working OCR path (Tesseract)
- Does not require ML frameworks or GPU drivers
- Uses explicit configuration to invoke external OCR services

### OCR Services
- Own their dependency stacks and hardware requirements
- May be CPU or GPU based
- Can evolve independently of ingestion
- May support multiple OCR engines behind a single service

### Testing
- Unit tests rely on in-process Tesseract or mocked OCR responses
- Advanced OCR engines are tested independently
- CI remains fast and CPU-only by default

### Deployment
- Default deployment requires no additional OCR services
- Advanced OCR is opt-in via Docker Compose or orchestration
- Failures in advanced OCR services do not destabilize ingestion

---

## Consequences

### Positive
- Clear, pragmatic separation of concerns
- Stable defaults with advanced extensibility
- Improved testability and CI reliability
- Smooth path toward agentic and multi-step pipelines

### Trade-offs
- Multiple OCR execution paths to reason about
- Slightly more configuration surface area

These trade-offs are accepted to balance simplicity today with scalability tomorrow.

---

## Notes

This ADR does not define the OCR service protocol.
Service contracts and request/response schemas will be documented separately
once advanced OCR services stabilize.
