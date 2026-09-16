# Handoff: red-star production correctness

Updated: 2026-09-16
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

User explicitly requests every red-star fix, issue/spec/plan/roadmap and KB
updates, then commit, push and merge EACH scoped change. Do not stop at planning.
No further approval is needed for routine branches, tests, issues, pushes or
green PR merges. No production SSH exists. Do not conflate code merged with
Linux deployed/validated. User specifically requires session-independent plans
usable by a new session or Claude Code.

## Current state

- Branch: spec/004-bounded-ingestion-memory-issue-160; PR #164 open.
- Starting HEAD: 308f0ac068fb0a8bdbb30ceba34cc6777abfb304.
- Audit reports/probe were untracked at start; authored in the preceding audit
  session and authorized to include in the planning PR.
- #160 memory and #161 recovery already exist. #144 concerns rebuild visibility.
- Created #166 lifecycle, #167 evidence, #168 freshness, #169 health,
  #170 blocking I/O, #171 current release.
- 004 design files amended for M1-M8. Programme spec/plan/tasks and per-issue
  bodies written. No production fix implemented or deployed yet.
- Root uv sync --frozen succeeded. Root .venv/Scripts/python.exe exists.
- Local Docker daemon unavailable. Use CI for real Postgres tests until an
  isolated local/remote test stack is available; do not substitute mocks.

## Immediate next actions

Finish KB/roadmap links and docs verification. Commit/push amended #164,
replace its PR description with the amended final design and issue mapping,
wait for required CI and merge. Then branch from updated main for #160.
Independent #169 health work may proceed without waiting for memory benchmark
infrastructure. Update this handoff before each meaningful transition.

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

Planning PR #164: open, amendment not yet committed/pushed.
Implementation PRs: none yet.
Mandatory live memory/recovery/quality/release gates: all pending.
Do not close the overall objective until every requirement is evidenced.
