---
title: "Product API access enforcement and same-origin boundary: review before external exposure"
date: 2026-11-24
type: assessment
status: accepted
tags: [frontend, security, access, phase-6]
related:
  - "[ADR-057](/DOCS/adr/ADR-057-react-typescript-product-frontend.md)"
  - "[Issue #438](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/438)"
  - "[Issue #208](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/208)"
  - "[First-release spec](/specs/016-product-frontend/spec.md)"
  - "[Enterprise platform plan](/DOCS/audit/05-Enterprise-Platform-Plan.md)"
---

# Product API access enforcement review (#438)

**Status: accepted (2026-11-24). The first release serves a single local user.**
This record states what enforcement the product API has today, what each
audience needs, and the recommendation the owner accepted. It authorizes no
exposure beyond a single local user.

## Decision

On 2026-11-24 the owner chose **audience A, a single local user**. Consequences:

- The frontend port is published on `127.0.0.1` by default (applied in #437).
  Binding it wider is a deliberate operator choice and is outside this decision.
- Audiences B and C are not approved. B needs the items in recommendation 4; C
  needs recommendation 5 and is tracked under #208.
- The backend ports remain published on every interface by the existing Compose
  file; that is a separate hardening decision (recommendation 3).
- #438 is decided. External exposure stays gated until its prerequisites exist.

## What exists today

Checked on 2026-11-24 against `main` plus the #432-#437 branches.

- **No authentication or authorization** in the orchestrator or ingestion
  service. A search of both services' API code and `shared/` found no
  authentication dependency, no token or API-key check, no CORS configuration
  and no middleware on either FastAPI app. This matches the audit's statement
  that no endpoint has authentication
  ([Enterprise platform plan](/DOCS/audit/05-Enterprise-Platform-Plan.md)).
- **No caller identity.** Nothing in a request says who is asking, so nothing
  can scope the repository list or a source read to a caller.
- **No request rate or cost limit** on the orchestrator. The only concurrency
  limit found is an internal semaphore for document fetches. An `ask` call
  spends retrieval and model time.
- **All service ports are published on every host interface** in
  `docker-compose.yml`: ingestion 8001, vector store 8002, LLM 8003,
  orchestrator 8004, Gradio 7860 (and 5434 for Postgres). The ingestion service
  exposes mutating routes (`POST` ingest routes and `DELETE /repos/{id}`).
  Anything that can reach the host can call them directly, with or without the
  frontend.
- **The frontend's nginx mapping is a routing allowlist, not authorization.**
  Through the frontend origin only `/v1/product/*` is reachable (#437). That
  narrows what the *browser path* exposes; it does not protect the published
  service ports or identify a caller.

## Browser-facing routes and their current enforcement

| Route | What it exposes | Current enforcement |
| --- | --- | --- |
| `GET /v1/product/repos` | Every completed repository's name, branch, counts. Paths and URLs are stripped (#432). | None. Not filtered per caller. |
| `GET .../readiness` | Ready generation and commit for a repository. | None. |
| `GET .../orient` | Languages, manifests, services, gaps for a repository. | None. |
| `GET .../files` | File paths in a repository. | None. |
| `GET .../locate` | Matching paths and Python definitions. | None. |
| `GET .../source` | Stored source text, up to 500 lines per call, any path in any indexed repository. | None. Repository ID and generation are caller-chosen. |
| `POST .../ask` | Model-generated answers and cited source locations. | None. Spends model time per call. |
| Investigate (not built, #439) | Agent runs over a repository. | Not applicable yet; the service token must stay server-side. |

The sensitive facts: source text and repository names are readable by any
caller who can reach the origin, and `ask` is an unauthenticated cost surface.

## Audiences and what each needs

| Audience | What is enough | What is missing |
| --- | --- | --- |
| **A. One user on their own machine** (development, the current Gradio use) | Nothing beyond binding to localhost. | Binding today is all interfaces. |
| **B. A small trusted group on a private network** | Network-level access control (for example the existing private network), an explicit decision that every member may read every indexed repository, and a cap on concurrent asks. | A single shared secret or gateway check is a stopgap, not identity. |
| **C. External or multi-team exposure** | Authenticated identity, per-repository authorization, TLS, a gateway that is the only reachable entry point, request and cost limits, audit logging. | All of it. This is #208 (deferred) and is not authorized by ADR-057. |

## Recommendation

1. **First release targets audience A, and B only on an explicitly trusted
   network.** Do not describe the product frontend as safe for audience C.
2. **Publish the frontend port on localhost by default**
   (`127.0.0.1:8080:8080`) and leave wider binding to a deliberate operator
   choice. This is a small change to the #437 Compose service; it is not made
   here.
3. **Treat the published backend ports as a separate hardening decision.** The
   ingestion service's mutating routes are reachable without the frontend. A
   future gateway must be the only reachable entry point, which means
   unpublishing 8001-8004 from the host in that deployment. That is operator
   territory and belongs to #208.
4. **Before any audience B deployment**, add a per-process cap on concurrent
   `ask` requests and a request-size and timeout policy at the gateway, so one
   caller cannot exhaust the model.
5. **Before any audience C exposure**, require at least: gateway-validated
   identity, a per-repository authorization check enforced in the orchestrator
   on every product route (listing included), the same check on ingestion's
   source routes, TLS, and a decision on audit logging. The product API already
   passes `repo_id` on every route except the repository list, so the check has
   a natural place; the list needs a filter by authorized repository.
6. **Investigate** (#439) must keep the agent service token server-side and
   bind run IDs to the authorized caller and repository, as the plan states.
   That is only enforceable once there is a caller identity.

## Questions that framed the decision

1. Which audience does the first release serve: A, B, or C?
2. For B, is "every group member may read every indexed repository" acceptable,
   and which network boundary is relied on?
3. Do you want the localhost-default binding for the frontend port now?
4. Is a concurrency cap on `ask` a prerequisite for B?
5. When C becomes a goal, should it be tracked under #208 with this record as
   its starting inventory?

## Limits of this review

- It is a static review of code and Compose files. No live service or deployed
  host was inspected, and no deployment was changed.
- "No authentication" means none was found in the application code and
  configuration read here. Network-level controls on a particular host (a
  firewall, a private network, a reverse proxy) would not appear in the
  repository and are out of scope.
- It does not assess Gradio's exposure beyond noting its published port.
