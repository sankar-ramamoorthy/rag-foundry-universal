# Handoff: red-star production correctness

Updated: 2026-09-17
Tracking: #160, #161, #166-#171
This is execution state, not an alternative specification or completion claim.

## Start here in a new session

1. Read CLAUDE.md and .specify/memory/constitution.md.
2. Read this file, spec.md, plan.md and tasks.md in this directory.
3. Inspect git status/log and GitHub issues/PRs; repository/external state wins
   if this handoff is stale. Preserve any user edits.
4. For #160 read all specs/004-bounded-ingestion-memory files. For other work
   read the corresponding issues/*.md and relevant ADR before implementation.
5. Continue the next unchecked task, with acceptance tests before/alongside code.

## Authorization and full objective

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
