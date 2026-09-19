---
title: "ADR-053: Source authority / subject / provenance model"
date: 2026-09-19
type: adr
status: proposed
tags: [provenance, authority, evidence, issue-199]
related:
  - "[Issue #199](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/199)"
  - "[Phase 6 handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md)"
  - "[ADR-031 canonical identity](/DOCS/adr/ADR-031-canonical-identity-model.md)"
  - "[ADR-030 unified artifact graph](/DOCS/adr/ADR-030-unified-artifact-graph.md)"
  - "[ADR-045 hybrid retrieval](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md)"
  - "[ADR-052 evidence delivery](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)"
  - "[Architecture audit](/DOCS/audit/2026-09-07-repository-intelligence-architecture-audit.md)"
---

# Source authority / subject / provenance model

Issue [#199](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/199).
**Status: proposed** — this ADR records a design decision for Stage B
implementation; no code, migration, or producer described below is
implemented yet. It defines the contract Stage B (`B0`) fixes before
`B1` (migration/persistence), `B2` (transport to context/manifest), and
`B3` (measured rollout) proceed, per the
[Phase 6 handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md).

## Problem

The system cannot currently distinguish, for a given piece of retrieved
evidence: implementation vs. design/ADR material; current vs. archived;
test/fixture vs. production; the repository itself vs. an example
described inside it; a deterministic source fact vs. an LLM-generated
summary; or which exact ingested snapshot it came from. Issue #200
Stage A's mechanical sufficiency (ADR: none yet, see spec
[007](/specs/007-bounded-evidence-sufficiency/spec.md)) already proves a
TRACE/IMPACT/ORIENT obligation is *mechanically* satisfied; it cannot
tell a caller whether the satisfying evidence is *authoritative* for the
claim being made. That gap is what this model closes, deferred to a
Stage C `#200` follow-up that consumes it (`Do not make #199 a
prerequisite for the first useful #200 release` — already honored: A0-A5
shipped mechanical-only, see `DOCS/status.md`).

## Decision

Five orthogonal facets, no composite "authority score":

| Facet | Meaning | Values (initial) |
|---|---|---|
| Origin | where the artifact physically came from | repo_id, canonical_id, relative_path, source span (optional), serving ingestion_id, file/commit hash when available |
| Role | what kind of artifact this is | `implementation`, `configuration`, `test`, `design`, `documentation`, `example_fixture`, `evaluation`, `historical`, `unknown_mixed` |
| Subject | what the artifact's content is actually *about* | `selected_repository`, `embedded_subject` (with a basis pointer), `external_subject`, `unknown_mixed` |
| Derivation | how the text/fact was produced | `source` (byte-identical to ingested input), `deterministic_projection` (e.g. a structural fact), `generated_summary` (with input artifact/fact IDs + transform version, when known) |
| Validity | is this artifact declared current | declared status/supersession if the source states one (e.g. an ADR's own `status:` frontmatter); explicitly distinguished from *verified* implementation truth, which this model never claims |

A sixth, non-domain field, **Classification**, records how the above
were computed: `schema_version`, `classifier_version`, the rule/basis
used, its scope (artifact/section/span), and an explicit uncertainty
marker. This is what lets an unclassified/legacy row read as `unknown`
rather than silently defaulting to some interpretation.

Authority is **relative to the claim being checked**, never a global
number: "is this evidence a good source for claim X" depends on X's
claim type (implemented behavior vs. design rationale vs. test
contract vs. repository overview), which is supplied by the caller
(Stage C), not inferred here.

### Persistence

A versioned, nullable JSON `provenance` column on the existing
`DocumentNode` table (`shared/models/document_node.py`), populated
additively — **no new per-role artifact table**, consistent with the
existing "everything lives in `DocumentNode`/`DocumentRelationship`"
invariant (`CLAUDE.md`, ADR-030). `DocumentNode` already carries several
Origin-facet fields directly (`repo_id`, `canonical_id`, `relative_path`,
`source`, `ingestion_id`, `doc_type`, `content_hash`) — those are reused
as-is via the classification's `origin.basis`, not duplicated inside the
JSON blob. Only Role/Subject/Derivation/Validity/Classification are new,
and only as JSON initially; narrowly typed/indexed columns are added
later, only where a real query need justifies the index cost (e.g. if
Stage C needs to filter by `role` at scale, that becomes its own
follow-up migration, not assumed here).

Old rows decode as `provenance = null` → every facet reads
`unknown`/`unknown_mixed`. No backfill invents historical facts; a row
either gets provenance from re-ingestion or stays explicitly unknown
(handoff: "never invent historical subject, derivation or snapshot
facts").

### Classification is deterministic, not LLM-based

Per Constitution Principle I ("No LLM calls are permitted anywhere in
the ingestion path"), every facet is computed from auditable, versioned
rules over already-known signals: file path conventions (e.g. `tests/`,
`docs-archive/`), existing `doc_type`, structural inventory facts
(#197), and declared frontmatter (an ADR's own `status:` field, read as
declared, never verified). A rule set change bumps
`classification.classifier_version`; Stage B1's incremental-ingestion
handling must recompute classification (not re-embed) when only the
rule version changed and the underlying bytes did not (see
`DOCS/adr/ADR-030-unified-artifact-graph.md` and the incremental
equivalence invariant in `.specify/memory/constitution.md` Principle I).

### Selected-repo binding and embedded-subject override

The request's `repo_id` binds the **default** subject
(`selected_repository`). Free text inside an artifact describing another
system (a fixture, an example README) cannot silently redefine that
default; it can only be classified `embedded_subject` with an explicit
basis (e.g. "this file lives under a `fixtures/` or `examples/`
directory" or "this Markdown section's own heading names an unrelated
project"), and a caller can still explicitly ask a Stage C query to
target that embedded subject (handoff: "Explicit fixture/example
questions can select that embedded subject and should still work").

### Snapshot ties to existing generation lineage

The Snapshot dimension named in issue #199 is **not** a new mechanism:
it is `DocumentNode.ingestion_id` plus the existing generation-lineage
machinery (`IngestionRequest.parent_generation_id`,
`is_incremental`, `commit_sha` — see ADR-030/ADR-051, and issues #180/#181
for the narrower source-revision and eval-revision provenance slices
already filed). This ADR's Origin facet points at that lineage rather
than re-deriving it. A missing/dirty commit SHA stays `unknown`; it is
never filled from the evaluator's own local checkout.

## Non-goals

- No composite authority score, ranking, or filter — Stage C consumers
  read facets explicitly.
- No new artifact/role-specific table.
- No LLM call anywhere in classification.
- No claim that a declared `status:` (e.g. an ADR marked "accepted")
  reflects current, verified implementation truth — Validity records
  what the source *declares*, not what is true.
- No semantic/new chunk-boundary work — classification starts at
  existing artifact/section/chunk boundaries; splitting is a separate,
  not-yet-justified change (handoff: "New semantic chunk splitting is
  separately evaluated, not an implicit dependency").
- Full transport to the LLM prompt/manifest (B2), migration/producer
  implementation (B1), and measured rollout (B3) are follow-up PRs under
  this same ADR, not decided here beyond the shape above.

## Consequences

- `shared/models/document_node.py` gains one nullable JSON column
  (Alembic migration, `ingestion_service`-owned per the DB boundary,
  ADR-045) — additive, no existing field removed or renamed.
- Every ingestion-time producer (Python/TS/JS/Rust/Java extractors,
  Markdown/document parser, ORIENT's structural inventory) gains an
  optional classification step; orchestrator/retrieval consumers stay
  DB-free and receive provenance only via the existing graph/vector
  APIs (ADR-045 boundary preserved).
- Incremental ingestion (#196) must be re-verified for provenance
  round-trip equivalence: forced-full vs. incremental reuse, including a
  classifier-version bump with unchanged bytes, per the acceptance
  cases listed in the Phase 6 handoff's Stage B section.

## Open questions for B1

- Exact JSON key names/nesting (kept out of this ADR per Constitution
  Principle VII — implementation detail, not an architectural decision).
- Whether `origin.source_span` is representable at all before any
  semantic sub-chunking work lands, or must stay artifact-level only
  for the initial version.
