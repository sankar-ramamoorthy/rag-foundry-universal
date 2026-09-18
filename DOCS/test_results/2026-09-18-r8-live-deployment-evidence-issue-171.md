---
title: "WP-R8 live deployment evidence: prod-2026-09-17-2130pm baseline"
date: 2026-09-18
type: test-results
status: partial
tags: [release, production, provenance, acceptance, r8]
related:
  - "[Repository architecture audit (A9/A7/A8)](/DOCS/audit/2026-09-16-repository-architecture-audit.md)"
  - "[R8 issue](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/171)"
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
  - "[Prod release record template](/DOCS/releases/prod-release-template.md)"
---

# R8/#171 live evidence — prod-2026-09-17-2130pm

## What this is and isn't

`scripts/prod-refresh.sh --deploy` was run on the production host against
`main` at merge commit `372f82a` (both #170/WP-R7 PRs, #185 and #186,
included). This is the deployed-state evidence gathered immediately
after, over Tailscale HTTP (no SSH channel exists to this host from this
session).

**This is a point-in-time baseline snapshot, not #171 closure.** #171's
acceptance criteria call for a full pinned fixture ingest/query/delete/
redeploy lifecycle test on an isolated smoke corpus, and explicitly say
"never close on scripts or HTTP reachability alone" and "operator
supplies container-level evidence where no remote command channel
exists." Several fields below can only be filled from the host itself
(image IDs, OCI labels, bind-mount absence, DB migration head) — they're
marked **PENDING (operator)** rather than guessed or omitted silently.

## Identity

- Release label: `prod-2026-09-17-2130pm` (from `/version`, all 4 services)
- Deployed git SHA: `372f82a88b382e1682f9368d2d26bef54090c2d0`
- Matches `origin/main` HEAD: **yes**, confirmed by `git rev-parse origin/main`
- Build date (from `/version`): `2026-09-18T01:50:58Z`
- Includes #170/WP-R7 PR 1 (#185) and PR 2 (#186): **yes** — both merged
  into the commit that was deployed
- Operator: sankar Ramamoorthy

## Application-level checks (HTTP, over Tailscale, this session)

| Check | Result |
| --- | --- |
| `/version` git_sha matches approved SHA on all 4 services | pass — `ingestion_service`, `vector_store_service`, `llm_service`, `rag_orchestrator` all report `372f82a88b3...` |
| `/health` on all 5 endpoints (4 services + Gradio :7860) | pass — all HTTP 200 |
| Corpus/generation visibility (`GET /v1/repos`) | pass — 6 completed repos listed, unchanged set from the prior audit's snapshot |
| Self-repo generation endpoint (`GET /v1/repos/{id}/generation`, #168/R5) | pass — `ingestion_id=d4da8274-f2dc-4b66-89fc-684c467c3539`, `generation_status=ready` — same ingestion as the Sept 16 audit's snapshot, confirming no re-ingestion happened as a side effect of this deploy |
| RAG smoke query (`POST /v1/rag`, self-repo) | pass — HTTP 200, real answer with graph-expansion evidence (`expanded_canonical_ids` populated via `hybrid_retrieve`/`get_cached_graph`), `reranked: false` (default off) |
| Health responsiveness during a live ~57s RAG query on the same service | 8/8 concurrent `/health` polls returned in <50ms during the query. Caveat: `rag_orchestrator`'s `/health` is a plain sync route Starlette already threadpools independent of #170's fix, so this shows general responsiveness, not an isolated proof of the async-offload mechanism specifically |

## Host-only checks — resolved 2026-09-18

The operator ran `prod-refresh.sh --deploy` twice more against this same
SHA; both attempts hit the same failure (see "Startup-readiness false
negative" below), so the container/mount provenance below was collected
by manual `docker inspect`, not by the script's own post-deploy section
(which never ran either time). **This manual collection is exceptional
evidence for this one failed-readiness deployment, not a new standing
release procedure** — once #188/PR #189 lands, a normal
`prod-refresh.sh --deploy` run should produce this evidence
automatically again, and manual `docker inspect` should go back to being
a troubleshooting-only step.

- **Running image IDs + OCI revision labels** — pass, all five match the
  approved SHA and release label:

  | Container | Running image ID | OCI revision | Build date | Release version |
  | --- | --- | --- | --- | --- |
  | ingestion-service | `sha256:2e364d1e...` | `372f82a88b382e1682f9368d2d26bef54090c2d0` | `2026-09-18T01:50:58Z` | `prod-2026-09-17-2130pm` |
  | vector-store-service | `sha256:db768834...` | `372f82a88b382e1682f9368d2d26bef54090c2d0` | `2026-09-18T01:50:58Z` | `prod-2026-09-17-2130pm` |
  | llm-service | `sha256:238ed0a9...` | `372f82a88b382e1682f9368d2d26bef54090c2d0` | `2026-09-18T01:50:58Z` | `prod-2026-09-17-2130pm` |
  | rag-orchestrator | `sha256:550cc9c1...` | `372f82a88b382e1682f9368d2d26bef54090c2d0` | `2026-09-18T01:50:58Z` | `prod-2026-09-17-2130pm` |
  | gradio-ui | `sha256:1dbb206e...` | `372f82a88b382e1682f9368d2d26bef54090c2d0` | `2026-09-18T01:50:58Z` | `prod-2026-09-17-2130pm` |

- **No application source bind mounts** — pass. Only bind mount across
  all five containers is `llm-service`'s
  `.../volumes/llm-runtime -> /runtime` (runtime model-policy state, not
  application source — matches the intentional `docker-compose.prod.yml`
  `volumes: !override` for exactly this path). `ingestion-service`,
  `vector-store-service`, `rag-orchestrator`, `gradio-ui` have zero
  mounts.
- **DB migration head** — resolved, and this was not a documentation-only
  gap: production's applied head (`20260831_language_col`) was one
  migration behind the repo's actual head (`20260917_repo_id_on_requests`,
  WP-R3/#166), which added `ingestion_requests.repo_id` — a column the
  deployed application code unconditionally reads/writes. Consequence:
  `DELETE /v1/repos/{repo_id}` and `POST /v1/ingest-repo` were both
  raising `UndefinedColumn` in production. `alembic upgrade head` was run
  against production (this session, explicit authorization) and verified:
  head matches, column/indexes present, backfill correct, and the
  previously-failing query shapes now execute. Filed as
  [#191](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/191)
  (a deployment schema-compatibility gate — no release step currently
  compares repo vs. production migration heads). Full incident writeup
  in the [release record](/DOCS/releases/2026-09-18-prod-2026-09-17-2130pm.md).
- **Startup-readiness false negative** (new finding, not originally
  requested here): both of the operator's last two `--deploy` attempts
  against this SHA failed at `docker compose up -d` —
  `ingestion-service`/`llm-service` were marked unhealthy at 34s/39s and
  Compose aborted dependent startup, even though both later became
  healthy unattended and stayed healthy. Filed as
  [#188](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/188)
  with full timing/`State.Health` evidence; fix (`start_period: 60s` on
  the five app-service healthchecks) is
  [#189](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/189),
  CI-green, not yet merged. This means the script's own automated
  release record for this SHA is `status: incomplete` — see the release
  record below.
- **The `prod-refresh.sh`-generated release record**: copied and
  completed at
  [`DOCS/releases/2026-09-18-prod-2026-09-17-2130pm.md`](/DOCS/releases/2026-09-18-prod-2026-09-17-2130pm.md).
  Its `Deployment validation` section deliberately preserves what the
  script itself actually recorded (`Running-container OCI revision
  labels match`, `Application source bind mounts absent`, `Health
  checks`, `Corpus persistence check`, `RAG smoke query` = `not run`,
  since `--deploy` exited before that section ran) rather than being
  overwritten with this session's independent post-hoc HTTP/`docker
  inspect` results, which are recorded separately in that file as
  "independent post-deploy verification (this session, not the script)."

## R1/R2/R3/R5/R6/R7 non-destructive live status

- **R7/#170** (this deploy's headline change): covered above —
  deployed SHA includes it, smoke query exercises the exact code paths
  changed (`embed_query`, `hybrid_retrieve`→`get_cached_graph`),
  reranker path not exercised live (off by default, not toggled here to
  avoid non-default load on a single-GPU host during a baseline check).
- **R5/#168** (generation-aware graph cache): confirmed — the generation
  endpoint returns a real `ingestion_id`/`generation_status`, and the
  smoke query's `expanded_canonical_ids` shows graph expansion actually
  ran (i.e. `get_cached_graph` resolved a generation and served a graph).
  No re-ingestion was performed in this session, so cache invalidation
  on a generation change was **not** exercised live here (would need a
  deliberate re-ingest, which is out of scope for a non-destructive
  baseline check).
- **R3/#166** (repo lifecycle): live `DELETE`/rebuild behavior itself not
  exercised end-to-end (destructive, out of scope for a baseline pass),
  but the migration investigation above found R3's *code* was running
  against a database missing the column it depends on
  (`ingestion_requests.repo_id`) — i.e. `delete_repo` was actually broken
  in production until the migration was applied 2026-09-18. Now schema-
  correct and verified via the read-only query-shape check above; still
  not verified via a real end-to-end delete.
- **R1/#160** (bounded ingestion memory), **R2/#161** (orphan recovery):
  not exercised — both require triggering ingestion or simulating a
  worker crash, neither of which is safe to do against the live corpus
  without a dedicated isolated smoke repo (per #171's own acceptance
  criteria — this is exactly the gap #171 exists to close, not something
  this snapshot substitutes for).
- **R6/#169** (healthchecks/provenance): confirmed live 2026-09-18.
  `docker inspect --format '{{json .Config.Healthcheck}}'` on
  `ingestion-service`/`llm-service`/`rag-orchestrator` shows the CMD
  argv form (`["CMD","python3","-m","shared.healthcheck",...]`) with the
  correct internal port for each service — audit A8's `CMD-SHELL`/
  wrong-port malformation is gone, PR #172's fix is live. `State.Health`
  logs show 5 consecutive passing probes at ~0.1-0.2s each once the app
  is actually serving. What A8/#169 did **not** cover — a `start_period`
  grace window — is the separate gap this deploy surfaced; tracked as
  #188/#189, see below.

## Explicitly still open (per current issue tracker state)

#160, #161, #166, #168, #169 show as OPEN on GitHub despite merged code
— consistent with this repo's known "Tracked by" vs. "Closes" gap (PRs
reference the issue without a closing keyword). Do not read GitHub issue
state alone as "not implemented"; see each issue's linked test-results
doc for actual code status. Genuinely unimplemented, confirmed open:

- **#180** — ingestion source-revision provenance (resolved commit SHA,
  config fingerprint recorded at ingest time). Not present in this
  deploy: the self-repo's `ingestion_id` above carries no git-ref
  identity of what was actually cloned/ingested.
- **#181** — evaluation three-revision (runtime/corpus/ground-truth)
  provenance.
- **#176** — intermittent zero-ANN-results after bulk deletion in CI;
  production impact unverified.
- **#188** — healthcheck `start_period` false negative (fix: PR #189,
  CI-green, not merged).
- **#191** — deployment schema-compatibility gate (no release step
  compares repo vs. production Alembic head; this is how #166's
  migration went silently unapplied — see the release record).

#169's code is merged (PR #172, 2026-09-17) and this deploy is on a
commit after that merge, and the corrected Docker healthcheck
definitions were confirmed live 2026-09-18 (`Config.Healthcheck` shows
the CMD argv form with correct ports on all three checked services) —
see R6/#169 above. #169's code is confirmed live; #188's separate
`start_period` gap remains open.

**Caveat for anyone treating this deploy as the current baseline**: it
predates #180/#181, so it has full runtime-identity provenance
(`/version`'s git_sha, confirmed above) but does **not** have full
source-revision provenance — there is no recorded resolved commit SHA or
config fingerprint tying the currently-served corpus to the exact repo
state it was ingested from, beyond the `ingestion_id` itself. Treat this
as the current integrated checkpoint; the provenance gap is disclosed,
not blocking, and is #180/#181's job to close in a later cycle — this
deploy should not be redone solely because #180 is open.
