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

## Host-only checks — **PENDING (operator)**

Not retrievable over the available HTTP surface (confirmed by the Sept 16
audit; unchanged here). Needs the operator to run these on the host, in
the repo checkout:

- **Running image IDs + OCI revision labels**, one row per container:
  ```
  for name in ingestion-service vector-store-service llm-service rag-orchestrator gradio-ui; do
    echo "== $name =="
    docker inspect "$name" --format 'image={{.Image}} revision={{ index .Config.Labels "org.opencontainers.image.revision" }}'
  done
  ```
- **No application source bind mounts** on any running container:
  ```
  for name in ingestion-service vector-store-service llm-service rag-orchestrator gradio-ui; do
    echo "== $name =="
    docker inspect "$name" --format '{{json .Mounts}}'
  done
  ```
  (both of the above are also checked internally by `prod-refresh.sh`
  itself — `RUNNING_LABELS_CHECK` / `RUNNING_MOUNTS_CHECK` — so the
  auto-generated release record below may already answer this)
- **DB migration head**:
  ```
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec -T ingestion_service alembic current
  ```
- **The `prod-refresh.sh`-generated release record itself**: the script
  always writes one once `--deploy` starts (`write_release_summary`),
  to `<repo-parent>/rag-foundry-release-records/<date>-prod-2026-09-17-2130pm.md`
  by default. That file has the real `CONFIG_CHECK` / `BUILD_CHECK` /
  `BUILT_LABELS_CHECK` / `RUNNING_LABELS_CHECK` / `RUNNING_MOUNTS_CHECK` /
  `HEALTH_CHECK` / `CORPUS_CHECK` / `SMOKE_RESULT` outcomes from the
  actual deploy run (more authoritative than this document's HTTP-only
  re-checks), plus several **FILL IN** fields (DB migration, DB backup,
  repo re-ingestion, graph rebuild, vector re-embedding, config change,
  cadence, operator, rollback command tested, DB restore required,
  notes) that need the operator's judgment. This is the "something after
  deploy" step still outstanding — copying/completing that record and
  landing it in `DOCS/releases/` via a normal branch + PR (per the
  script's own comments; this is a deliberately manual, non-automated
  step). Paste its contents back and I'll fold it into this record and
  open that PR.

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
- **R3/#166** (repo lifecycle): not exercised — would require a delete,
  which is destructive to the current corpus and explicitly out of scope
  for this baseline pass.
- **R1/#160** (bounded ingestion memory), **R2/#161** (orphan recovery):
  not exercised — both require triggering ingestion or simulating a
  worker crash, neither of which is safe to do against the live corpus
  without a dedicated isolated smoke repo (per #171's own acceptance
  criteria — this is exactly the gap #171 exists to close, not something
  this snapshot substitutes for).
- **R6/#169** (healthchecks/provenance): code merged via PR #172
  (2026-09-17), and this deploy is on a commit after that merge, so the
  fix should be live — but not confirmed here. `/version` (also #169's
  work) is confirmed live above (all 4 services responded correctly).
  The corrected Docker healthcheck definitions themselves (audit A8's
  `CMD-SHELL` malformation and wrong internal ports) are not verifiable
  over HTTP — external `/health` returning 200 says the *application* is
  up, not that Docker's own internal healthcheck probe is now correctly
  formed. Needs the operator's `docker inspect <container> --format
  '{{json .State.Health}}'` output per container to close this out.

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

#169's code is merged (PR #172, 2026-09-17) and this deploy is on a
commit after that merge, but the corrected Docker healthcheck
definitions themselves have not been confirmed live (host-only check,
see above) — so #169's Linux validation gate is also still open.

**Caveat for anyone treating this deploy as the current baseline**: it
predates #180/#181, so it has full runtime-identity provenance
(`/version`'s git_sha, confirmed above) but does **not** have full
source-revision provenance — there is no recorded resolved commit SHA or
config fingerprint tying the currently-served corpus to the exact repo
state it was ingested from, beyond the `ingestion_id` itself. Treat this
as the current integrated checkpoint; the provenance gap is disclosed,
not blocking, and is #180/#181's job to close in a later cycle — this
deploy should not be redone solely because #180 is open.
