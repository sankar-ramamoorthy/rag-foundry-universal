# Specification: production correctness programme

Created: 2026-09-16
Status: Planned; delivery in separate issue-backed PRs
Tracking issues: #160, #161, #166, #167, #168, #169, #170, #171
Roadmap: Phase 4 / WP-R1 through WP-R8
Audit: [September 16](/DOCS/audit/2026-09-16-repository-architecture-audit.md)

## User objective

Fix every red-star production correctness/scale issue identified by the audit,
with clear specs/plans, roadmap and ontology-based knowledge-base updates,
tests/evidence, and a separate committed, pushed and merged PR per work item.
Planning alone, green unit tests alone, or implemented-but-unvalidated runtime
behavior does not satisfy the full objective.

## Work packages and acceptance ownership

| Package | Issue | Contract/spec | Completion evidence |
| --- | --- | --- | --- |
| WP-R1 bounded ingestion memory | #160 | [004 spec](../004-bounded-ingestion-memory/spec.md) | Normalized parity, bounded buffers, PostgreSQL tests, pinned Linux/DocsGPT memory runs |
| WP-R2 recovery/admission | #161 | Recovery contract below; [implementation tasks](./issues/recovery.md) | Hard-death reconciliation, live-worker protection, bounded concurrent work |
| WP-R3 corpus lifecycle | #166; related #144 | [lifecycle](./issues/lifecycle.md) | Durable attempt identity, retry cleanup, mutation exclusion and truthful serving state |
| WP-R4 evidence delivery | #167; related #91/#141/#145/#149/#156 | [evidence](./issues/evidence.md) | Exact prompt/manifest agreement and pinned uncontaminated stage/quality evaluation |
| WP-R5 snapshots/cache | #168 | [freshness](./issues/freshness.md) | Resolved commit, generation-consistent queries and bounded invalidated caches |
| WP-R6 health/provenance | #169 | [health](./issues/health.md) | Real probe success/failure, correct ports and runtime revision |
| WP-R7 blocking I/O | #170 | [async](./issues/async.md) | Unrelated requests remain responsive under controlled slow operations/saturation |
| WP-R8 current release | #171 | [release](./issues/release.md) | Current Linux full lifecycle and container provenance/release evidence |

## Recovery/admission contract (#161)

An accepted or running job cannot remain apparently active after its owning
process dies. Record a terminal failure reason/timestamp and retain partial
data for explicit cleanup; do not automatically rebuild or delete user data.
Never fail another live worker's job simply because a second process starts.
Use database-backed worker ownership/exclusivity or leases with conservative
expiry; a wall-clock job-age threshold is not a liveness proof.

Bound accepted active ingestion work, including file and repository routes.
Reject saturation with a clear retryable status before allocating an upload's
full bytes or cloning. A durable queue is not required. Test death after
acceptance but before thread launch, death during embedding, startup with a
live competing owner, worker exceptions before mark_running, and JSON error
persistence from a fresh database session. Coordinate shared ownership and
repository locks with #166 rather than implement independent race-prone guards.

## Architectural constraints

Follow the constitution and applicable ADRs: canonical identity, graph/vector
DB boundaries and HTTP service separation. Preserve model-used/fallback
provenance. No change of embedding model, default reranker or autonomous router.
Disclose existing artifact-vs-subchunk and pipeline-factory drift. If a new
decision supersedes an ADR, write an issue-linked ADR with explicit scope and
update its links/status; do not silently change the definition in a spec.

The initial rebuild contract may explicitly make a repository unavailable
while building or after failure. It must never serve a mixture of generations
or hide that state. Preserving uninterrupted old-generation service requires
staged publication and is not implied by graph-transaction atomicity.

## Cross-package acceptance

- One query uses one completed ingestion generation or returns an explicit
  retryable generation-change/building response; it never mixes cached edges
  with another snapshot's vectors.
- Delete and ingest cannot mutate the same repository concurrently. Retry
  after interruption completes cleanup, including attempts with no graph rows.
- Needed evidence must cross the actual prompt boundary; source and manifest
  claims describe that payload exactly. Distinguish candidate discovery,
  document selection, passage selection, rerank and context-budget losses.
- Memory controls cover bytes and chunk count; graph build and GPU memory
  are measured separately from embedding working state.
- Health probes demonstrably fail on unavailable endpoints. Runtime HTTP
  provenance complements rather than substitutes image/mount evidence.
- Current runtime revision, ingested source revision and ground-truth revision
  are pinned independently. Answer-bearing eval/audit documents are excluded
  from the benchmark corpus. Historical live results are not rerun claims.

## Knowledge-base acceptance

Each PR links issue -> spec/plan -> implementation -> tests/evidence -> current
status/roadmap. Follow DOCS/standards/okf-documentation.md: typed frontmatter
for knowledge-bearing DOCS, standard Markdown links, related/supersedes links
where appropriate. Update DOCS/index.md/audit index routing; keep DOCS/status.md
as the evolving current state. DOCS/log.md records new decisions/structural
changes, not every code commit. Preserve dated audits as historical evidence.

## Out of scope

The blue-star product work remains deferred: general agentic retrieval,
ORIENT/TRACE/IMPACT expansion, OCR modernization, new embedding/reranker defaults,
and unrelated UI/factory cleanup. Necessary correctness changes to shared
contracts remain in scope even when they touch multiple services.
