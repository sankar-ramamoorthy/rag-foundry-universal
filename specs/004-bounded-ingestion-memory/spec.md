# Feature Specification: Bounded Ingestion Memory

**Feature Branch**: `004-bounded-ingestion-memory`

**Created**: 2026-09-16

**Status**: Draft

**Tracking Issue**: #160

**Roadmap Context**: Not tied to a pre-existing roadmap phase — a reliability/scalability fix scoped directly from a confirmed live-incident postmortem (issue #160), not a planned feature.

**Input**: User description: "Bound ingestion_service's memory usage during codebase ingestion so it scales with a configured working-set/batch size rather than total repo artifact/chunk count, per the confirmed findings in GitHub issue #160 (DocsGPT OOM: ingestion_service was OOM-killed, exit 137, after graph persistence completed for 44,884 nodes but before any of the 23,354 embeddable chunks were vector-persisted)."

## Scenarios & Testing *(mandatory)*

### User Story 1 - Large repo ingests without exhausting memory (Priority: P1)

An operator ingests a large real-world repository (comparable in scale to the
`arc53/DocsGPT` incident: tens of thousands of graph nodes, tens of thousands
of embeddable chunks) into `ingestion_service` under the same memory
allocation that previously caused an OOM-kill. Ingestion completes
successfully — the graph is persisted, every embeddable artifact is chunked,
embedded, and vector-persisted, and the ingestion record reaches
`completed` — without the process being killed for exceeding available
memory.

**Why this priority**: This is the incident this spec exists to prevent from
recurring. Without it, any sufficiently large repository ingestion remains a
reliability risk to `ingestion_service` and, since it shares a host with
other services, a risk to the rest of the stack.

**Independent Test**: Re-ingest the same `arc53/DocsGPT` snapshot (or an
equivalently large fixture) against the same memory ceiling that produced
the original OOM, and confirm it reaches `completed` with the same graph
node count and a non-zero, complete vector count.

**Acceptance Scenarios**:

1. **Given** a repository whose total embeddable-chunk count previously
   caused an OOM-kill, **When** it is ingested again under an unchanged
   memory allocation, **Then** the ingestion reaches `status=completed` and
   every embeddable artifact has a corresponding persisted vector.
2. **Given** an ingestion in progress, **When** memory usage is observed
   during the chunk/embed/persist stage, **Then** it does not grow
   proportionally with total repository size — it stays bounded by the
   configured working-set/batch size.

---

### User Story 2 - Partial progress survives an interruption (Priority: P2)

An operator's ingestion run is interrupted (process killed, container
restarted) partway through the chunk/embed/persist stage of a large repo.
Because that stage now processes and persists work in bounded slices instead
of accumulating the whole repository before persisting anything, the work
already completed for prior slices remains durably persisted; only the
in-flight slice's work is lost.

**Why this priority**: This directly addresses the DocsGPT incident's
observed outcome — full graph persisted, but zero of 23,354 possible vectors
persisted, because the entire embedding/persistence stage was one
all-or-nothing unit of work. Reducing the blast radius of an interruption is
valuable independent of whether the interruption's root cause (OOM) is fully
eliminated.

**Independent Test**: Interrupt an ingestion partway through the
chunk/embed/persist stage and confirm that vectors for artifacts processed
before the interruption point are already queryable, rather than all-or-
nothing.

**Acceptance Scenarios**:

1. **Given** an ingestion processing artifacts in bounded slices, **When**
   the process is killed after N slices have completed but before the
   (N+1)th slice finishes, **Then** vectors for the artifacts in the first N
   slices are already persisted and queryable.

---

### User Story 3 - Ingestion progress is observable (Priority: P3)

An operator watching a long-running ingestion can tell, from observable
progress information, that it is actively making forward progress through
the chunk/embed/persist stage rather than hung or stalled — closing the gap
the DocsGPT postmortem identified ("no sufficiently granular stage/memory
logs to distinguish" where in the pipeline a failure occurred).

**Why this priority**: Lower priority than actually bounding memory (P1) or
limiting blast radius (P2), but necessary for operators and future
incident investigations to trust and verify the P1/P2 behavior without
re-deriving it from source inspection each time, as this investigation had
to.

**Independent Test**: Start an ingestion of a large repository and confirm
that, at any point during the chunk/embed/persist stage, currently available
progress information (e.g. artifacts processed vs. total) advances over
time.

**Acceptance Scenarios**:

1. **Given** an ingestion in the chunk/embed/persist stage, **When** an
   operator checks its progress at two different times, **Then** the
   reported progress has advanced, evidencing forward motion rather than a
   hang.

---

### Edge Cases

- What happens when a single artifact's text is large enough that even one
  working-set slice containing it is a significant memory allocation (the
  DocsGPT incident's largest node was ~128KB; some real repos may have
  larger)?
- How does the system behave when a repository has zero embeddable artifacts
  (all nodes have empty text, as ~48% of DocsGPT's nodes did)?
- How does slicing interact with the existing repo-wide `canonical_id →
  document_id` lookup that chunk/embed/persist already depends on — does
  building that map remain a single repo-wide step, or does it also need to
  be bounded for a sufficiently large repo?
- What happens if the configured working-set/batch size is set larger than
  the total number of embeddable artifacts (should behave identically to
  today's whole-repo-at-once processing)?
- What happens if the vector-store or embedding provider becomes unavailable
  partway through a slice — does the slice retry, fail the whole ingestion,
  or skip forward (this determines what "durably persisted" means for User
  Story 2)?

## Non-Goals

- This spec does not decide or implement a specific streaming/incremental
  ingestion design — that is `/speckit-plan`'s job.
- This spec does not add durable job queues, external workers, or otherwise
  replace the current in-process background-thread ingestion model.
- This spec does not address the orphaned `status=running` lifecycle gap
  (tracked separately in issue #161) — that is a distinct failure mode (hard
  process death skipping status cleanup) from memory accumulation, and the
  two must not be conflated per issue #160's explicit direction.
- This spec does not treat a container `mem_limit` as sufficient on its own;
  see FR-006.
- This spec does not change what gets embedded, how it is chunked, or which
  embedding model is used — embedding unit and chunking semantics are
  unchanged (see Governing References); only the memory lifetime of that
  work during processing changes.
- This spec does not fix or re-litigate the file-by-file vs. repo-wide
  structural resolution tradeoff for graph construction (`RepoGraphBuilder`/
  `GraphAssembler`) — it explicitly requires that the repo-wide structural
  pass continue to work as-is (FR-003), and only bounds the
  chunk/embed/persist pathway that follows it.
- Exact numeric batch-size defaults, and the specific measured memory-growth
  ratio for SC-002, are not decided here — they are planning/benchmarking
  outputs, not spec-time decisions.

## Governing References

- Constitution: `.specify/memory/constitution.md` — Principle II (Service &
  Database Boundaries: `ingestion_service` owns all DB access exclusively),
  Principle VI (every change traces to a documented issue), Principle VII
  (specs reference ADRs, not restate them).
- ADR-030 (`DOCS/adr/ADR-030-unified-artifact-graph.md`) — repo scoping and
  rebuild determinism, relevant to any change touching how nodes are
  processed per repo.
- ADR-038 (`DOCS/adr/ADR-038-pipeline-construction-ownership.md`) — pipeline
  construction must go through `pipeline_factory.py`; any bounded-slicing
  change to `IngestionPipeline` usage must preserve this.
- ADR-039 / ADR-040 (`DOCS/adr/ADR-039-artifact-level-embedding-strategy.md`,
  `ADR-040-code-intelligence-embedding-strategy.md`) — embedding unit is the
  artifact, not a sub-chunk; bounded-slicing must not change this unit.
- ADR-041 (`DOCS/adr/ADR-041-code-artifact-persistence-embedding-strategy.md`)
  — text persisted on `DocumentNode.text` directly; relevant to what data a
  bounded slice needs to re-read vs. hold in memory.
- Tracking issue: #160 (DocsGPT OOM investigation and confirmed findings).

**Known conflicts**: None identified. This spec's bounded-slicing requirement
(FR-001–FR-003) is additive to the ADRs above — it changes memory lifetime
during processing, not the identity, embedding-unit, or persistence-location
rules those ADRs establish.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The ingestion system MUST process a repository's
  chunk-embed-persist work in bounded-size slices (a configured working-set
  size), such that peak memory held for chunk text, embedding vectors, and
  persistence-record working state at any point in time is bounded by that
  configured size, not by the repository's total embeddable-artifact count.
- **FR-002**: The ingestion system MUST fully persist each slice's vectors
  before beginning to accumulate the next slice's chunk/embedding working
  state, so that failure after slice N leaves slices 1..N durably persisted
  (supports User Story 2).
- **FR-003**: Bounding memory for the chunk-embed-persist pathway MUST NOT
  require bounding the repository-wide structural graph-resolution pass
  (symbol/import/call/inheritance resolution) — that pass's existing
  correctness guarantees are unaffected by this feature.
- **FR-004**: The working-set/batch size MUST be operator-configurable
  without a code change.
- **FR-005**: The ingestion system MUST expose observable progress through
  the chunk-embed-persist stage (e.g., artifacts or slices completed vs.
  total) sufficient to distinguish active progress from a stall (supports
  User Story 3).
- **FR-006**: A container memory ceiling (`mem_limit` or equivalent) MUST NOT
  be the sole mechanism relied upon to prevent an OOM during ingestion; it
  MAY be added as an additional backstop, but bounded-slice processing
  (FR-001) is the primary mechanism.
- **FR-007**: For a given repository snapshot, the final persisted graph
  (nodes, relationships) and vector set MUST be identical regardless of the
  configured working-set/batch size — batching changes memory profile only,
  never ingestion output.
- **FR-008**: When a repository has zero embeddable artifacts, the ingestion
  system MUST still complete successfully (graph-only ingestion), consistent
  with today's behavior for such repositories.

### Key Entities

- **Working-set slice**: A bounded subset of a repository's embeddable graph
  nodes that is chunked, embedded, and vector-persisted as one unit before
  its working memory (chunk text, embedding vectors, persistence records) is
  released and the next slice begins.
- **Ingestion progress state**: Observable information about how far an
  in-progress ingestion has advanced through the chunk-embed-persist stage
  (e.g., slices or artifacts completed vs. total), independent of the
  existing `status` field (`accepted`/`running`/`completed`/`failed`), which
  today carries no sub-stage granularity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A repository of the same scale as the `arc53/DocsGPT` incident
  (44,884 graph nodes, ~23,354 embeddable chunks) completes ingestion to
  `status=completed` with a full vector set, under the same memory
  allocation that previously produced an OOM-kill.
- **SC-002**: Peak memory observed during the chunk-embed-persist stage does
  not scale linearly with total repository chunk count — increasing a test
  repository's embeddable-chunk count substantially increases elapsed
  ingestion time but not peak memory in that stage in the same proportion.
  (Exact target ratio is a planning/benchmarking output, not fixed here.)
- **SC-003**: After an ingestion is interrupted partway through the
  chunk-embed-persist stage, the number of already-embedded artifacts that
  must be re-processed on retry is bounded by one working-set slice, not the
  full repository.
- **SC-004**: An operator can confirm, from observable progress information
  and without reading source code or logs at DEBUG granularity, that a
  running ingestion is advancing rather than hung, at any point after
  ingestion start.

## Evaluation Evidence

**Evaluation Required**: No.

This feature changes the memory lifetime and batching of existing
chunk/embed/persist processing; it does not change chunking strategy,
embedding model, or retrieval/generation behavior (FR-007 requires identical
output regardless of batch size). Constitution Principle III's evidence
requirement governs retrieval/generation *quality* changes (reranking,
hybrid search, chunking rework that changes chunk semantics, embedding-model
migration); this feature is explicitly barred from changing those semantics,
so it does not fall under that gate.

## Assumptions

- The existing repo-wide `canonical_id → document_id` lookup that
  `_embed_repo_artifacts` already builds once per ingestion (cheap,
  structural-only) can continue to be built once per ingestion rather than
  per slice; only the heavy chunk/embed/persist work needs bounding. If
  benchmarking during planning finds this lookup itself becomes a memory
  concern at extreme repo scale, that is a planning-phase finding, not
  assumed away here.
- `ingestion_service` remains the sole owner of database access (Constitution
  Principle II); bounded slicing is an internal processing change within
  `ingestion_service`, not a new cross-service dependency.
- The existing embedder (Ollama) and vector-store HTTP interfaces are reused
  as-is; this feature does not require a new embedding provider or vector
  store capability.
- "Operator" in this spec refers to whoever triggers and monitors ingestion
  (via the Gradio UI or direct API) — there is no distinct end-user role for
  this infrastructure-facing feature.
- A future container `mem_limit` (defense-in-depth, per FR-006) is out of
  this spec's scope to size or configure, but is not precluded as a
  complementary follow-up.
