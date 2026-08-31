# Feature Specification: WP-L6a — Language-Aware Retrieval Filter

**Feature Branch**: `feat/wp-l6a-language-aware-retrieval-issue-85`

**Created**: 2026-08-31

**Status**: Draft

**Tracking Issue**: #85

**Roadmap Context**: Phase 3 (multi-language support), pulled forward from
WP-L6 per `DOCS/audit/03-Multi-Language-Graph-Plan.md` §3, narrowed to the
retrieval-filter half only. Sequenced ahead of WP-L3/WP-L4 (Rust/Java)
because it becomes part of the measurement apparatus for validating WP-L2
(#83, shipped) against a real mixed-language repository.

**Input**: User description: "give every code symbol/import graph node a
dedicated language value, carry it into vector chunk metadata as a typed
indexed column, and let the graph-aware code-query endpoint accept an
optional language filter that scopes retrieval to one language, defaulting
to today's unfiltered behavior."

## Scenarios & Testing *(mandatory)*

### User Story 1 - Distinguish extraction failures from retrieval leakage in a mixed-language repo (Priority: P1)

An operator investigating a bad answer from a repository that mixes Python
and TypeScript/JavaScript code needs to tell apart two different failure
causes: the language-specific extractor produced wrong graph structure, or
retrieval simply mixed candidates from both languages together. Today,
without any language scoping, both failure modes look identical from the
query response.

**Why this priority**: this is the entire reason this feature is being
built now rather than later — it directly gates trustworthy validation of
the just-shipped TypeScript/JavaScript extractor.

**Independent Test**: ingest a repository containing both Python and
TypeScript files, ask the same question once unfiltered and once scoped to
each language, and confirm the scoped answers only ever cite sources from
that language.

**Acceptance Scenarios**:

1. **Given** a repository with both Python and TypeScript code ingested,
   **When** a query is scoped to Python, **Then** every cited source comes
   from a Python file.
2. **Given** the same repository, **When** the same query is scoped to
   TypeScript, **Then** every cited source comes from a TypeScript or
   JavaScript file.
3. **Given** the same repository, **When** the query is run with no
   language scoping, **Then** results are identical to what today's
   behavior already produces (no regression).

---

### User Story 2 - Retrieval never silently reintroduces cross-language results after a fallback (Priority: P2)

An operator scopes a query to one language and expects that scoping to
hold even when the underlying seed search has to relax another condition
to find any results at all (the same way scoping a query to one repository
already survives that relaxation today).

**Why this priority**: without this, language scoping would be
unreliable exactly in the edge case it's meant to help with (sparse
per-language results) — but the base case (User Story 1) already delivers
the primary value independent of this refinement.

**Independent Test**: force the seed search's primary condition to return
nothing so the existing relaxation path runs, with a language scope
applied, and confirm the relaxed search still carries the language scope.

**Acceptance Scenarios**:

1. **Given** a query scoped to one language whose primary seed search
   returns no results, **When** the existing fallback relaxation runs,
   **Then** the relaxed search still excludes the other language(s).

---

### Edge Cases

- A query with no language scoping specified behaves exactly as it does
  today — this feature changes no default behavior.
- A language scope for a language that has no ingested content in this
  repository yields no results for that scope, rather than silently
  falling back to unfiltered results (an empty, honest answer is more
  trustworthy than a silently-widened one).
- Non-code content (documentation sections, external/unresolved
  placeholder nodes) carries no language value and is excluded from any
  language-scoped search — it was never part of what "Python" or
  "TypeScript" results would mean.
- Documents ingested before this feature shipped have no language value
  recorded; a language-scoped query against that pre-existing content
  simply won't surface it (consistent with "empty, not silently wrong").

## Non-Goals

- No language selector in the Gradio UI — this is an API-level capability
  only; the UI surface is deferred to the remainder of WP-L6.
- No per-language embedding model — one embedder continues to serve all
  languages, unchanged.
- No support for Rust or Java as language values — those extractors don't
  exist yet (WP-L3/WP-L4).
- No formal, merge-blocking evaluation run comparing filtered-vs-unfiltered
  retrieval precision. This feature is an optional, off-by-default
  narrowing of an existing search — not a change to ranking, chunking,
  embedding, or generation architecture. A manual comparison against a
  real mixed-language repository is documented as a follow-up validation
  exercise, not an automated acceptance gate.

## Governing References

- Constitution: `.specify/memory/constitution.md`
- ADRs: ADR-030 (unified artifact graph), ADR-031 (canonical identity —
  language is metadata, never part of identity), ADR-045 (hybrid
  vector+graph RAG pipeline, the retrieval flow this feature adds one
  optional filter to)
- Audit/roadmap: `DOCS/audit/03-Multi-Language-Graph-Plan.md` §3 WP-L6
  (this feature's origin and acceptance criteria, narrowed here to its
  retrieval-filter half); `DOCS/audit/04-Scalability-Plan.md` WP-S4B (the
  existing typed-filter-column pattern this feature's storage design
  follows — that entry already named `language` as an anticipated,
  not-yet-implemented fourth typed column alongside `repo_id`/`doc_type`)
- Tracking issue: #85

**Known conflicts**: None.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record a language value on every code symbol
  and import graph node produced by an existing language extractor
  (currently Python, TypeScript, JavaScript), distinct from any existing
  content-type classification on that node.
- **FR-002**: Non-code nodes (documentation sections, unresolved/external
  placeholder nodes) MUST NOT carry a language value.
- **FR-003**: Every vector chunk embedded from a language-bearing node MUST
  carry that same language value in its retrievable metadata.
- **FR-004**: The language value MUST be efficiently filterable at query
  time (i.e., stored so a language-scoped search does not require a full
  scan of unstructured metadata), consistent with how this system already
  makes repository and content-type filterable.
- **FR-005**: The graph-aware code-query endpoint MUST accept an optional
  language scope. When provided, every retrieved seed result MUST match
  that language.
- **FR-006**: When the language scope is omitted, retrieval behavior MUST
  be unchanged from today (no seed result is excluded on language grounds).
- **FR-007**: A language scope, once applied, MUST remain in effect through
  any existing fallback/relaxation behavior the seed search already
  performs for other conditions — a fallback MUST NOT reintroduce
  candidates outside the requested language.
- **FR-008**: Graph-traversal expansion from an already-language-scoped
  seed set MUST NOT require its own separate language filter — expansion
  follows graph edges from seeds that are already correctly scoped.

### Key Entities

- **Language value**: one of `python`, `typescript`, `javascript` in this
  feature's scope — an attribute of a code graph node and of the vector
  chunks embedded from it, never part of that node's canonical identity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a repository mixing Python and TypeScript/JavaScript
  content, a language-scoped query returns zero results from any other
  language, in 100% of cases tested.
- **SC-002**: An unscoped query against the same repository returns
  results identical to pre-feature behavior (zero regression).
- **SC-003**: A language scope survives the existing seed-search fallback
  relaxation in 100% of cases tested — a relaxed search never reintroduces
  another language's results.
- **SC-004**: Adding this feature requires no change to how any existing,
  already-ingested repository is queried unless a language scope is
  explicitly requested.

## Evaluation Evidence

**Evaluation Required**: No — this is an optional, off-by-default metadata
filter on an existing search, not a change to retrieval ranking, hybrid
search strategy, chunking, embedding, or prompt/context assembly.
Constitution Principle III's evidence-before-architecture-change gate
therefore does not apply; Principle VIII's test-guided development
(acceptance-criteria tests, see Success Criteria and `tasks.md`) applies
instead. A manual, non-blocking comparison of filtered-vs-unfiltered
retrieval against a real mixed-language repository is documented in
`quickstart.md` as a follow-up validation exercise that directly supports
WP-L2 confidence-building, not as a criterion this feature's merge depends
on.

## Assumptions

- The three language values in scope (`python`, `typescript`,
  `javascript`) are treated as three independent values, not grouped —
  a caller wanting "everything except Python" would need to know both
  `typescript` and `javascript` exist as separate values; no combined
  "JS-family" alias is introduced in this feature.
- An unrecognized language value (e.g. a typo, or a not-yet-supported
  language name) is treated as a scope that matches nothing, the same way
  scoping to a language with no ingested content yields no results —
  there is no separate validation error response in this feature's scope.
- This feature does not backfill language values onto content ingested
  before it shipped; only newly (re-)ingested content gains a language
  value, consistent with how this system's other metadata additions have
  been introduced (no retroactive migration of existing rows' content,
  only schema readiness for new rows).
