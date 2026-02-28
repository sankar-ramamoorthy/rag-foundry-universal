#DOCS/ARCHITECTURE/adr-008-python-version-lock.md
---

# 📘 ADR-008: Python Version Lock

## Status

**Accepted**

## Context

The RAG-Ingestion-Engine service depends on a stack with multiple
binary and native dependencies, including:

* PostgreSQL drivers (`psycopg`, `psycopg2-binary`)
* `pgvector`
* OCR and image-processing libraries
* Static analysis and tooling (`uv`, `pyright`, `pre-commit`)
* Docker-based integration testing

Allowing unconstrained Python versions introduces risk in:

* Dependency resolution
* Availability of binary wheels
* Tooling behavior
* Docker reproducibility

During development, dependency resolution failures were observed when
Python **3.13** was implicitly permitted, despite all execution environments
using Python **3.12**.

---

## Decision

The project **locks Python support to a bounded range**, with a single
canonical runtime.

Specifically:

* `pyproject.toml` declares:

  ```toml
  requires-python = ">=3.12,<3.13"
  ```

* Python **3.12** is the **only supported runtime**

* `uv python pin 3.12` is used to ensure deterministic local and CI behavior

* All Docker images use Python **3.12**

* Python 3.13 is **explicitly excluded** until formally reviewed

---

## Rationale

1. **Binary Dependency Stability**

   OCR and image-processing libraries frequently lag behind new Python
   releases. Locking prevents missing or incompatible wheels.

2. **Deterministic Dependency Resolution**

   Fixed Python versions avoid resolver ambiguity and cross-index conflicts,
   especially when using non-PyPI package indexes.

3. **Operational Consistency**

   Development, Docker, CI, and test environments run the same Python
   version, eliminating environment-specific failures.

4. **Reduced Cognitive Load**

   Engineers can reason about failures without questioning interpreter drift.

---

## Consequences

### Positive

* Predictable builds and installs
* Fewer CI and Docker-only failures
* Faster onboarding
* Clear support guarantees

### Negative (Accepted)

* Python 3.13 features are unavailable
* Python upgrades require explicit review

This tradeoff is intentional.

---

## Upgrade Policy

Python version upgrades require:

1. A dedicated ADR
2. Verification of all binary dependencies
3. Docker image updates
4. Successful dependency resolution via `uv`
5. Passing Docker and non-Docker test suites

No implicit Python upgrades are permitted.

---

## Summary

Python version drift is a hidden source of instability.

By locking Python to **3.12**, the ingestion service remains
**predictable, reproducible, and operationally safe**, consistent with the
platform’s broader principles of determinism and traceability.

---
