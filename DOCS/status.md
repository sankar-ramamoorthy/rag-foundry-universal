---
title: "Project Status"
date: 2026-09-19
type: status
status: current
tags: [status, overview]
related:
  - "[Documentation Index](/DOCS/index.md)"
  - "[Multi-Language Graph Plan](/DOCS/audit/03-Multi-Language-Graph-Plan.md)"
  - "[Audit Overview](/DOCS/audit/00-Audit-Overview.md)"
---

# Project Status

Single evolving snapshot of what's currently shipped, in progress, and
known-broken. **Update this file in place** on substantial changes —
don't create a dated copy of it (that was the old top-level `status/`
directory convention, archived 2026-09-18 into
`docs-archive/status-snapshots-2025-2026/` since it had been abandoned
since the repository's first commit; see `DOCS/index.md`'s "Historical"
section) and don't confuse it with [`DOCS/log.md`](/DOCS/log.md), which
tracks documentation-*structure* governance changes, not feature/project
status.

This is where ADR/issue/PR-numbered detail belongs — `README.md` links
here rather than embedding it, so the README stays a stable reference
document.

## Language / codebase graph support

- **Python** — tree-sitter-based extraction, the production default
  since WP-L5 (issue #134, [PR #135](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/135)).
  The legacy stdlib-`ast` extractor is retained as an automatic + manual
  rollback path (`PYTHON_TREESITTER_ENABLED` /
  `PYTHON_TREESITTER_AUTO_FALLBACK` env vars); see the WP-L5 section of
  [`DOCS/audit/03-Multi-Language-Graph-Plan.md`](/DOCS/audit/03-Multi-Language-Graph-Plan.md)
  for the rollback mechanism and parity evidence.
- **TypeScript / JavaScript** — tree-sitter-based extraction, shipped
  (WP-L2, issue #83).
- **Rust** — tree-sitter-based extraction, shipped (WP-L3, issue #130,
  [PR #131](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/131)).
- **Java** — tree-sitter-based extraction, shipped (WP-L4, issue #132,
  [PR #133](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/133)).
- **Retrieval `language` filter** on graph-aware queries — shipped
  (WP-L6a, issue #85), pulled forward ahead of WP-L3/L4 to validate
  WP-L2 against a real mixed-language repo.

## RAG quality

WP-R4/#167 on `fix/wp-r4-evidence-delivery` (commit `cbb84d7`): passage
selection, final-context provenance and generation-scoped retrieval are
implemented and code-reviewed clean against ADR-052, with full local
mechanics coverage. The frozen 8-question quality-evaluation gate
completed 2026-09-18 against the Tailscale production Ollama with a net
positive result (WP-R4 beat legacy 5/8 vs. 3/8; the one case WP-R4
scored worse was root-caused to intended, documented budget-strictness
behavior, not a defect) — see
[mechanics](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md) and
[quality evaluation](/DOCS/test_results/2026-09-18-wp-r4-quality-evaluation.md).
No production/deployment validation is claimed (separate #171 gate).

- The WP-Q0 baseline (issue #49; full evidence in
  [`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`](/DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md))
  measured 70%→90% Recall@5 from graph expansion over raw vector search
  alone.
- Follow-up retrieval-quality fixes and a second evaluation round
  (issues #64, #65, #79, #89, #91) are tracked in that same test-results
  doc and
  [`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`](/DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md).
  #91 (same-relation-type candidate overload) remains open.
- **Doc-type-aware seed tie-break** (issue #142, fix for #141): a
  self-ingested Markdown eval doc's near-verbatim question text could
  outrank the real implementation it discussed badly enough to exclude
  it from the seed search's `top_k` entirely. Fix is merged, flag-gated
  off by default (`DOC_TYPE_TIE_BREAK_ENABLED`) — live re-verification
  on 2026-09-15 found the original repro no longer reproduces post
  corpus drift, so this stays `investigate`, not `validated`; see
  [`DOCS/test_results/2026-09-14-doc-type-tie-break-issue-141.md`](/DOCS/test_results/2026-09-14-doc-type-tie-break-issue-141.md).
- **HNSW post-filter under-recall** (issue #150): a `repo_id`-filtered
  vector search could silently return far fewer rows than requested
  (confirmed capped at ~28 regardless of `LIMIT`, once the shared
  multi-repo `vector_chunks` index made the filter selective enough).
  Fixed via pgvector iterative index scans
  (`hnsw.iterative_scan=relaxed_order` + `max_scan_tuples=20000`),
  restoring full recall at ~17-24ms — see
  [`DOCS/test_results/2026-09-15-hnsw-iterative-scan-issue-150.md`](/DOCS/test_results/2026-09-15-hnsw-iterative-scan-issue-150.md).
- **Optional cross-encoder reranker** (WP-S8, issue #152): implemented,
  flag-gated off by default (`RERANK_ENABLED`), request-overridable
  (`RAGQuery.rerank`/`SimpleRAGQuery.rerank`) for A/B comparison without
  a redeploy. Built deliberately *ahead of* the reranker decision gate's
  own evaluation requirement — see
  [`DOCS/notes/20260915-reranker-built-ahead-of-evaluation-gate-decision.md`](/DOCS/notes/20260915-reranker-built-ahead-of-evaluation-gate-decision.md)
  for why. **Plumbing exercised live; quality benefit remains unvalidated** —
  the [September 15 run](/DOCS/test_results/2026-09-15-wp-s8-rerank-evidence-survival-run.md)
  was contaminated and had insufficient clean cases. The reranker decision in
  [`DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md)
  stays `deferred/NO-GO` as a *default* pending clean, pinned, matched-budget
  comparisons accounting for issue #150's recall fix.

## Incremental ingestion & snapshot lineage

Issue #196 (WP-S6, spec `specs/006-incremental-ingestion-lineage/`):
re-ingesting a repository re-parses/re-resolves the whole graph every
time (ADR-036's deterministic-rebuild guarantee, unchanged), but skips
re-chunking/re-embedding files whose content hash is unchanged from the
prior generation, and records queryable per-generation snapshot
lineage. All three user stories (US1 fast reuse, US2 lineage query,
US3 delete correctness) plus the cross-cutting equivalence proof are
merged to main:

- **US1 (fast re-ingestion) + Foundational persistence** — PR #212
  (Phases 1-3): `persist_graph` upsert-by-`(repo_id, canonical_id)`
  keeps a surviving node's `document_id` stable across generations
  (R1), full repo-scoped relationship replace every generation (R2,
  reused-but-unchanged nodes' stale edges don't survive on node-reuse
  alone), and a content-hash-based `snapshot_diff` classifier gates
  which files skip re-embedding (FR-006, all-or-nothing on a chunking/
  embedding config-version match).
- **US2 (lineage queryable)** — PR #213 (Phase 4): `GET /v1/repos/
  {repo_id}/generation` extended with `commit_sha`, `ingested_at`,
  `parent_generation_id`, `is_incremental` (`contracts/repo-generation-
  lineage.md`), populated only when `generation_status == "ready"` (the
  contract originally said the literal string `"completed"` — that
  value never comes out of `db_utils.generation_status()`'s actual
  ADR-051 vocabulary; corrected in the contract, quickstart, and source
  comments alongside Phase 5/6 work, no runtime behavior change).
- **US3 (deletions never orphaned) + equivalence proof** — Phase 5/6:
  a deleted file's file-level *and* symbol-level canonical IDs leave no
  `document_nodes`/`document_relationships`/`vector_chunks` rows behind,
  and an unrelated unchanged caller's edge to a symbol the deleted file
  used to define re-resolves to `EXTERNAL_SYMBOL:` on the next
  generation, not stale graph state (`test_incremental_deletes.py`).
  The FR-012/SC-002 acceptance bar — incremental ingestion's end state
  equals a clean full rebuild's end state for the same target commit —
  is proven automatically (`test_incremental_equivalence.py`):
  equivalent `(canonical_id, relation_type)` edge sets and
  `(canonical_id, chunk_index, chunk_text)` vector tuples between a
  baseline full ingest and a full-then-incremental ingest reaching the
  same target state via a scripted add/change/delete edit. 15/15 tests
  green against real Postgres + a real `vector_store_service` process.
  Merged to `main` via [PR #214](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/214),
  CI green. Issue #196 closed 2026-09-19 (manually — the PR body had no
  auto-close keyword).
- **#180** (ingestion source-revision provenance) is *not* closed by
  #196 — verified against its acceptance criteria rather than assumed
  subsumed (spec.md's explicit instruction): #196 satisfies only
  "resolved SHA queryable"; pinned-ref admission/rejection, dirty-
  `local_path` disclosure, and an exposed config fingerprint remain
  open, see [issue #180 comment](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/180#issuecomment-5735599046).
- SC-001 (a ~2,000-file fixture, 1 file changed, re-ingest completes
  under 30s) has local evidence (`test_incremental_performance.py`,
  opt-in `slow` marker) but no production-scale/Linux validation —
  same disclosed gap pattern as the WP-R* production-correctness track
  below.

## Repository intelligence (ORIENT)

Issue #197 (blue-star tranche, priority 2/13, named by the
[2026-09-07 repository-intelligence audit](/DOCS/audit/2026-09-07-repository-intelligence-architecture-audit.md)
as the strongest fix for "semantic top-k can't reliably answer 'what is
this repository'" questions): an MVP deterministic repository-structure
inventory, merged to `main` via [PR #215](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/215)
(stacked on #196's branch, since it keys facts by `(repo_id, generation)`
using #196's `ingestion_id`/`commit_sha`; retargeted to `main` and
re-verified green after #214 merged). Issue closed automatically.

- **`ingestion_service/src/core/codebase/structural_inventory.py`** —
  pure, deterministic walk/classify/find pipeline: per-language file
  counts, manifest presence (`pyproject.toml`/`package.json`/
  `Cargo.toml`/`pom.xml`/`requirements.txt`), Docker Compose service
  declarations (dockerfile path, container name, best-effort `command:`
  entry point), heuristic test/docs directory locations, and an explicit
  gap/unknown list (unparseable Compose YAML, unresolvable entry points)
  — no LLM call anywhere in the ingestion-time path.
- **`IngestionRequest.structural_summary`** (migration
  `20260919_orient_inventory`) — a generation-aggregate JSON blob,
  computed once per ingestion and read directly by the query endpoint;
  same generation always returns the same JSON. Inventory-only
  `FILE`/`MANIFEST`/`SERVICE` graph nodes are also persisted (for future
  TRACE/IMPACT traversal), built inside `_build_and_persist_graph` and
  merged into the single `persist_graph()` call — `persist_graph` deletes
  any `canonical_id` absent from the node set it's given, so a second,
  separate call would have silently deleted the symbol graph's own
  nodes. A hard canonical-ID collision rule (a `FILE`/`MANIFEST` node is
  only emitted for a path not already indexed by the symbol graph)
  guarantees no duplicate `MODULE`/`MARKDOWN_MODULE` identity.
- **`GET /v1/repos/{repo_id}/orient`** — 404 with no completed
  generation, 409 when a generation predates this feature
  (`structural_summary IS NULL`) rather than serving an empty/wrong
  inventory.
- Verified two ways: 4 integration tests against real Postgres
  (404/409/deterministic-response/re-ingestion-supersedes-prior-
  generation), and `build_structural_inventory()` run directly against
  this repository's own checkout — correctly found all 6
  `docker-compose.yml` services with real dockerfile paths/container
  names, all 5 `pyproject.toml` manifests, and recorded
  `docker-compose.prod.yml`'s unparseable `!override` YAML tag as an
  explicit `compose_parse` gap instead of crashing. No live two-service
  HTTP round trip (a running `rag_orchestrator` actually calling a
  running `ingestion_service`) or production deployment is claimed.
- **Not yet done, deliberately deferred out of #197's scope**: ORIENT is
  not reachable from `rag_orchestrator`'s query path — `run_rag()` has no
  mode concept today and every existing seam only activates after vector
  search has already run. Tracked as fast-follow
  [issue #216](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/216).
  TRACE/IMPACT (#3) and a general agentic investigator (#12) remain
  separately scoped, not started.

## Evidence sufficiency (#200, Stage A in progress)

Per the [Phase 6 handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md),
#200 (bounded evidence-sufficiency) is implemented before #199
(authority/subject/provenance) as a mechanical-only first pass, with
authority-aware sufficiency deferred to a Stage C follow-up once #199
exists. See [spec 007](/specs/007-bounded-evidence-sufficiency/spec.md).

- **Slices A0 (spec) and A1 (pure assessor) done**:
  `rag_orchestrator/src/retrieval/evidence_sufficiency.py` classifies
  ORIENT facet, TRACE start/target, and IMPACT start/candidate-set
  obligations as `satisfied`/`missing`/`unknown` from already-computed
  results — pure functions, no I/O, no retry, not wired into any request
  path yet. `trace_impact.py`'s `TraceResult` gained a `depth_limited`
  field (distinct from the existing node-count `truncated`) so a target
  cut off by the depth cap is distinguishable from one genuinely absent
  from a fully-explored frontier. 20 new unit tests
  (`tests/test_evidence_sufficiency.py`), plus 2 more in
  `tests/test_trace_impact.py` for `depth_limited`; full `-m unit` suite
  and `ruff`/`pyright` clean.
- **Slice A2 (bounded repair + generation fence) done**:
  `rag_orchestrator/src/retrieval/evidence_workflow.py` adds the pure
  one-repair control loop (`run_orient_workflow`/`run_trace_workflow`/
  `run_impact_workflow`) — TRACE is the only mode with an obligation-
  driven repair in Stage A (extend a depth-limited frontier to the
  server ceiling, at most once); ORIENT has no repair capability yet and
  reports gaps honestly; IMPACT's candidate-set obligation is always
  satisfied so nothing there ever needs repair.
  `rag_orchestrator/src/core/evidence_service.py` adds the I/O adapters
  (`run_orient_evidence`/`run_trace_evidence`/`run_impact_evidence`),
  each reusing `service.py`'s `_query_generation`/`_verify_generation`
  ready-generation pattern (ADR-052) around the work, plus a new
  `get_cached_graph_with_generation` in `codebase_utils.py` so a TRACE/
  IMPACT fence has a generation to check against (the plain
  `get_cached_graph` never exposed one). ORIENT's response is also
  cross-checked against the resolved generation before use, since
  ingestion_service's ORIENT payload carries its own `ingestion_id`.
  21 new unit tests (`tests/test_evidence_workflow.py`,
  `tests/test_evidence_service.py`); full `-m unit` suite (249 passed)
  and `ruff`/`pyright` clean. Still not reachable from any existing
  endpoint — no HTTP route calls these adapters yet.
- **Not yet done**: the `/v1/repos/{repo_id}/evidence` API surface (A3),
  explanation generation wiring (A4), and the live paired-evaluation
  gate (A5) — all tracked under #200, not separately filed yet.

## Known issues

**Production-correctness track (WP-R1–R8) is substantially closed.**
R1/#160, R2/#161, R3/#166, R4/#167, R5/#168, R6/#169, and R7/#170 are all
merged to main; only R8/#171 (full pinned-lifecycle Linux validation) and
two narrow follow-ups (#176 post-delete ANN, #191 migration-gate
tooling) remain open. Full per-item detail is below, kept for its
issue/PR-numbered evidence trail. **What comes next is tracked as a new
roadmap tranche, not restated here** — see
[`07-Roadmap.md`'s Phase 6](/DOCS/audit/07-Roadmap.md#phase-6--repository-intelligence-and-incremental-ingestion-foundation)
and issues [#196](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/196)-[#208](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/208).

- The [September 16 architecture audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md)
  identifies production blockers now tracked as
  [WP-R1–R8](/specs/005-production-correctness/spec.md): #160 memory, #161
  recovery/admission, #166 corpus lifecycle, #167 evidence delivery, #168
  generation-aware cache freshness (split 2026-09-17; source-revision
  provenance now #180, eval-revision provenance now #181), #169
  health/provenance, #170 blocking I/O, and #171 current-release
  verification. At programme creation, these fixes are
  **planned, not implemented or production validated**. Execution state is in
  the [handoff](/specs/005-production-correctness/HANDOFF.md).
  Planning PR #164 is merged. WP-R6/#169 healthcheck and runtime-provenance
  implementation has [local verification evidence](/DOCS/test_results/2026-09-16-healthchecks-provenance-issue-169.md);
  PR #172 is merged with green CI; Linux validation remains pending.
  #160 has an integrated worker merged in PR #175 with
  [unit/real HTTP and PostgreSQL evidence](/DOCS/test_results/2026-09-17-bounded-ingestion-issue-160.md);
  synthetic Linux RSS and graph/vector parity passed; pinned DocsGPT and
  admission/mutation gates remain open. R2/#161 (ownership/admission/recovery)
  is merged to main via PR #177 (`12cf75d`), with real-PostgreSQL/process-kill
  CI evidence, [recovery/admission tasks and rollout](/specs/005-production-correctness/issues/recovery.md)
  and [accepted ADR-049](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md).
  Linux/live rollout validation remains a separate, still-pending #171 gate;
  do not treat merged CI as production deployment. R3/#166 (repository
  rebuild/delete lifecycle) is merged to main via PR #178 (`351dc56`), with
  real-PostgreSQL CI evidence (including a rebuild-in-progress generation
  test) in [its test-results doc](/DOCS/test_results/2026-09-17-repository-lifecycle-issue-166.md)
  and [accepted ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md).
  Its migration's backfill SQL has not been verified against genuine
  pre-#166 historical rows (only against CI's always-empty fresh DB) — a
  disclosed, non-blocking gap. #168 was reconstructed and split on
  2026-09-17 into #168 (generation-aware query/cache freshness, narrowed),
  #180 (ingestion source-revision provenance), and #181 (evaluation
  three-revision provenance) — see
  [freshness](/specs/005-production-correctness/issues/freshness.md).
  #168's narrowed scope is merged to main via PR #183 (`cb36220`), with
  real-PostgreSQL CI evidence in
  [its test-results doc](/DOCS/test_results/2026-09-17-generation-aware-cache-issue-168.md)
  and [accepted ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md):
  `rag_orchestrator`'s graph cache now keys on `(repo_id, generation_id)`
  via a new cheap `GET /v1/repos/{repo_id}/generation` check, LRU-bounded.
  No live two-service HTTP round-trip test exists yet (disclosed in
  ADR-051); vector-store search still filters by `repo_id` only, not
  generation. #180/#181 remain unimplemented. Linux/live rollout validation
  is a separate, still-pending #171 gate. Other fixes remain planned.
  September 17 follow-up #176 tracks intermittent zero ANN results after bulk
  deletion in CI; production impact and exact cause remain unverified.
  R7/#170 (blocking I/O) is merged to main via PR #185 (delete_repo +
  vector-service routes, `0393d8d`) and PR #186 (query embedding,
  reranker, #168/R5 graph-cache fetch, `372f82a`) — see their
  [PR 1](/DOCS/test_results/2026-09-17-blocking-io-delete-vectors-issue-170.md)
  and [PR 2](/DOCS/test_results/2026-09-17-blocking-io-query-path-issue-170.md)
  test results. `main` at `372f82a` (including #170) was deployed to
  production on 2026-09-18 via `scripts/prod-refresh.sh --deploy`
  (release `prod-2026-09-17-2130pm`) — both deploy attempts hit a
  previously-undiscovered healthcheck `start_period` readiness-gate
  defect (containers marked unhealthy before they finished starting,
  then converged healthy unattended/after manual `docker start`), filed
  as #188 with fix PR #189 (CI-green, not yet merged). Separately, a
  migration audit found production's DB one migration behind the
  deployed code (`20260831_language_col` vs. repo head
  `20260917_repo_id_on_requests`, #166) — `ingestion_requests.repo_id`
  was missing, so `DELETE /v1/repos/{repo_id}` and `POST /v1/ingest-repo`
  were both broken in production for an unknown window predating this
  deploy. Applied and verified 2026-09-18 (`alembic upgrade head`,
  confirmed head/column/indexes/backfill/query-shapes); the missing
  release-process gate (no step compares repo vs. production migration
  heads) is filed as #191. Full account in the completed
  [release record](/DOCS/releases/2026-09-18-prod-2026-09-17-2130pm.md)
  and [R8/#171 live evidence](/DOCS/test_results/2026-09-18-r8-live-deployment-evidence-issue-171.md)
  — image IDs/OCI labels, bind-mount absence, and DB migration head are
  now all confirmed. This is explicitly not #171 closure (that needs a
  full pinned fixture ingest/query/delete/redeploy lifecycle test, not a
  snapshot).

- The NVIDIA NIM free-tier LLM provider is currently broken in the live
  deployment (issues #123, #124) — see
  [`DOCS/notes/20260913-free-provider-live-verification.md`](/DOCS/notes/20260913-free-provider-live-verification.md)
  for current per-provider status.

## Production release

- Current pinned deployment SHA and the audited-release history live
  under [`DOCS/releases/`](/DOCS/releases/) — not duplicated here.
