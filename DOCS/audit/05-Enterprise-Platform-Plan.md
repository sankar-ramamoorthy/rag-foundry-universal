---
title: "Enterprise Platform Plan — Laptop to Enterprise Web Product"
date: 2026-07-09
type: audit-plan
status: proposed
target: "multi-user, multi-team, self-hosted enterprise deployment"
tags:
  - audit
  - enterprise
  - security
  - deployment
  - rag-foundry
related:
  - "[[04-Scalability-Plan]]"
  - "[[06-LLM-Provider-LiteLLM-Plan]]"
  - "[[00-Audit-Overview]]"
---

# 🏢 Enterprise Platform Plan

> [!abstract] Goal
> Evolve from a single-user laptop stack (docker-compose + Gradio + host Ollama) into an **enterprise web product**: authenticated multi-user access, tenant isolation, production deployment, observability, and pluggable LLMs (the LLM part is detailed in [[06-LLM-Provider-LiteLLM-Plan]]).

## 0 · Honest gap assessment

| Enterprise requirement | Today | Gap class |
|---|---|---|
| Authentication / authorization | **None on any endpoint** | Build |
| Tenant / team isolation | `repo_id` namespacing only; any caller sees all repos | Build |
| Secrets management | Plaintext in `docker-compose.yml` (`ingestion_pass`) | Fix |
| TLS / ingress | None; raw ports on host | Deploy-time |
| Web UI | Gradio prototype (`ingestion_service/src/ui/gradio_app.py` + `gradio/`) | Replace eventually |
| Background processing | In-process threads ([[01-Codebase-Audit-Findings#F-11|F-11]]) | [[04-Scalability-Plan#WP-S5|WP-S5]] |
| Observability | `logging` only; no metrics, traces, request IDs | Build |
| CI/CD | Broken workflow file ([[01-Codebase-Audit-Findings#F-17|F-17]]) | Fix |
| Horizontal scaling | In-memory caches (`codebase_utils.py:15`), per-process state | [[04-Scalability-Plan#WP-S7|WP-S7]] |
| LLM flexibility | Ollama-only, hardcoded | [[06-LLM-Provider-LiteLLM-Plan]] |
| Git-host integration (private repos) | `git clone` of public URLs only, no credentials | Build |

> [!important] Strategic framing
> The service decomposition you already have (4 APIs + DB) is the **right shape** for enterprise — do not merge services or rewrite frameworks. The work is: put a gateway in front, identity through the middle, a queue underneath, and Kubernetes around it.

## 1 · Target architecture

```
                        ┌────────────────────────────┐
   Browser (React SPA)  │  Ingress / API Gateway      │  TLS, OIDC, rate limit
   ──────────────────►  │  (Traefik/NGINX + oauth2)   │
                        └──────┬─────────────────────┘
              ┌────────────────┼──────────────────────────┐
              ▼                ▼                          ▼
      rag_orchestrator   ingestion_service         admin/api service
              │                │        │                 │
              │                │        └── ingestion workers (arq) ── Redis
              ▼                ▼
      vector_store_svc    Postgres + pgvector  (managed / HA)
              │
              ▼
      LiteLLM proxy ──► OpenAI / Anthropic / Azure / Bedrock / Ollama …
```

## 2 · Work packages

### WP-E1 — Security baseline (do first, small)
**Goal:** no unauthenticated endpoint, no plaintext secret, one hardened entry point.
**Directions:**
- Add **service-to-service auth**: shared bearer token (env-injected) required by all internal APIs; FastAPI dependency `verify_internal_token` in each service. (Full OIDC comes in WP-E3; this closes the open-port problem immediately.)
- Move all secrets to `.env` (git-ignored) + `docker-compose` `secrets:`/env indirection; add `SECURITY.md` documenting rotation.
- Single exposed port via a reverse proxy container (Traefik) with TLS (self-signed/dev, cert-manager later); all other service ports become internal-only (`expose:` not `ports:` in compose).
- Fix CORS: nothing currently sets it — make it explicit and restrictive in each FastAPI app.
**Acceptance criteria:**
- [ ] `curl http://host:8001/v1/repos` without token → 401; with token → 200
- [ ] `docker compose config` output contains no literal password strings
- [ ] Only ports 80/443 (proxy) reachable from host network
- [ ] Basic security integration test suite added (`tests/security/`)

### WP-E2 — Deployability: images, config, CI
**Goal:** reproducible builds + working CI; Kubernetes-ready images.
**Directions:**
- Rewrite CI as `.github/workflows/ci.yml` ([[01-Codebase-Audit-Findings#F-17|F-17]]): matrix over services → `uv sync` → ruff → pyright → unit tests; integration job with Postgres service container; image build+push on tag.
- Dockerfiles: pin base images by digest, non-root `USER`, healthcheck endpoints standardized to `/health` (they exist but healthchecks in compose are malformed — the `CMD-SHELL` + list syntax at `docker-compose.yml:47` is wrong and always passes/fails oddly; also ingestion's healthcheck curls port 8002, i.e. the wrong service).
- Config: one `pydantic-settings` class per service, **fail-fast on missing required settings** (today defaults paper over misconfig, e.g. `PgVectorStore` skips table validation "for dual-write test", `pgvector_store.py:22`).
- Helm chart (or Kustomize) under `deploy/`: Deployments per service, HPA for orchestrator + workers, external Postgres/Redis as values.
**Acceptance criteria:**
- [ ] CI green on PR: lint + typecheck + unit tests all services
- [ ] `helm install` on kind/minikube brings up the full stack; smoke test (ingest fixture repo, run query) passes as CI nightly
- [ ] All compose healthchecks actually probe their own service

### WP-E3 — Identity & multi-tenancy
**Goal:** users authenticate via corporate IdP; repos belong to teams; queries are scoped to what the caller may see.
**Directions:**
- **AuthN:** OIDC (Keycloak for self-hosted default; pluggable for Okta/Entra). Gateway validates JWT; services trust gateway-forwarded identity (`X-User-*` headers signed or re-validated).
- **Data model** (new tables in `ingestion_service` schema — it already owns the DB): `organizations`, `teams`, `users`, `repo_grants(repo_id, team_id, role)`. Roles v1: `admin`, `maintainer` (ingest), `reader` (query).
- **Enforcement:** FastAPI dependency resolving caller → allowed `repo_id` set; every repo-scoped endpoint filters by it (this is why WP-S4's move of `repo_id` into a real column matters). `/v1/repos` returns only granted repos.
- **Isolation levels:** v1 = row-level scoping by `repo_id` grants (adequate for single-org enterprise). v2 (multi-org SaaS): schema-per-org or database-per-org — decide only if the product goes SaaS; document as ADR.
- **Audit log:** append-only table of (user, action, repo_id, ts) for ingest/query/admin actions — an enterprise checkbox that's cheap now, painful later.
**Acceptance criteria:**
- [ ] User in team A cannot list, query, or traverse team B's repo (403, tested)
- [ ] Reader role cannot trigger ingestion (403)
- [ ] Audit rows written for ingest + query with user identity
- [ ] OIDC login flow works end-to-end against Keycloak in compose dev stack

### WP-E4 — Private git-host integration
**Goal:** ingest private GitHub/GitLab/Bitbucket repos safely; foundation for the PR-assistant vision.
**Directions:**
- Credential store: per-org git credentials (PAT or GitHub App installation) encrypted at rest (Fernet key from secret store); never logged.
- Clone via token-injected HTTPS in the worker only; shallow clone (`--depth 1`) by default; configurable branch.
- **GitHub App + webhooks (phase 2):** `push` → enqueue incremental ingest ([[04-Scalability-Plan#WP-S6|WP-S6]]); `pull_request` → run fixed graph queries (callers of changed functions, tests touching changed paths) → post PR comment. This is the killer feature from `README_VISION.md` — everything above is its prerequisite chain.
**Acceptance criteria:**
- [ ] Private repo ingests with an org-scoped PAT; token absent from all logs/status metadata
- [ ] Webhook push on a connected repo triggers incremental ingest within 1 min
- [ ] PR opened → structured comment with caller-impact list appears (phase 2)

### WP-E5 — Observability
**Goal:** operate it like a product: metrics, traces, structured logs, request IDs.
**Directions:**
- **Structured logging:** `structlog` JSON logs everywhere; kill import-time `basicConfig`/`setLevel` calls in libraries ([[01-Codebase-Audit-Findings#F-19|F-19]]); one logging config per service entrypoint; propagate `X-Request-ID` across service calls.
- **Metrics:** `prometheus-fastapi-instrumentator` per service + domain counters (artifacts ingested, resolution hit-rate by confidence, chunks retrieved, LLM tokens by provider) → Prometheus + Grafana in `deploy/`.
- **Tracing:** OpenTelemetry auto-instrumentation (FastAPI + httpx + psycopg) → OTLP collector; one trace spanning UI → orchestrator → vector store → LLM.
- **SLO starters:** query availability 99.5%, query p95 < 5 s (excluding LLM generation), ingest job success rate ≥ 99%.
**Acceptance criteria:**
- [ ] A single query produces one trace with spans across ≥3 services
- [ ] Grafana dashboard shows ingest throughput + query latency from the benchmark run
- [ ] Logs are JSON with `request_id`, `repo_id`, `user` fields

### WP-E6 — Product web UI (replace Gradio)
**Goal:** a real frontend for enterprise users; Gradio remains a dev tool.
**Directions:**
- **React + TypeScript SPA** (Vite), served by the gateway. Views: repo list + ingest status (live via SSE from status endpoint), chat-style query with cited sources (canonical_id → file/line deep-links to the git host), graph explorer (Cytoscape.js on the traverse endpoint from [[04-Scalability-Plan#WP-S7|WP-S7]]), admin (teams/grants/providers).
- API layer: create versioned OpenAPI-first contracts; FastAPI already generates schemas — freeze them, generate the TS client.
- **Streaming answers:** SSE endpoint on orchestrator that streams LLM tokens (LiteLLM supports streaming — see [[06-LLM-Provider-LiteLLM-Plan#Streaming]]); Gradio path can keep non-streaming.
- Keep Gradio container behind a `--profile dev` compose flag.
**Acceptance criteria:**
- [ ] Login → repo list → ask question → streamed answer with clickable source links, all through the gateway
- [ ] Graph explorer renders depth-2 neighborhood of a clicked symbol
- [ ] Gradio absent from production Helm values

## 3 · Sequencing & effort

| Order | WP | Est. |
|---|---|---|
| 1 | WP-E1 security baseline | 3–5 days |
| 2 | WP-E2 CI/deploy | 1 week |
| 3 | [[04-Scalability-Plan#WP-S5|WP-S5]] queue (prereq for everything ingest-related) | 1 week |
| 4 | WP-E3 identity & tenancy | 2–3 weeks |
| 5 | WP-E5 observability | 1 week (parallelizable) |
| 6 | WP-E4 git-host integration | 1–2 weeks (+PR bot 2 weeks) |
| 7 | WP-E6 web UI | 3–4 weeks |

> [!warning] Non-negotiable prerequisites from other docs
> Enterprise rollout without [[04-Scalability-Plan#WP-S1|WP-S1–S4]] means the first real monorepo a customer ingests will hang the product. Treat Phase A of the scalability plan as part of "enterprise readiness", not an optimization.
