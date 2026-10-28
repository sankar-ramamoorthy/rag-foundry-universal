---
title: "Documentation Index — rag-foundry-universal"
date: 2026-08-27
type: doc-index
status: complete
tags: [index, moc]
aliases: [Docs Index, DOCS MOC]
---

# Documentation Index

This routes to where the knowledge lives — it doesn't restate it. If a fact
here goes stale, fix the routing, not by copying content into this file.

## Status

[`DOCS/status.md`](/DOCS/status.md) is the single, continuously-updated
snapshot of what's currently shipped, in progress, and known-broken —
language/codebase-graph support, RAG quality evaluation results, and
known issues. `README.md` links here rather than embedding ADR/issue/PR
numbers itself. Not to be confused with `DOCS/log.md` (documentation-
structure governance) or the old top-level `status/` directory (an
abandoned dated-snapshot convention, archived 2026-09-18 — see
"Historical" below).

## Documentation Standard

[README accuracy policy](/DOCS/standards/readme-accuracy.md) requires product
descriptions to match implementation and validation, with development progress
kept in `DOCS/status.md`. The [PR review checklist](/.github/pull_request_template.md)
records the applicable accuracy and license checks.

New or substantially-edited docs follow
[the OKF documentation standard](/DOCS/standards/okf-documentation.md)
(frontmatter + linking conventions). [`DOCS/log.md`](/DOCS/log.md)
records documentation-standard-relevant history — new ADRs, policy
changes, structural migrations.

## Decisions

The [October 14 code-evidence experiment decisions](/DOCS/evaluations/2026-10-14-code-evidence-experiment-decisions.md)
record the authorized local scope, baseline metrics, fixed-byte constraints and
separate discovery, passage-coverage and context-allocation experiments following
the [LightRAG forensics](/DOCS/test_results/2026-10-13-lightrag-implementation-forensics.md).
The [E1 case manifest](/DOCS/evaluations/code-evidence-e1/README.md) is frozen;
the [completed baseline report](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)
records six captures, incomplete implementation evidence and a later full-graph
timeout during prototype control setup. Prototype quality remains unverified.
No production selection policy is adopted.
The [statement-level delivery contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)
(#276, **accepted and frozen** 2026-10-28; checksum recorded) specifies the experiment that the
[structural-context oracle](/DOCS/test_results/2026-10-28-e1-structural-context-feasibility.md)
makes worth testing, including the held-out case plan required by ADR-054.

`DOCS/adr/` — check each ADR's own `status` field before relying on it;
don't assume numeric order implies currency.

[ADR-049: ingestion ownership and recovery](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md)
records the accepted WP-R2 admission/recovery decision and its R3 boundaries.

[ADR-050: repository lifecycle consistency](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)
records the accepted WP-R3 repo-identity/generation-resolution/delete-lock
decision and its explicit non-goals (no zero-downtime staged publication).

[ADR-051: generation-aware graph cache](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)
records the accepted WP-R5 (narrowed #168) decision keying
`rag_orchestrator`'s graph cache on `(repo_id, generation_id)` with LRU
bounding, and its explicit non-goals (no vector-store generation filtering,
no live two-service HTTP round-trip test yet).

[ADR-053: source authority / subject / provenance model](/DOCS/adr/ADR-053-source-authority-provenance-model.md)
— **proposed**, not yet implemented — records the issue #199 (Phase 6
Stage B) contract: five orthogonal facets (origin/role/subject/
derivation/validity) plus a classification envelope, persisted as an
additive nullable JSON field on `DocumentNode`, no composite authority
score, no LLM calls in classification.

[ADR-054: evaluation dataset isolation and generalization](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)
— **accepted** — defines how development, regression, and held-out
repository evaluations are kept distinct before future retrieval tuning.

[ADR-055: node-text read endpoint](/DOCS/adr/ADR-055-node-text-read-endpoint.md)
— **accepted** (2026-10-28), not implemented — records that no ingestion_service endpoint
returns a node's original source text by canonical id and decides on one bounded,
generation-fenced, read-only `POST` endpoint, for the statement-level E1
experiment (#276). Accepting it authorizes no implementation by itself.

## Audit & Planning

The production-correctness programme
([WP-R1 through WP-R8](/specs/005-production-correctness/spec.md), with
[delivery plan](/specs/005-production-correctness/plan.md),
[execution handoff](/specs/005-production-correctness/HANDOFF.md), and
[September 16 audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md))
is substantially closed as of WP-R4/#167 (2026-09-18). The
[memory design review](/DOCS/audit/2026-09-16-bounded-ingestion-memory-design-review.md)
informs the amended [004 specification](/specs/004-bounded-ingestion-memory/spec.md).

The active next tranche is **Phase 6** in
[`07-Roadmap.md`](/DOCS/audit/07-Roadmap.md#phase-6--repository-document-and-coding-agent-intelligence) —
13 prioritized issues (#196-#208) covering incremental ingestion/snapshot
lineage, repository intelligence (ORIENT/TRACE/IMPACT), provenance/source
authority, and related foundation work, **reorganized 2026-10-12** under
R/A/D/E/O/P workstream labels (every issue number and shipped checkbox
preserved; see the roadmap for the full reconciliation). Items 1-3
(#196, #197, #198) and their fast-follows (#216, #220, #221) have
shipped. #200 Stage A (mechanical bounded evidence sufficiency, its own
internal A0-A5 stage labels — distinct from the roadmap's new `AG0`-`AG5`
coding-agent items) has shipped — see [status](/DOCS/status.md); its full
frozen live-evaluation gate remains open. Next is #199 (source authority /
subject / provenance, ADR-053 proposed, not yet implemented), then a #200
Stage C follow-up combining both. Separately, #254's normal-mode evidence-
delivery symptom is production-verified resolved (#257, PRs #258-#260);
#254 stays open for its overview-policy and historical seed-set questions
— see the [production verification record](/DOCS/test_results/2026-10-11-issue-254-257-production-verification.md).

Start at [[audit/00-Audit-Overview]] — the audit subtree's own index
(codebase findings, scalability/platform/LLM-provider plans, the roadmap,
and the RAG quality evaluation methodology).

[[audit/09-Retrieval-Technique-Decision-Gates]] — external retrieval/
generation ideas recorded as hypotheses with evidence-triggered decision
gates, not roadmap items; deliberately not linked from `07-Roadmap.md` or
`00-Audit-Overview.md`'s work-package index so an idea can't become
architecture just by being written down.

## Architecture Deep-Dives

`DOCS/architecture/` — diagrams and flow references (e.g. codebase ingestion
flow, repo query ASCII flow, extraction hierarchy model). Not yet
frontmatter-linked — planned follow-up.

## Deployment

`DOCS/deployment/` holds operational deployment guidance. Start with
[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)
for the manual production release procedure, provenance checks, validation,
and rollback rules. [Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md)
covers the operator-owned deployment boundary, the local/deployed execution
model, the four SHAs that can differ, and the limits of HTTP-based
verification.

`DOCS/releases/` holds production release records. Current release:
[prod-2026-09-12](/DOCS/releases/2026-09-12-prod-release.md), deployed from
`202d91b34ee18e21c1dbb625d72acf9b82bce16d`. The earlier
[827c9cdc failed promotion](/DOCS/releases/2026-09-12-827c9cdc-failed-promotion.md)
is retained as part of the audit trail.

## Proposals

The [Phase 6 Claude handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md)
plans #200 mechanical sufficiency, then #199 authority/subject/provenance, then
authority-aware sufficiency checks. Its
[code findings](/DOCS/notes/2026-09-19-phase-6-sufficiency-findings.md)
record the inspected baseline and implementation seams. This is proposed work,
not a shipped capability.

[The roadmap-reorientation proposal](/DOCS/proposals/2026-10-11-roadmap-reorientation-agent-ready-intelligence.md)
(`status: integrated`, 2026-10-12) — reconciled and integrated into
`07-Roadmap.md`'s Phase 6 (above); kept as the historical rationale record,
not a live planning document.

`DOCS/proposals/` — process/tooling proposals under discussion, not yet
binding: [[proposals/sdd-spec-kit-adoption]],
[[proposals/lean-instruction-routing-layer]] (before Phase 3).

## Evidence / Test Results

The [graph export benchmark](/DOCS/test_results/2026-10-28-graph-export-benchmark.md) (issue #273) records how `GET /v1/graph/repos/{repo_id}` behaves under 1/2/4 simultaneous exports before and after PR #272 (latency, `/version` responsiveness, memory, response equivalence). Local and synthetic; it does not explain the E1 control-replay timeout (#270).

[WP-R4 evidence delivery](/DOCS/test_results/2026-09-17-wp-r4-evidence-delivery.md)
tracks local mechanics verification and outstanding quality gates;
[ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md) records the accepted contract.

Issue #240's [pinned overview comparison](/DOCS/test_results/2026-10-03-issue-240-frozen-quality-comparison.md)
records the failed quality gate, raw traces, and next experiment. Its
[restart handoff](/DOCS/notes/20261003-issue-240-restart-handoff.md) preserves
the branch, production, and publication state.
The [October 8 HTTP structured-answer comparison](/DOCS/test_results/2026-10-08-issue-240-http-structured-comparison.md)
records the later matched 11-request result and its remaining merge gate.

Issue #257/#254's [production verification](/DOCS/test_results/2026-10-11-issue-254-257-production-verification.md)
confirms two merged retrieval-pipeline fixes (structural discovery past a
one-hop expansion limit; context-allocation priority for explicitly-named
methods) against the live deployed stack — the authoritative method is
now discovered, fetched, and cited in the generated answer for normal-
mode queries. The [October 12 overview control comparison](/DOCS/test_results/2026-10-12-issue-254-overview-control-comparison.md)
records 30 matched pinned requests: overview correctness improves, but
claim selection removes explicit-path method evidence and produces false
code-absence answers. This confirmed regression and the historical seed-set
discrepancy remain open, separate work under #254.
The [local policy candidate](/DOCS/test_results/2026-10-12-issue-254-policy-candidate.md)
preserves R1 implementation/CLI evidence and all eight overview passes in
30 additional matched requests, but its answer gate still fails. It remains
unmerged and undeployed; held-out #243 evaluation is not claimed complete.
The [agent-loop completeness diagnosis](/DOCS/test_results/2026-10-12-issue-254-loop-evidence-completeness.md)
records two unchanged observed replays and the actual generation payload:
provider/feedback passages are not fetched, exact `main`/full CLI passages
lose to byte capacity, and equivalent file-level startup/CLI handoffs survive.
It corrects the candidate report's `main` chunk-count attribution and keeps
incomplete delivery separate from incorrect synthesis and independent C1 grounding.
The [fixed-cap complete-evidence experiment](/DOCS/test_results/2026-10-12-issue-254-complete-evidence-experiment.md)
then fits five normal-flow transition witnesses in 4024 evidence bytes and
compares three matched pairs with the unchanged captured candidate context.
Memory-input/feedback explanation improves to 3/3, while full factual/attribution
acceptance remains 0/3. This is a manual source-excerpt oracle with state-dependency
limits, not an implemented selector or a completed #243 evaluation.
The [separate automatic-coverage and frozen-evidence grounding tests](/DOCS/test_results/2026-10-12-issue-254-separated-investigations.md)
find that a 3952-byte offline AST selection still misses feedback/startup and
branch relationships. A six-call explicit answer-contract comparison passes
0/3 full-loop gates in each arm and gives no scored improvement. No runtime
policy is changed; state dependencies remain unresolved and #243 is deferred.


`DOCS/test_results/` — benchmark and verification records tied to specific
audit findings.

## Evaluations

The [local D0 attempt](/DOCS/test_results/2026-10-12-document-rag-local-ingestion-blocker.md)
resolves Docker isolation but finds Markdown upload's IR/legacy-consumer mismatch:
HTTP admission followed by terminal failure, with zero answer requests. Ingestion
repair precedes baseline execution, native formats and MCP.

The [D0 post-deployment preflight](/DOCS/test_results/2026-10-12-document-rag-post-deploy-preflight.md)
verifies frozen source bytes and a ready index, but repository fixtures are tagged
as code and excluded by the document path. The baseline awaits isolated document
uploads; it has no answer-quality score.

The current focus is the [D0 document-RAG baseline](/DOCS/evaluations/2026-10-12-document-rag-baseline.md),
with twelve frozen synthetic development cases. Corpus isolation is now available,
but Markdown upload fails at the IR consumer; no document quality score is claimed.
[#254 is deliberately deferred](/DOCS/notes/2026-10-12-issue-254-deferred.md)
with the failed acceptance gate open, candidate preserved, C1 separate and #243
held-out evaluation untouched.

`DOCS/evaluations/` — pre-registered evaluation question/candidate sets
(defined before the experiment runs, distinct from `DOCS/test_results/`'s
post-hoc verification evidence):
[[evaluations/2026-09-07-evidence-survival-question-set]].
The [issue #240 frozen overview set](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)
defines the current repository-overview comparison and controls.

## Patterns

`DOCS/patterns/` — reusable, framework-agnostic architecture patterns
worth taking to other projects (distinct from `DOCS/adr/`'s
this-repo decision records):
[Three-Layer Model/Provider Configuration](/DOCS/patterns/three-layer-model-config-pattern.md).

## Notes

`DOCS/notes/` — ad hoc working notes.

## Historical (non-authoritative)

`../docs-archive/` — do not treat as current source of truth, including
its `status-snapshots-2025-2026/` subdirectory (dated pre-rename project
notes, formerly a top-level `status/` directory — consolidated 2026-09-18
since it had been untouched since the repository's first commit and
duplicated `DOCS/status.md`'s purpose).
[[../README_VISION|README_VISION.md]] — March 2026 external vision/design-intent
writeup, now annotated (2026-08-27) distinguishing what shipped from what's
still only envisioned; not a current-state reference.

For **current** project status, see [`status.md`](/DOCS/status.md) above
this section — it's the single, continuously-updated status document;
nothing else in the repo should be treated as an alternative to it.
