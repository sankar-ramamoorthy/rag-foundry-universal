---
title: "Stage C: authority-aware sufficiency -- live verification"
date: 2026-09-19
type: test-results
status: complete
tags: [phase-6, evidence, sufficiency, provenance, issue-199, issue-200, stage-c]
related:
  - "[ADR-053](/DOCS/adr/ADR-053-source-authority-provenance-model.md)"
  - "[Spec 007](/specs/007-bounded-evidence-sufficiency/spec.md)"
  - "[Stage B3 findings](/DOCS/test_results/2026-09-19-stage-b3-provenance-shadow-diagnostics.md)"
  - "[Status](/DOCS/status.md)"
---

# Stage C: authority-aware sufficiency

## What this is

The `#200` follow-up the Phase 6 handoff calls Stage C: TRACE/IMPACT
evidence, already mechanically sufficient (Stage A), gets an
*additional*, separately-visible authority-qualified status, using
Stage B's persisted/transported provenance and Stage B3's already-
established, deterministic, query-purpose-aware rules
(`provenance_diagnostics.py`). No new policy was invented for Stage C:
`evidence_authority.py` reuses those exact rules.

**Prerequisite closed first**: Stage B2 only transported provenance
into `/v1/rag`'s vector-retrieval path (`RetrievedChunk`/
`final_context_manifest`). TRACE/IMPACT/ORIENT consume a *different*,
in-memory graph (`CodebaseGraph`/`Node`, loaded via `GET /v1/graph/
repos/{repo_id}`), which had no provenance reachability at all. Closed
by extending `GraphNode` (ingestion_service's graph API) and `Node`
(rag_orchestrator's in-memory graph) with the same `provenance` field,
mirroring B2's transport pattern exactly -- no new I/O in the workflow
layer, since the graph is already loaded once per request.

## Scope

TRACE and IMPACT only, opt-in via `claim_type` on `POST /v1/repos/
{repo_id}/evidence` (same four claim types Stage B3 already defined:
`implemented_behavior`, `design_rationale`, `test_contract`,
`repository_overview`). ORIENT explicitly rejects `claim_type` (400) --
its facets are inventory-level aggregates, not individually-sourced
artifacts this provenance model attaches to; an ORIENT authority check
needs its own design, not attempted here.

Never gates, filters, or replaces Stage A's mechanical assessment --
`assessment` and `authority` are always both present (or `authority`
is `null` when `claim_type` was omitted), never one instead of the
other.

## Live verification against the real `shared/` corpus

Using `repo_id=3ab62236-...` (post the `role-subject-v2` classifier
fix, so `smoke_repo/` correctly classifies `example_fixture`/
`embedded_subject`), all calls through the real HTTP endpoint:

| Case | `start` | `claim_type` | mechanical `assessment.status` | `authority.status` |
|---|---|---|---|---|
| Handoff acceptance case 1 | `smoke_repo/dogs.py#Dog` (a real fixture) | `implemented_behavior` | `satisfied` | **`authority_unqualified`** (`embedded_subject_offered_as_implementation`, `non_implementation_role_offered_as_implementation`) |
| Control: real implementation | `chunkers/selector.py#ChunkerFactory` | `implemented_behavior` | `satisfied` | `authority_qualified` |
| Zero contamination | same as above | *(omitted)* | `satisfied` | `null` (no computation ran) |
| Handoff acceptance case 2 | `smoke_repo/dogs.py#Dog` (same fixture) | `test_contract` (a claim type appropriate for inspecting a fixture) | `satisfied` | **`authority_qualified`** -- explicit example-appropriate claim still passes |

This is exactly the handoff's Stage C acceptance bar: *"the same
fixture must pass Stage A mechanical coverage but fail Stage C
authority-qualified sufficiency when all support concerns an embedded
example; a valid explicitly requested example must still pass."* Both
halves confirmed live, not just in the 9 pure unit tests
(`test_evidence_authority.py`) that cover the same cases plus edge
cases (missing provenance -> `authority_unknown`, not `unqualified`;
superseded ADR validity; a real concern outranking `unknown_provenance`
in the same batch; Stage C never mutating Stage A's own result object).

## What this does and does not establish

**Established**: the authority layer works correctly end-to-end --
graph-transport prerequisite, pure assessment, HTTP wiring, and the
exact two-sided acceptance criterion the handoff specifies -- against
real ingested data, not synthetic fixtures alone.

**Not established**: `design_rationale` and `test_contract` still have
no rules by design (Stage B3's "unjustified rules are themselves the
disallowed policy" bar) -- a design/eval/summary-offered-as-current-
implementation check (handoff's "Claim-relative role fit" row) and a
"declared validity" check against a real superseded ADR in a live
corpus were only unit-tested, not live-verified (this local corpus has
no `design`-role content). Snapshot consistency, derivation support,
and required-context-dropped-by-budget (three more rows in the
handoff's Stage C obligations table) are not implemented at all --
snapshot consistency is already covered structurally by the existing
generation fence (Stage A2), derivation support has no live producer to
check yet (no generated-summary path exists), and required-context is
`/v1/rag`'s manifest concern, not TRACE/IMPACT's.

## Follow-up finding: incremental ingestion silently dropped vector-level provenance

After this document's initial verification, the owner deployed the
Stage C build to production and ran a **second** ingestion of the full
self-repo corpus -- this one incremental (`is_incremental: true`,
confirmed via `GET /v1/repos/{repo_id}/generation`), not a full rebuild.
Querying `/v1/rag` for real content afterward showed every manifest
entry reading `unknown_provenance`, including files independently
confirmed (via direct `GET /v1/graph/repos/{repo_id}/nodes/lookup`
calls) to have correct, current `role-subject-v2` provenance on their
`DocumentNode` row.

**Root cause**: Stage B1's `persist_graph` recomputes `DocumentNode.
provenance` on every upsert, including a reused row -- that invariant
held. But Stage B2's chunk-level provenance is only ever set inside
`_chunk_and_buffer_node`, the re-embed path. An incremental generation
that reuses an unchanged file's existing vectors (`_retag_reused_
vectors`, previously just an `ingestion_id` retag) never touched that
vector's `source_metadata` at all -- so `/v1/rag`, which reads
chunk-level metadata, not the graph, silently lost provenance for
anything the generation didn't literally re-embed. TRACE/IMPACT/Stage C
(reading the graph) were unaffected; only the vector-retrieval path
was stale. This is exactly the split described in the follow-up
directive: mechanical classification was generation-aware at the graph
layer, but provenance freshness on the vector layer was accidentally
tied to embedding regeneration.

**Fixed**: `_retag_reused_vectors` now recomputes each reused node's
provenance (same `classify_node` call, same inputs persist_graph uses)
and passes it to a widened `retag_ingestion_id` (`vector_store_service`
gained a narrowly-scoped `provenance_by_document_id` parameter on the
existing `/v1/vectors/retag` endpoint -- no new endpoint), which patches
`source_metadata.provenance` via `jsonb_set` in the same `UPDATE` that
already retags `ingestion_id`, preserving every other `source_metadata`
key. No embedding call, no row insert -- one bulk `UPDATE` per batch,
same as before.

Verified end-to-end via a new real-Postgres-plus-real-`vector_store_
service` integration test
(`test_reused_vector_provenance_refreshed_without_reembed`): an
unchanged file's provenance is refreshed to a simulated classifier-
version bump's output, the file is confirmed *not* re-embedded, and
every other `source_metadata` key (e.g. `canonical_id`) survives
unchanged.

## Recommendation

Keep fully opt-in. This is a real, working authority layer for the two
rules Stage B3 already validated (subject fit, claim-relative role
fit for `implemented_behavior`/`repository_overview`, plus declared
validity), live-verified against real fixture content, and now correct
under incremental ingestion as well as full rebuilds. The remaining
Stage C obligation-table rows are legitimate future increments, not
blockers to using what exists today.
