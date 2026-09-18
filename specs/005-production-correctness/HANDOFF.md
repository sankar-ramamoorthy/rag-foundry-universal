# Handoff: red-star production correctness

Updated: 2026-09-17
Tracking: #160, #161, #166-#171, #180, #181
This is execution state, not an alternative specification or completion claim.

## WP-R4 handoff ? owner requested checkpoint near usage limit

Branch: `fix/wp-r4-evidence-delivery`. Base: `3ba6a2f4cec4d3e0724859d70aeff98bb7f7880f`.
The checkpoint commit is the latest commit on that branch; inspect `git log -1`.
**WP-R4 is not complete. Do not close #167 or merge based on this checkpoint.**
No PR was opened and no quality questions or generation controls have run.

Implemented and saved: query-aware exact per-artifact passage fetch with stable
ordinal ties and optional repo/ingestion filters; seed supplementation; stored
ordinal separate from fetch position; explicit relaxed ANN sorting; query-term
canonical-ID preference within graph relation priority; generation-scoped seed
and passage retrieval with post-retrieval generation check; single context
selection returning text/chunks; final-only sources and manifest including
content hashes; simple-document expansion inclusion; separate reranker loss.
No embedding/reranker model defaults changed. See
[ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md),
[verification](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md), and
[issue specification](/specs/005-production-correctness/issues/evidence.md).

Latest checks: 173 orchestrator tests passed / 1 live A/B skipped; 28 vector
unit tests passed / 13 deselected; 1 real PostgreSQL passage test passed;
root ruff and diff whitespace checks passed. Focused pyright has baseline
missing sentence_transformers and vector Settings DATABASE_URL diagnostics.
New PostgreSQL test is explicitly added to CI. CI has not run on this branch.

### Live local evaluation state ? poll before restarting

A fresh, isolated database `wp_r4_741f14a1c7_test` exists in the test PostgreSQL
container `ingestion-db-test`, port 5433, all migrations applied. It uses the
credentials already specified in docker-compose.test.yml. Do not delete or
re-ingest existing production corpora. The original `ingestion_test` DB had
historical active rows blocking admission; no such rows were altered. The
fresh evaluation DB avoids that unrelated historical state.

Local HTTP services (real code, not mocks): ingestion `http://localhost:18011`,
vector `http://localhost:18012`; embedding `http://localhost:11434` with existing
`mxbai-embed-large:latest`. Ingestion job:
`bc88625d-8168-40e5-8e99-4cfac38ae50f`; repo:
`f6901107-aedc-562a-9709-956aa4e1e03e`.
Last authoritative GET `/v1/ingest-repo/bc88625d-8168-40e5-8e99-4cfac38ae50f`
returned `running`, stage embedding, nodes 27/396, chunks persisted 0,
maximum buffer 110 chunks / 72789 bytes. This is a live job, not a completed
corpus. Repeated unchanged counters alone do not prove death; poll the same
job and inspect its process/logs. Do not restart solely for slow observation.
Graph persistence reported 1284 nodes and 1950 relationships.

Local ignored `.wp-r4.tmp/` contains exported corpus, full manifest, ingestion
response, database connection configuration, PID records and stdout/stderr logs.
It remains on this workspace but is not pushed. Exported files are reproducible
from base SHA using the checked-in manifest and `git show SHA:path`.
Process records: `.wp-r4.tmp/eval-processes.json` (launcher PIDs 15500/20008);
uvicorn logs report vector PID 8980 and ingestion PID 24712. Earlier auxiliary
services remain on ports 18001/18002 using `ingestion_test`, with launcher PIDs
23252/3584 and server PIDs 20476/23452. Verify current command lines before any
cleanup; never kill by name or reuse old PID numbers without checking.
All launches were hidden. No evaluation runner is active.

### Next actions

1. Poll the exact ingestion job and inspect `.wp-r4.tmp/eval-ingestion_service.err`.
   Resolve a reported failure if terminal; otherwise preserve the running job.
2. Review conservative context budget/query/output headroom and passage-stage
   trace completeness. Current budget is UTF-8 bytes including labels/separators,
   with configured prompt/output allowances, not active-provider tokenization.
   Generation output limit is not enforced by this patch. See ADR limitations.
3. Finish evaluation harness using the frozen
   [eight questions](/DOCS/evaluations/wp-r4-questions.json) and
   [protocol](/DOCS/evaluations/2026-09-17-wp-r4-protocol.md). The corpus is 54 real
   source-only Python files exported from base SHA; answer keys/tests/audits are
   excluded. [Manifest](/DOCS/evaluations/wp-r4-corpus-manifest.json) pins every
   file. No TS or real document quality coverage is implied by these questions.
4. Pin runtime and ground-truth revisions independently. Run baseline,
   WP-R4, matched-budget control, clean/noisy generation; retain exact prompts,
   manifests, model/digest/fallback, stage traces and rubric grades. Local Ollama
   and Linux LLM health responded, but no generation model has been selected.
   Production deployment was not changed.
5. Review results, correct demonstrated failures, refresh docs and tests,
   push dedicated PR, inspect required CI, and follow authorized delivery flow.
   Keep deployment acceptance distinct from code/quality completion.

## Usage-limit checkpoint instruction

Owner requests a documented, committed checkpoint when either usage allowance
reaches 5% remaining, so another session or Claude can resume. This session has
no reliable account-quota percentage feed; do not confuse goal token accounting
with daily/weekly allowance or claim to monitor an unavailable percentage.
Checkpoint proactively at meaningful milestones and immediately on a surfaced
low-quota warning or owner notification. Include branch/head, CI run/PR state,
known failures, pending gates and exact next actions; commit and push authorized
changes without falsely marking incomplete work complete.

R2 MERGED: PR #177 squash-merged to main at `12cf75d88b6f35c7e3ed7a251331f251d6883a80`
on September 17. Final pre-merge head 7af4507 passed all four checks in CI run
35270392032 (lint, unit, integration, bounded-memory) after the docs-only
checkpoint (recovery.md checklist fully checked, ADR-049 flipped to accepted,
PR body rewritten to match the already-implemented/CI-validated state). Issue
#161 code/CI work is complete; the issue itself stays open pending Linux/live
rollout evidence, which is a separate #171 gate — do not deploy on the owner's
behalf and do not treat merged CI as production validation.

R3 (#166) MERGED: PR #178 squash-merged to main at
`351dc56a66c6b6f06e31f9738baf2407d9446652` on September 17. Implemented:
`repo_id` persisted on `ingestion_requests`
(migration `20260917_add_repo_id_to_ingestion_requests`, backfilled from
document_nodes); repo-scope advisory lock serializing ingest vs. delete;
`list_ingestion_ids_for_repo` retry-safe via repo_id (document_nodes fallback
kept); `resolve_current_generation`/`generation_status` gating graph reads on
the actual document_nodes owner's ingestion status (discovered mid-
implementation that `persist_graph` already atomically replaces all of a
repo's document_nodes at graph-build time, before embedding/completion — so
generation resolution corrects for that rather than assuming a prior
generation stays visible during rebuild); best-effort superseded-generation
vector/request cleanup after a successful rebuild. ADR-050 (accepted) and
[evidence doc](/DOCS/test_results/2026-09-17-repository-lifecycle-issue-166.md)
written. Local: 310 ingestion unit tests pass (up from 307), lint clean, focused
pyright clean on touched files (one real `str | None` narrowing fixed in
`ingest_repo`; remaining pyright noise is the same pre-existing
import-resolution baseline as R1/R2). Final pre-merge head `f55ce5f` passed
all four CI checks (run 35276463515): lint, unit-tests, integration-tests
(including the new `test_repo_lifecycle.py` real-PostgreSQL suite — 16
tests passed, alongside the pre-existing `test_db_utils_repo_delete.py`
which CI's file-allowlist had never actually run before this PR extended
it), bounded-memory. rag_orchestrator's graph cache does not yet consult
`generation_status` — disclosed as #168's scope, not folded into this PR.
Migration backfill SQL runs for real in CI but only ever against an empty
fresh test DB, so its behavior on genuine pre-#166 historical rows remains
unverified (disclosed in the evidence doc, not blocking merge since the
document_nodes fallback covers any row it misses). Issue #166 code/CI work
is complete; the issue stays open pending Linux/live rollout evidence, a
separate #171 gate — do not deploy on the owner's behalf and do not treat
merged CI as production validation.

R5 (#168) SCOPE SPLIT: #168 reconstructed against current (post-R3) code at
owner's request, before any implementation. Its original text bundled three
unrelated concerns; split into #168 (generation-aware query/cache freshness,
narrowed), #180 (ingestion source-revision provenance), #181 (evaluation
three-revision provenance) — docs-only PR #182, merged. No #180/#181
implementation has started.

R5 (#168 narrowed) MERGED: PR #183 squash-merged to main at
`cb3622056cd58a08961e450c8b9c2383b47af6e1` on September 17. Owner gave
explicit go-ahead after the scope split. `rag_orchestrator`'s `_repo_graphs` cache
was process-global, unbounded, keyed only by `repo_id`, never reloaded — a
warm worker kept serving a stale graph after a repo was re-ingested, even
though R3 already fixed the *data*-correctness half at the source
(`/v1/graph/repos/{repo_id}` returns one current-completed generation's
nodes, plus a `generation_status` field the orchestrator was discarding).
Implemented: new cheap `GET /v1/repos/{repo_id}/generation` on
`ingestion_service` (wraps #166's `resolve_current_generation`/
`generation_status`, no full graph fetch); `get_cached_graph` now keys on
`(repo_id, generation_id)`, LRU-bounded (`GRAPH_CACHE_MAX_REPOS`,
thread-safe via a lock); no-completed-generation short-circuits to an empty
graph without fetching or caching. `hybrid_retrieve` calls
`get_cached_graph` exactly once per request, so resolving generation once
per call structurally prevents mixing two generations within one query.
ADR-051 (accepted) and [evidence doc](/DOCS/test_results/2026-09-17-generation-aware-cache-issue-168.md)
written. Local: ingestion_service 314 unit tests pass (up from 310),
rag_orchestrator 162 pass (up from 158), lint clean on all touched files,
focused pyright clean (only pre-existing baseline import-resolution noise).
Final pre-merge head `0adbb3b` passed all four CI checks (run 35281353921):
lint, unit-tests, integration-tests (20 real-Postgres repository-lifecycle/
generation tests — 16 from #166 plus 4 new), bounded-memory. One CI attempt
at this same head hit the pre-existing known-flaky #176 ANN symptom
(unrelated to this PR — confirmed by its own VACUUM-retry diagnostic step
passing); a plain re-run of the failed job came back green, not treated as
a regression. Disclosed non-goal: no live two-service HTTP round-trip test
exists anywhere (unit tests mock the HTTP seam on the orchestrator side;
the integration test exercises the real route against real Postgres on the
ingestion side — both together, not an end-to-end process test).
Vector-store search still filters by `repo_id` only, not generation — a
residual gap noted in ADR-051, not closed here. Issue #168 code/CI work is
complete; the issue stays open pending Linux/live rollout evidence, a
separate #171 gate — do not deploy on the owner's behalf and do not treat
merged CI as production validation. #180/#181 remain unimplemented,
untouched by this PR.

## Start here in a new session

1. Read CLAUDE.md and .specify/memory/constitution.md.
2. Read this file, spec.md, plan.md and tasks.md in this directory.
3. Inspect git status/log and GitHub issues/PRs; repository/external state wins
   if this handoff is stale. Preserve any user edits.
4. For #160 read all specs/004-bounded-ingestion-memory files. For other work
   read the corresponding issues/*.md and relevant ADR before implementation.
5. Continue the next unchecked task, with acceptance tests before/alongside code.

## Authorization and full objective

Latest update: owner resumed **R2** on September 17 and will wait to deploy.
Branch `fix/161-ingestion-recovery-admission` starts from merged R1 main
`12040f1`; handoff commit `4258ea0` carried forward as `cd17e54`.
Read [R2 tasks/design review](./issues/recovery.md). Three file-setup exception
regressions were reproduced failing and now pass locally. Ownership primitive
and reconciliation helper added (not route/startup wired); terminal status
resurrection blocked. Seven focused R2 unit tests and all 295 ingestion unit
tests pass. PostgreSQL/process-kill tests added to CI, execution pending.
Next: draft PR for early real-DB validation; finish design/ADR, integrate both
routes and recovery trigger, ownership-loss work-boundary checks, HTTP tests,
legacy maintenance procedure and real vector-write death test. R2 incomplete.
This instruction supersedes the earlier pause below; R3 is not started.

R2 continuation: draft PR #177, foundation fb9fce8. CI 35267843408 passed
lint/unit/memory but ownership integration failed: this SQLAlchemy version
requires dbapi_connection, not driver_connection. Corrected locally. Routes now
use submit_ingestion; startup and 5-second sweeps reconcile managed attempts;
context-bound guard checks protect status, embedding, vector dispatch and graph
commit boundaries. Sixteen focused tests and 304 ingestion unit tests pass;
new core modules pass focused pyright and repo lint. Pending: green real-DB CI,
actual vector-write kill test, lifecycle/startup tests, legacy operator command,
ADR/KB evidence, final review and merge. Do not claim distributed write fencing:
already-dispatched HTTP writes can complete after lock loss; R3 remains separate.

Latest R2 CI: cc4fd70 / 35268896379 passed eight real PostgreSQL ownership tests
and the real vector-write kill test (14 acknowledged vectors retained). One
R1 parity fixture reused a completed attempt; 96952ce corrects it to fresh
attempts, preserving parity assertions, and adds a guard before file CRUD's
internal commit. Seventeen focused tests pass. 96952ce is pushed; await its CI.
[Evidence ledger](/DOCS/test_results/2026-09-17-ingestion-recovery-issue-161.md).
ADR-049 and legacy rollout command are written. Remaining: final green CI,
review/KB checklist updates and merge; Linux evidence remains operator-owned.

Latest owner instruction (September 17): **resume, but pause after R1**.
Do not begin R2 or later implementation without a new instruction.
Final R1 head `696476e7d27d675d3b69ae327f4e55329b37b94b` passed all four
checks in CI run `35221220107` (lint, unit-tests, integration-tests,
bounded-memory). After explicit owner approval and rechecking all four checks,
PR #175 was squash-merged at `12040f133052bbb614b23bc1dcb6653dbd408c7d`
on September 17 at 18:52:23 UTC; GitHub confirms MERGED. Issue #160 remains
OPEN for T012 and T016. Work is now paused as requested; R2 has not started.
This update supersedes the pre-merge execution history below. Handoff and
task-checkbox updates are a separate documentation follow-up, not part of PR #175.

User explicitly requests every red-star fix, issue/spec/plan/roadmap and KB
updates, then commit, push and merge EACH scoped change. Do not stop at planning.
No further approval is needed for routine branches, tests, issues, pushes or
green PR merges. No production SSH exists. Do not conflate code merged with
Linux deployed/validated. User specifically requires session-independent plans
usable by a new session or Claude Code.

## Pre-merge execution history

- Branch: fix/160-bounded-ingestion-memory; partial implementation, not release-ready.
  Draft PR #175. Worker now uses generation-scoped keyset pages and the
  count/UTF-8-byte-bounded EmbeddingBuffer, with stable document ordinals.
  Graph-build helper returns scalar stats; weakref tests prove graph/builder
  lifetime ends before embedding, and page tests forbid predecessor retention.
  Progress starts before reads; fresh JSON updates and terminal stages exposed
  by status endpoint. 288 ingestion unit tests passed; lint passed. Focused
  buffer types passed; broader types still report baseline ORM/GitPython issues.
  First PostgreSQL CI: 3 paging tests passed; empty fixture used invalid UUID.
  Fixture corrected; fresh-session progress and real paging/status tests added.
  Follow-up 9edf84b passed full CI run 35219308277: nine real PostgreSQL tests,
  including separate vector-service HTTP parity and durability. Query-plan
  probe f9868f1 passed CI 35219461132: 10 integration tests, existing PK index,
  32-row late page from 4000 nodes in 0.036ms. No new index from this fixture;
  not proof of selective multi-repo scale.
  Linux RSS harness added at d0b6603: calibration run 35220047904 passes SC-002
  synthetic criterion and all observed bounds (N +7,991,296B; 4N +4,784,128B).
  Raw JSONL archived under DOCS/test_results/data/issue-160-calibration-35220047904.
  Entire CI fails after benchmark deletion: ANN tests return zero rows (#176).
  5827b67 adds test-only VACUUM diagnostic retaining original failed gate.
  Run 35220317090 passed ANN tests on repeat, so vacuum diagnostic was skipped;
  symptom intermittent, not resolved or proven vacuum-responsive.
  Memory acceptance moved to its own CI job/database (same fixture/criterion),
  not a production fix for #176. Separate synthetic acceptance passed run
  35220643252 at c264325; archived raw samples in issue-160-acceptance-35220643252.
  Full real rebuild graph/vector parity at 1/7/128 passed fb33c4b, run
  35220823709. SC-002 passed; DocsGPT/production gates remain open.
  [Evidence](/DOCS/test_results/2026-09-17-bounded-ingestion-issue-160.md).
- PR #172 merged after lint/unit/PostgreSQL integration CI passed on
  36a1a62d370fd94338f89243b200880d68bedd15 (run 35172556194).
  Main merge: 2b198b6f96c3ce54c5f031cef11e9ebd2f306614.
- Planning PR #164 merged with green unit and PostgreSQL integration CI.
  Main merge: 853b0e3814a228337028929109a44ed837f5fd2d.
- Audit reports/probe were untracked at start; authored in the preceding audit
  session and authorized to include in the planning PR.
- #160 memory and #161 recovery already exist. #144 concerns rebuild visibility.
- Created #166 lifecycle, #167 evidence, #168 freshness, #169 health,
  #170 blocking I/O, #171 current release.
- 004 design files amended for M1-M8. Programme spec/plan/tasks and per-issue
  bodies written. #169 healthcheck/provenance implementation locally tested;
  no production fix deployed yet.
- Root uv sync --frozen succeeded. Root .venv/Scripts/python.exe exists.
- Local Docker daemon unavailable. Use CI for real Postgres tests until an
  isolated local/remote test stack is available; do not substitute mocks.

## Immediate next actions

Pause after merged R1, per owner instruction. Do not start #161 or #166 until
the owner resumes implementation. Latest paging uses SQLAlchemy select/execute to avoid new ORM stub typing
errors; five pre-existing typing errors in persistence and missing root
GitPython remain, documented (service dependency already declares GitPython).
Keep #160 open for T012 admission/mutation protection and T016 DocsGPT. When
authorized to resume, implement #161, then #166, with shared ownership design;
see issue specs. Current code is suitable for isolated validation, not an
unrestricted production rollout: those mandatory deployment gates remain open.
Do not treat #176 as fixed: preserve its controlled post-delete regression work
for separate PR. Pinned DocsGPT and actual Linux ceiling are
still unknown; operator target-host evidence required. Retain unexecuted
production gates; merged code and synthetic acceptance do not satisfy them.
GitHub upstream default main resolved on September 17 to
fbcf320458386558906388c030b4149906ef3877; this is a potential NEW DocsGPT
baseline, NOT the incident SHA. No clone/benchmark on that revision yet.
Keep #169 open until Linux Docker health/image evidence is recorded.
Local #169 results and remaining gates:
[evidence](/DOCS/test_results/2026-09-16-healthchecks-provenance-issue-169.md).
Use root .venv for service suites. For llm tests disable ambient personal
dotenv: PYTHON_DOTENV_DISABLED=1 and empty LLM_DEFAULT_ALIAS,
REMOTE_OLLAMA_BASE_URL, WINDOWS_OLLAMA_BASE_URL. Do not edit user .env.

## Important design decisions already made

- #160: independent node-page, artifact-byte, chunk-count and chunk-byte limits;
  explicit oversize failure, no silent truncation; preserved chunk semantics.
- Explicit chunk ordinal interface extension is allowed/required across buffers.
- Graph references must leave scope before embedding. Paging scopes repo+attempt.
- Partial durability is NOT resume; remove one-slice retry guarantee.
- #161/#166 must share coherent worker/mutation ownership, not race-prone guards.
- Explicit unavailable/building state during rebuild is allowed; partial/mixed
  generation serving is not. Uninterrupted old-corpus availability is separate.
- Retrieval changes require clean pinned quality evidence, not just unit tests.
- Current status/roadmap/indices evolve; dated audit remains historical.

## Access and commands

gh auth status in sandbox falsely reports invalid token; outside sandbox it
succeeds with OS keyring credentials. Escalate gh commands when necessary;
do NOT log out, replace credentials or print tokens. Remote origin is
https://github.com/sankar-ramamoorthy/rag-foundry-universal.git.
Use gh PR checks and inspect merge status after merge; do not bypass CI.

Production HTTP: 100.105.24.12 ports 8001-8004/7860. September 16 audit made
read-only checks only. Current deployed SHA/cgroup ceiling/DocsGPT incident
source SHA are not established. Need operator container evidence for #171.

Windows file reads: Get-Content -Encoding UTF8 (default decoding corrupts
Unicode patch matching). Use apply_patch for edits. New docs under DOCS need
OKF type/frontmatter and Markdown links. GitHub multiline bodies use --body-file.

## Completion ledger

Planning PR #164: merged, 853b0e3814a228337028929109a44ed837f5fd2d.
Implementation #160: PR #175 merged, 12040f133052bbb614b23bc1dcb6653dbd408c7d;
synthetic acceptance passed; admission/mutation and pinned DocsGPT gates pending.
Implementation #169: PR #172 merged; Linux host validation still pending.
Mandatory live memory/recovery/quality/release gates: all pending.
Do not close the overall objective until every requirement is evidenced.
