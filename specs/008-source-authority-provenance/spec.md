# Feature Specification: Source Authority / Subject / Provenance Model (Stage B, contract)

**Feature Branch**: `docs/199-source-authority-provenance-adr`

**Created**: 2026-09-19

**Status**: Draft

**Tracking Issue**: #199

**Roadmap Context**: Phase 6, blue-star tranche priority 4 of 13
(`DOCS/audit/07-Roadmap.md`). Stage B of the reordered sequence in the
[Phase 6 handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md):
#200 mechanical sufficiency shipped first (specs/007, Stage A0-A5,
merged PRs #225-#229), #199 provenance second, then a #200 Stage C
follow-up combining both.

**Input**: User description: "#200 mechanical sufficiency → #199
authority/subject/provenance → #200 authority-aware sufficiency; get it
going" (owner request, 2026-09-19, continued from the Stage A session).
This spec covers Stage B's **B0 slice only**: the contract
([ADR-053](/DOCS/adr/ADR-053-source-authority-provenance-model.md)) and
this spec skeleton. B1 (migration/producers/persistence), B2 (transport
to context/manifest), and B3 (measured rollout) are follow-up slices
under the same issue, not implemented by this spec.

## Scenarios & Testing *(mandatory)*

### Scenario 1 - Role/subject classification distinguishes fixture from real subject (Priority: P1)

Given an ingested repository containing both its own implementation and
an embedded example/fixture describing an unrelated system, a caller
asking about the *selected repository* must not receive the fixture's
content as if it described the repository itself, while a caller
explicitly asking about the fixture/example must still be able to reach
it.

**Why this priority**: This is the concrete failure mode issue #199 and
the architecture audit name directly (mixed-example/fixture
contamination) and the one Stage C's acceptance test targets first.

**Independent Test**: Ingest a fixture repo containing one real
implementation file and one `fixtures/`-scoped file whose content
describes a different, unrelated project. Query both the default
(selected-repo) subject and an explicit fixture-scoped query; assert
each reads the correct `role`/`subject` classification via the graph/
vector metadata APIs.

**Acceptance Scenarios**:

1. **Given** a file under a conventional fixture/example path
   describing an unrelated system, **When** classified, **Then**
   `subject=embedded_subject` with a recorded basis, never
   `selected_repository`.
2. **Given** the same file, **When** a caller's request explicitly
   targets the embedded subject, **Then** it is still reachable and
   classified consistently (not filtered out).
3. **Given** a real implementation file with no subject-overriding
   signal, **When** classified, **Then** `subject=selected_repository`.

---

### Scenario 2 - Declared validity is exposed, not verified as true (Priority: P2)

Given an ADR or design doc whose own frontmatter declares
`status: superseded` or `status: proposed`, the classification records
that declared status without asserting it reflects current
implementation truth.

**Why this priority**: Prevents Stage C from silently treating "this
doc says it's current" as "this doc is verified correct" — a
distinction the handoff repeats explicitly (`distinguish declared status
from verified implementation truth`).

**Independent Test**: Classify a fixture doc with `status: superseded`
frontmatter and one with no `status` field at all; assert the first
reads `validity.declared_status=superseded` and the second reads
`validity=unknown`, and neither classification asserts correctness.

**Acceptance Scenarios**:

1. **Given** a doc with declared `status: superseded`, **Then**
   `validity.declared_status == "superseded"`.
2. **Given** a doc with no declared status, **Then**
   `validity.declared_status` is `unknown`, not defaulted to `current`.

---

### Scenario 3 - Unchanged bytes with a bumped classifier version get reclassified without re-embedding (Priority: P2)

Given incremental ingestion reuses an unchanged file's existing
embedding, and the provenance classifier's rule version has changed
since it was last classified, the node's provenance must be
recomputed and re-persisted even though its embedding is reused.

**Why this priority**: This is the exact incremental-reuse trap the
handoff calls out (`unchanged bytes do not imply unchanged
classification when policy version ... changes`) and the kind of defect
that only shows up in an incremental-vs-full-rebuild equivalence test,
per Constitution Principle I.

**Independent Test**: Ingest a fixture repo fully under classifier
version N. Bump the classifier version constant. Re-run incremental
ingestion with no file changes. Assert the affected nodes' `provenance.
classification.classifier_version` updated to N+1 while their
`content_hash`/embedding stayed identical (no re-embedding work done).

**Acceptance Scenarios**:

1. **Given** an unchanged file and a bumped classifier version,
   **When** incremental ingestion runs, **Then** provenance updates and
   the embedding is not recomputed.
2. **Given** an unchanged file and an unchanged classifier version,
   **When** incremental ingestion runs, **Then** neither provenance nor
   embedding changes (idempotent).

---

### Edge Cases

- A Markdown section with genuinely mixed content (partly implementation
  reference, partly design rationale) must classify `role=unknown_mixed`,
  never guessed from its parent directory alone, unless a real
  subsection/span boundary is available (ADR-053's source-span caveat).
- A generated summary whose input artifact IDs are not resolvable
  (e.g. the input was deleted) must classify `derivation.status=
  unsupported`, not silently drop the derivation facet.
- A repo ingested before this feature exists (`provenance IS NULL`) must
  read as all-`unknown` facets through every consumer, not crash or
  default to some interpretation.

## Non-Goals

- No composite authority score or ranking (ADR-053).
- No migration, producer implementation, or actual persistence in this
  spec — that is B1, a separate PR/spec addendum once B0's contract is
  reviewed.
- No transport into the actual LLM-facing context/manifest — that is
  B2.
- No consumption by Stage C's authority-aware sufficiency policy — that
  is the `#200` follow-up, explicitly sequenced after B2/B3's measured
  rollout per the handoff.
- No new semantic chunk-splitting work (ADR-053 non-goals).
- No LLM call anywhere in classification (Constitution Principle I).

## Governing References

- Constitution: `.specify/memory/constitution.md` (Principle I: no LLM
  in ingestion, incremental-equivalence invariant; Principle II: DB
  boundaries; Principle VII: reference ADRs, don't restate).
- ADR: [ADR-053](/DOCS/adr/ADR-053-source-authority-provenance-model.md)
  (this spec's contract — read it first; this spec does not restate its
  facet definitions).
- ADR-030 (unified artifact graph), ADR-031 (canonical identity), ADR-045
  (hybrid retrieval / DB boundary), ADR-051 (generation-aware graph
  cache) — existing invariants this model must not violate.
- Handoff: `DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md`
  (Stage B section — incremental rollout steps, acceptance/PR slices).
- Tracking issue: #199. Related, not duplicated: #180 (ingestion
  source-revision provenance), #181 (evaluation three-revision
  provenance), #196 (incremental ingestion, owns snapshot-lineage
  mechanics this model's Origin facet points at).

**Known conflicts**: None identified yet — B0 has not been implemented
against real code, so no conflict with current behavior has been found
to surface. Any conflict discovered during B1 must be recorded here or
in ADR-053, not silently resolved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST classify every `DocumentNode` into the
  five ADR-053 facets (origin, role, subject, derivation, validity),
  each independently `unknown`/`unknown_mixed`-capable, never a single
  composite score.
- **FR-002**: Classification MUST be deterministic and rule-based; no
  LLM call may occur in the ingestion path to produce it.
- **FR-003**: An artifact's selected-repository binding MUST come from
  the request's `repo_id`, not from text found inside any artifact;
  an artifact may only be classified `embedded_subject`, with a
  recorded basis, never silently promoted to redefine the default.
- **FR-004**: Old rows (pre-dating this feature) MUST decode as
  `provenance = null` and every consuming facet read MUST treat that as
  `unknown`, not error or silently default.
- **FR-005**: Incremental ingestion MUST recompute (not skip)
  classification when the classifier/rule version changes, even when
  the underlying bytes and embedding are unchanged and reused.
- **FR-006**: Validity classification MUST record only the artifact's
  own declared status (e.g. frontmatter), never an inference about
  whether that declaration is currently true.
- **FR-007**: `DocumentNode`'s existing Origin-facet fields (`repo_id`,
  `canonical_id`, `relative_path`, `source`, `ingestion_id`, `doc_type`,
  `content_hash`) MUST be reused, not duplicated, inside the new
  provenance representation.

### Key Entities

- **Provenance record**: one per `DocumentNode` (or narrower span, when
  a real boundary is known) — the five ADR-053 facets plus a
  classification envelope (schema/classifier version, rule/basis,
  scope, uncertainty).
- **Classification rule set**: versioned, deterministic, path/frontmatter/
  structural-fact-based; a version bump is itself a recorded, auditable
  event (exact storage mechanism decided in B1).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a real ingested repository with at least one fixture/
  example artifact, its subject classification correctly separates
  `selected_repository` from `embedded_subject` evidence (Scenario 1),
  verified by an integration test against real Postgres.
- **SC-002**: A forced-full ingestion and an incremental re-ingestion of
  the same unchanged corpus under the same classifier version produce
  byte-identical provenance for every node (idempotence), and a
  classifier-version bump with unchanged bytes updates provenance
  without triggering re-embedding (Scenario 3).
- **SC-003**: Zero LLM/HTTP calls to `llm_service` occur during
  classification, verified by test-double call-count assertions.

## Evaluation Evidence

**Evaluation Required**: No, for B0/B1/B2 (structural transport, not a
retrieval/ranking/generation behavior change — Constitution Principle
III/VIII). **Yes**, once Stage C (the `#200` follow-up) consumes
provenance to change sufficiency outcomes — that stage's spec carries
its own evaluation section per the handoff's frozen paired-evaluation
methodology.

## Assumptions

- B1's exact JSON key names/migration shape are implementation detail
  deferred to that slice's own PR (per Constitution Principle VII, this
  spec references ADR-053's facets rather than fixing field names here).
- The classifier rule set for `role`/`subject` initially covers path-
  convention and existing `doc_type`/structural-inventory signals only;
  broader heuristics are evaluated incrementally, not assumed complete
  at B1.
- Stage B's acceptance/PR slices (B0-B3) and required test cases mirror
  the handoff's Stage B section; this spec's scenarios are a subset
  (the three most load-bearing), not the full case list — B1's spec
  addendum expands them alongside real implementation.
