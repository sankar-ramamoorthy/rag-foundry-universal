# Feature Specification: Bounded Evidence-Sufficiency Loop (Stage A, mechanical)

**Feature Branch**: `feature/200-bounded-evidence-sufficiency`

**Created**: 2026-09-19

**Status**: Draft

**Tracking Issue**: #200

**Roadmap Context**: Phase 6, blue-star tranche priority 5 of 13
(`DOCS/audit/07-Roadmap.md`). Executed as Stage A of the reordered
sequence in the
[Phase 6 handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md):
#200 mechanical sufficiency first, #199 authority/subject/provenance
second, then a #200 follow-up combining both. This spec covers Stage A
only (mechanical signals; no authority/provenance input, which does not
exist yet).

**Input**: User description: "#200 mechanical sufficiency → #199
authority/subject/provenance → #200 authority-aware sufficiency; check
issues, get it going, implement" (owner request, 2026-09-19). This slice
implements A0 (this spec + fixtures) and A1 (pure assessor +
`trace_impact.py` limit semantics) of the handoff's implementation-slice
table. A2 (controller/generation fence), A3 (API), A4 (generation
wiring), and A5 (live evaluation gate) are follow-up slices, not part of
this spec's acceptance bar.

## Scenarios & Testing *(mandatory)*

### Scenario 1 - ORIENT facet obligation is mechanically checkable (Priority: P1)

Given a caller has already fetched ORIENT's structural-inventory response
for a repository and declares which facets (e.g. `services`, `manifests`)
the workflow requires, the assessor must classify each required facet as
`satisfied` (non-empty records present), `missing` (an explicit inventory
gap was recorded for that facet), or `unknown` (ORIENT has no gap
category and no records for it — an unsupported extraction, not a
manufactured gap).

**Why this priority**: This is the simplest mode (no traversal, no
ambiguity) and establishes the obligation/assessment vocabulary the other
two modes reuse.

**Independent Test**: Pure unit test feeding hand-built ORIENT-response
dicts (satisfied / gap / neither) into `assess_orient`, asserting the
per-facet classification and overall status.

**Acceptance Scenarios**:

1. **Given** an ORIENT response with a non-empty `services` list,
   **When** `services` is a required facet, **Then** the obligation is
   `satisfied` and cites the facet as evidence.
2. **Given** an ORIENT response with an empty `docs_dirs` list and a gap
   entry with `category="docs_dirs"`, **When** `docs_dirs` is required,
   **Then** the obligation is `missing`, not silently dropped or
   reported as an unrelated failure.
3. **Given** an ORIENT response with an empty `test_dirs` list and no
   matching gap entry, **When** `test_dirs` is required, **Then** the
   obligation is `unknown` — ORIENT itself did not account for that
   facet.

---

### Scenario 2 - TRACE target/scope obligation distinguishes missing from unknown (Priority: P1)

Given a resolved (or unresolved, or ambiguous) TRACE start symbol and an
optional required target canonical ID, the assessor must report whether
the target was reached, and if not, whether that is because the bounded
frontier was cut off (`unknown` — more graph may exist past the cap) or
because a fully-explored frontier does not contain it (`missing`).
Ambiguous starts must return `needs_clarification` without guessing a
candidate.

**Why this priority**: The handoff explicitly forbids conflating "ran out
of budget" with "target genuinely absent" (Stage A acceptance matrix,
`external gaps, depth exhaustion, node truncation and missing ORIENT
inventory remain distinguishable`). `trace_impact.py`'s existing
`TraceResult.truncated` only reports the node-count cap; it does not
report a depth cap cutting off an otherwise-continuable frontier, so this
scenario requires the accompanying `trace_impact.py` change
(`depth_limited`).

**Independent Test**: Pure unit tests over hand-built `CodebaseGraph`
fixtures via `traced_path`, then `assess_trace`, covering: target found;
target absent from a fully-explored frontier; target absent under
node-count truncation; target absent under depth-only cutoff; ambiguous
start; unresolved start.

**Acceptance Scenarios**:

1. **Given** a required target present among the traced hops, **Then**
   the target obligation is `satisfied` and cites the hop and its
   relation type.
2. **Given** a required target absent, and the traversal fully explored
   its bounded frontier with no node/depth cap engaged, **Then** the
   target obligation is `missing`.
3. **Given** a required target absent, and `TraceResult.truncated` is
   `True` (node cap) or `TraceResult.depth_limited` is `True` (depth
   cap), **Then** the target obligation is `unknown`, not `missing`.
4. **Given** an ambiguous start symbol, **Then** assessment status is
   `needs_clarification` and no candidate is silently chosen.
5. **Given** an unresolved start symbol (no match at all), **Then** the
   start obligation is `missing` and status is `partial`.

---

### Scenario 3 - IMPACT bounded negative result is a valid `satisfied` outcome (Priority: P2)

Given a resolved IMPACT start and its computed candidate set (possibly
empty, possibly truncated), the assessor must always report `satisfied`
for the candidate-set obligation — IMPACT's own construction already
guarantees every candidate carries a basis — while separately recording
whether the result was truncated, so an empty or truncated candidate set
is never confused with a global "no dependents exist" proof.

**Why this priority**: Prevents a future caller from treating IMPACT
truncation or an empty candidate list as a sufficiency failure, which
would violate the handoff's "no universal minimum chunk count" rule.

**Independent Test**: Pure unit tests over `assess_impact_result` with
empty, non-empty, and truncated `ImpactResult` fixtures, plus ambiguous
and unresolved starts (same shared handling as TRACE).

**Acceptance Scenarios**:

1. **Given** a non-empty, non-truncated candidate set, **Then** status is
   `satisfied` with no truncation reason code.
2. **Given** an empty candidate set, **Then** status is still `satisfied`
   — an empty result within the indexed graph is valid, not a gap.
3. **Given** a truncated candidate set, **Then** status is `satisfied`
   but `reason_codes` includes a truncation marker so a caller can still
   see the bound was hit.

---

### Edge Cases

- A `required_facets` / `required_target` list with duplicate entries
  must not double-count obligations.
- An ORIENT response with a `gaps` entry whose `category` does not match
  any requested facet must not affect that facet's classification.
- A TRACE node reached at exactly `max_depth` with no further matching
  edges must not be marked `depth_limited` (no frontier was actually cut
  off there).
- Direction (`forward`/`reverse`) and a `relation_types` filter must be
  respected when deciding whether a node's frontier was cut off —
  non-matching-relation edges past the cap do not count as an
  unexplored frontier.

## Non-Goals

- No repair/retry control loop, generation fence, or `/v1/repos/{id}/evidence`
  API endpoint — those are Stage A slices A2/A3/A4, tracked as follow-up
  work under the same issue #200, not this spec.
- No authority/subject/provenance input (issue #199, Stage B) — this
  spec is mechanical-signals-only, exactly as the handoff requires ("do
  not... make #199 a prerequisite for the first useful #200 release").
- No general agentic investigator, LLM judge, or natural-language mode
  router (explicitly excluded by issue #200 and the handoff).
- No live/paired quality-evaluation gate (Stage A5) — this spec's
  acceptance bar is pure unit-test coverage only, run against hand-built
  fixtures, not a live corpus.
- No change to ORIENT's ingestion-time computation (`ingestion_service`)
  or to `/trace`/`/impact` HTTP response *shape* beyond adding the new
  `depth_limited` field TRACE already needed to make Scenario 2 provable.

## Governing References

- Constitution: `.specify/memory/constitution.md` (Principles VI, VII,
  VIII: issue-linked, ADR-referencing, test-guided).
- Handoff: `DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md`
  (Stage A obligations tables, control-loop description, acceptance
  matrix — this spec implements only the mechanical-check subset needed
  for a pure assessor, not the control loop or API).
- Findings: `DOCS/notes/2026-09-19-phase-6-sufficiency-findings.md`
  (verified entry points: `trace_impact.py`, `orient.py`, `routes.py`).
- ADR-045 (`DOCS/adr/ADR-045-hybrid-vector-graph-rag.md`): retrieval flow
  this assessor sits alongside, not inside.
- Tracking issue: #200 (`Bounded evidence-sufficiency loop for
  structural workflows`), which itself names #199 as a *dependency for
  authority-aware sufficiency*, not for this mechanical-only slice; the
  handoff explicitly authorizes doing #200 mechanical work first and
  reconciling the dependency wording is a documentation nuance, not a
  scope conflict, since Stage C (not this spec) is what closes that gap.

**Known conflicts**: Issue #200's body lists #199 as a dependency without
qualifying "mechanical" vs. "authority-aware." The handoff (which the
owner directed) explicitly sequences mechanical-first. This spec follows
the handoff and notes the issue body should be clarified when #200 is
updated/closed for Stage A, rather than silently resolving the wording
conflict.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a pure function that classifies
  each ORIENT-required facet as `satisfied`, `missing`, or `unknown`
  given an ORIENT response and a list of required facet names.
- **FR-002**: The system MUST provide a pure function that classifies a
  TRACE request's `start` and optional `target` obligations as
  `satisfied`, `missing`, or `unknown`, given the start-resolution result
  and (if resolved) a `TraceResult`.
- **FR-003**: The system MUST provide a pure function that classifies an
  IMPACT request's `start` and `candidate_set` obligations, given the
  start-resolution result and (if resolved) an `ImpactResult`; a
  non-ambiguous, resolved candidate-set obligation MUST always be
  `satisfied` regardless of truncation or emptiness.
- **FR-004**: `traced_path` MUST report, per `TraceResult`, whether any
  visited node's matching-relation frontier was cut off solely by
  `max_depth` (as opposed to the existing node-count `truncated` flag),
  so a target-not-reached outcome can be classified `unknown` rather than
  `missing` when more graph may exist past the depth cap.
- **FR-005**: An ambiguous start symbol (either mode) MUST yield
  assessment status `needs_clarification` without selecting a candidate.
- **FR-006**: An unresolved start symbol (no match) MUST yield assessment
  status `partial` with the `start` obligation `missing`.
- **FR-007**: Assessment functions MUST NOT perform any I/O, retrieval,
  retraversal, or LLM call — inputs are already-computed results; this
  is Stage A1's "pure assessor" boundary.
- **FR-008**: Each returned assessment MUST carry a `policy_version`
  string so a later authority-aware policy (Stage C) can be distinguished
  from this mechanical-only one in diagnostics.

### Key Entities

- **EvidenceItem**: one piece of evidence a satisfied obligation points
  to (identity, kind, optional supporting relation/path). Not persisted;
  constructed per assessment call.
- **EvidenceAssessment**: `policy_version`, overall `status`
  (`satisfied`/`partial`/`needs_clarification`), per-obligation status
  map, `reason_codes`, `evidence`, `missing_obligations`. This is the
  full output contract for A1; `WorkBudget`/`StepRecord` from the
  handoff's contract table belong to the A2 control loop and are
  intentionally not introduced here (no consumer exists yet in this
  slice).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All Scenario 1–3 acceptance cases pass as unit tests with
  no DB/HTTP/Docker dependency (`pytest -m unit`).
- **SC-002**: `trace_impact.py`'s existing test suite continues to pass
  unmodified in behavior (only the new `depth_limited` field and its two
  new tests are added) — no regression to `truncated`, `gaps`, or hop
  ordering semantics.
- **SC-003**: `ruff check .` and `pyright .` pass clean on the new and
  modified files from repo root.

## Evaluation Evidence

**Evaluation Required**: No.

This slice adds no retrieval, ranking, generation, chunking, embedding,
or prompt-assembly behavior change (Constitution Principles III/VIII) —
it is a pure post-hoc classifier over already-computed TRACE/IMPACT/ORIENT
results, with no output yet consumed by any request path. The live
paired evaluation gate applies to Stage A5 (the wired control loop),
not this slice.

## Assumptions

- The ORIENT response shape consumed here is the JSON already returned
  by `rag_orchestrator`'s `/repos/{repo_id}/orient` passthrough
  (`languages`, `file_counts`, `manifests`, `services`, `test_dirs`,
  `docs_dirs`, `heuristic_fields`, `gaps: [{category, path, reason}]`) —
  unchanged by this spec.
- Callers of `assess_trace`/`assess_impact` are responsible for having
  already called `resolve_start_symbol` and, if resolved, `traced_path`/
  `assess_impact` (the `trace_impact.py` function) themselves; this
  spec's assessor does not call them.
- A2's controller (not part of this spec) will decide *what to do* with
  a `missing`/`unknown`/`needs_clarification` assessment (one bounded
  repair, per the handoff's priority table); this spec only produces the
  classification.
