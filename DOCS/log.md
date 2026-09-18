# Documentation Log

Reverse-chronological record of documentation-standard-relevant changes
across `DOCS/` — new ADRs, policy adoptions, and structural migrations.
Routine content edits are tracked by `git log`, not here; this file is
for changes that affect how the knowledge base itself is organized or
governed.

## 2026-09-18

Accepted [ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)
after WP-R4/#167 merged to main via PR #192. Added
[the quality evaluation record](/DOCS/test_results/2026-09-18-wp-r4-quality-evaluation.md):
the frozen 8-question set run against both WP-R4 and the legacy runtime,
plus a clean-context control, found WP-R4 net positive with no blocking
findings — resolved after switching the eval harness from a local CPU
Ollama (which failed four times on real-PostgreSQL crashes, a
misconfigured service URL, embedding timeouts, and a memory-pressure
process kill) to the Tailscale-reachable production Ollama.

Added a new Phase 6 roadmap tranche to
[`07-Roadmap.md`](/DOCS/audit/07-Roadmap.md) (13 prioritized issues,
#196-#208) superseding `spec.md`'s old "blue-star work remains deferred"
placeholder.

Consolidated project-status tracking to a single location: archived the
top-level `status/` directory (10 dated pre-rename snapshot files,
untouched since the repository's first commit) into
`docs-archive/status-snapshots-2025-2026/`. `DOCS/status.md` was already
documented as the single continuously-updated status doc (see the
2026-09-14 entry below); this closes the gap between that stated intent
and the file tree. Updated `CLAUDE.md`'s documentation map and
`DOCS/index.md`'s Status/Historical sections accordingly.

## 2026-09-17

Added proposed [ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)
and [WP-R4 verification record](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md),
linking passage/context contracts to issue #167 and its uncompleted quality gates.



Added proposed [ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)
for WP-R5's narrowed scope (#168): keys `rag_orchestrator`'s graph cache on
`(repo_id, generation_id)` via a new cheap `GET /v1/repos/{repo_id}/generation`
endpoint, LRU-bounds it, and records explicit non-goals (no vector-store
generation filtering, no live two-service HTTP round-trip test). Linked to
[freshness.md](/specs/005-production-correctness/issues/freshness.md).
Merge/CI validation pending.

Split WP-R5/#168 into three separately-tracked issues after reconstructing
it post-R3: #168 itself narrowed to generation-aware query/graph-cache
freshness only, ingestion source-revision provenance (Git ref/resolved
SHA/config fingerprint) moved to new issue #180, and evaluation
three-revision (runtime/corpus/ground-truth) provenance moved to new issue
#181. The original #168 text bundled all three under one acceptance list;
they are different correctness domains with different owners and don't
belong in one implementation unit. `specs/005-production-correctness/issues/
freshness.md` and `spec.md`'s tracking table updated to match. No
implementation for any of the three yet.

Added proposed [ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)
for WP-R3 repository rebuild/delete lifecycle consistency (#166), linked to
the programme's [acceptance and rollout tasks](/specs/005-production-correctness/issues/lifecycle.md).
It persists `repo_id` on `ingestion_requests` independently of graph rows,
adds a repo-scope mutation lock, and corrects generation resolution to match
`persist_graph`'s actual atomic-replace behavior rather than assuming a prior
generation stays servable during a rebuild. Merge/CI validation pending.

Accepted [ADR-049](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md) for
WP-R2 ingestion ownership/recovery (#161), linked to the programme's
[acceptance and rollout tasks](/specs/005-production-correctness/issues/recovery.md).
It distinguishes job ownership from R3 corpus consistency and records explicit
legacy-worker rollout requirements. Merged via PR #177 (`12cf75d`).

## 2026-09-14

Added [`DOCS/status.md`](/DOCS/status.md) — a new top-level, single,
continuously-updated status doc (language/codebase-graph support, RAG
quality results, known issues), distinct from the abandoned `status/`
dated-snapshot directory and from this file's own documentation-
structure-governance scope. Motivated by WP-L5 (issue #134) shipping:
`README.md` had accumulated ADR/issue/`WP-L*` references and status
prose that belonged in a dedicated doc instead, so those moved here and
`README.md` now links to it. `DOCS/index.md` updated with a `## Status`
entry pointing to it.

## 2026-09-13

Added `DOCS/patterns/` — a new top-level category for reusable,
framework-agnostic architecture patterns worth taking to other projects,
distinct from `DOCS/adr/`'s this-repo decision records. First entry:
[Three-Layer Model/Provider Configuration](/DOCS/patterns/three-layer-model-config-pattern.md),
extracted from WP-M6/WP-M7's dynamic model catalog + runtime model policy
work in `llm_service`
([LLM Provider Plan](/DOCS/audit/06-LLM-Provider-LiteLLM-Plan.md)).

## 2026-09-12

Promoted `DOCS/releases/` from a template-only folder to an explicit production
release-record bucket in `DOCS/index.md`. The first successful audited Docker
Compose production release is
[prod-2026-09-12](/DOCS/releases/2026-09-12-prod-release.md); the failed
`827c9cdc` promotion remains linked as part of the release audit trail.

## 2026-08-30

Adopted OKF v0.2 as the standing documentation standard. Added
`DOCS/standards/okf-documentation.md`; `CLAUDE.md` and `DOCS/index.md`
now point to it. New knowledge-bearing docs must comply going forward;
legacy docs migrate opportunistically on substantial edit, not in bulk.
See [issue #75](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/75) /
[PR #76](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/76).

## 2026-08-27

Retrofitted `DOCS/adr/` and added `DOCS/index.md` using the frontmatter
+ `[[wikilink]]` pattern `DOCS/audit/` had already independently
established, generalizing it into the repo's first cross-directory
documentation convention. See
[PR #63](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/63).
