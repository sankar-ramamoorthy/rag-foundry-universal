---
title: "Frontend API assessment for the Foundry first release"
date: 2026-11-23
type: assessment
status: proposed
tags: [frontend, api, phase-6]
related:
  - "[ADR-057](/DOCS/adr/ADR-057-react-typescript-product-frontend.md)"
  - "[Issue #404](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/404)"
  - "[First-release spec](/specs/016-product-frontend/spec.md)"
  - "[November 20 assessment](/DOCS/notes/20261120-evidence-api-assessment-404.md)"
---

# Frontend API assessment

Reviewed local Foundry main at `82e0118` through route and model inspection and
existing test and verification records. This review made no live service calls.
The table distinguishes reusable backend behavior from the public product
contract proposed for implementation.

| Experience | Available contract and evidence | First-release dependency |
| --- | --- | --- |
| Repository selection | Ingestion `GET /v1/repos` lists completed repositories. `GET /v1/repos/{id}/generation` returns ready generation and nullable commit. The list also contains local paths and source metadata. | Expose a sanitized picker through Foundry. Confirm readiness on selection and pin the generation for the session. |
| Orient | Orchestrator `GET /v1/repos/{id}/orient` exposes deterministic inventory with an evidence envelope. | Check the returned generation against the selected generation. Display overview and limitations as reported. |
| Locate | Orchestrator `GET /v1/repos/{id}/locate` matches path, glob or basename with optional verified Python definitions for up to five files. `/source/files` supplies cursor pagination. | Label this as file search and Python definitions. Follow file cursors with the same pattern and generation. Treat definition-name and semantic lookup as future capabilities. |
| Read source | Orchestrator `GET /v1/repos/{id}/source/read` accepts exact path, generation and one-based inclusive lines. It verifies the digest of returned text. Current contract limits reads to 500 lines and distinguishes a whole file from an interval. | Pin every read. Use response coordinates for highlights and handle missing, stale, unsupported and oversized requests visibly. Markdown lacks source-read support in the audited path. |
| Ask | `POST /v1/rag` supports explicit standard RAG and returns answer, envelope and structured citations alongside legacy labels. The request schema has no expected-generation field. | Add a generation-pinned product contract. Verify the selected generation before dispatch and the returned envelope and current generation before publishing the result. |
| Verify | RAG citations represent passages admitted to final context. They may lack path or range, and carry generation but no per-citation commit. The envelope provides the nullable commit. | Distinguish consulted evidence from claim-level support. Use the envelope commit when known and preserve range reasons. Never invent ranges. |
| Investigate | `POST /v1/repos/{id}/evidence` exposes fixed structural modes. The internal model-proposer loop is not a product HTTP endpoint. The peri-agent integration and its public response contract are undelivered in this checkout. | Specify an independent run contract through a Foundry-owned boundary. LAB supplies its service contract and operational limits through the owner. |

Sources for the implemented shapes include the [repository routes](/ingestion_service/src/api/v1/repos.py),
[orchestrator routes](/rag_orchestrator/src/api/v1/routes.py),
[source routes](/rag_orchestrator/src/api/v1/source_routes.py),
[RAG models](/rag_orchestrator/src/api/v1/models.py) and
[citation model](/rag_orchestrator/src/core/citations.py).

## Readiness and remaining gaps

- #416 live evidence on deployed SHA `f2e3f2a` showed **15,619 of 17,676**
  Mealie passages with ranges after incremental retagging. The seeded audit
  found no wrong readable range and counted 33 Markdown ranges it could not
  verify. This is evidence for the scope measured. Individual responses can
  still lack a usable range. [Live results](/DOCS/test_results/2026-11-22-416-live-verification.md)
- The orchestrator creates its FastAPI app with default schema settings.
  Source proxy and Locate success responses lack typed response models, so
  relying on the generated schema alone would leave client gaps. Publish an
  explicit, versioned OpenAPI artifact for the product subset and verify it
  against fixtures and endpoints. Peri-agent schema publication remains an
  integration requirement. The LAB application's schema settings were outside
  this assessment. [App entry point](/rag_orchestrator/src/api/v1/main.py)
- A citation's passage digest and a source read's returned-text digest
  describe their respective payloads. The product API should use the existing
  source verification and matching scope before returning a highlight.
  Exact byte equality with a passage can only be claimed when the compared
  payloads are defined to be identical. A missing or rejected range can still
  be shown with its limitation.
- Prefer the orchestrator as the Foundry product API for this increment.
  Route browser traffic through a same-origin path. Use a development proxy
  for the same paths locally. A production-facing integration still needs a
  review of access enforcement at that boundary. A development proxy alone
  supplies no authorization.

The [implementation plan](/specs/016-product-frontend/plan.md) proposes Ask as
the default and a separately gated Investigate mode. The shared citation
viewer can be reviewed and validated using Ask before peri-agent integration.
