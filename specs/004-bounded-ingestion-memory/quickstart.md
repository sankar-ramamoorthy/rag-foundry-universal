# Quickstart & Regression/Benchmark Harness: Bounded Ingestion Memory

This is a validation guide, not implementation code — it documents runnable
scenarios that prove the feature works, per research.md Decision 6's
measure-first approach. Exact scripts/fixtures are implementation-phase
(`/speckit-tasks`) output; this defines what they must show.

## Prerequisites

- `docker-compose.test.yml` stack (or full `docker-compose.yml`) with
  Postgres+pgvector and `ingestion_service` running, migrations applied
  (`alembic upgrade head`).
- A way to observe `ingestion_service`'s resident memory during a run — e.g.
  `docker stats ingestion-service` polled at a fixed interval, or reading
  `/proc/<pid>/status` `VmHWM` inside the container. Either is acceptable;
  the harness only needs a peak-RSS-over-time series, not a specific tool.
- Network access to clone `https://github.com/arc53/DocsGPT.git` (fixture A
  only — fixture B does not need this).

## Fixture A: Real-world reproduction (`arc53/DocsGPT`)

This is the exact repository and scale from issue #160's confirmed incident
(44,884 graph nodes, ~23,354 embeddable chunks after empty-text nodes are
excluded).

**Steps**:
1. Set `ingestion_service`'s memory allocation to match (or slightly exceed,
   for a controlled comparison) the allocation that produced the original
   OOM-kill (exit 137) — e.g. via `docker-compose.yml`'s `mem_limit` or the
   container runtime's equivalent.
2. Submit `POST /v1/codebase/ingest-repo` with
   `git_url=https://github.com/arc53/DocsGPT.git`.
3. Poll `GET /v1/codebase/ingest-repo/{ingestion_id}` until `status` reaches
   a terminal value, recording `embed_progress` at each poll
   (contracts/status-endpoint.md).
4. Concurrently sample `ingestion_service`'s resident memory for the run's
   duration.

**Pass criteria** (SC-001, SC-004):
- `status` reaches `"completed"`, not killed/`"failed"` from memory
  exhaustion.
- `GET /v1/repos` lists the repo with `status: "completed"`.
- The number of persisted vectors matches the number of non-empty-text
  nodes (~23,354 — confirmed via `vector_store_service`'s per-ingestion
  count, or the graph/vector equivalence check below).
- `embed_progress.nodes_processed` strictly increases across successive
  polls until it reaches `nodes_total` (SC-004: observable forward
  progress).
- Peak sampled resident memory during the run is materially lower than
  whatever peak (unmeasured, since the process was killed) the original
  incident implies — recorded as a data point, not a pass/fail threshold in
  itself, since fixture B is where the size-independence claim (SC-002) is
  actually tested at multiple scales.

**Graph/vector equivalence check** (FR-007): compare the resulting
`document_nodes` count and relationship count against a prior *successful*
structural-only run's numbers (i.e. confirm this feature didn't change how
many nodes/relationships get created — only chunk-embed-persist to the graph
pass changed).

## Fixture B: Synthetic scalable fixture

A generated or checked-in small repo whose embeddable-chunk count is a test
parameter, used to check the *shape* of the memory-vs-chunk-count curve
without depending on network access or a slow external clone.

**Steps**:
1. Generate (or select from existing test fixtures) a repo with N
   embeddable artifacts, for at least two values of N differing by a
   material factor (e.g. N and 4N).
2. Ingest each at the **same** working-set/batch-size configuration.
3. Sample peak resident memory for the chunk-embed-persist stage specifically
   (isolate it from the graph-build stage's memory using the `embed_progress`
   field's appearance as a marker of stage boundary, per research.md
   Decision 2's sequential-peaks design).

**Pass criteria** (SC-002, and indirectly FR-001):
- Increasing N by a material factor (e.g. 4x) does **not** increase the
  chunk-embed-persist stage's peak resident memory by anywhere close to
  that same factor — it should track the configured working-set size, which
  did not change between the two runs.
- Increasing the working-set/batch-size setting itself (at fixed N) *does*
  visibly move the chunk-embed-persist stage's peak memory — confirming the
  setting is actually the control variable (FR-004), not a no-op.
- Final graph/vector counts for a given N are identical across different
  working-set/batch-size configurations (FR-007) — run the same N at two
  different batch sizes and diff the resulting `document_nodes` and vector
  counts.

## Fixture-independent checks

- **FR-008 (zero embeddable artifacts)**: ingest a repo containing only
  files with no extractable text (e.g. all binary/ignored-suffix files) and
  confirm ingestion still reaches `status: "completed"` with
  `embed_progress.nodes_total == 0`.
- **User Story 2 (partial-progress survival)**: interrupt an ingestion
  (e.g. `docker kill` the container) after `embed_progress.nodes_processed`
  has advanced partway through `nodes_total` but before completion; on
  restart, confirm vectors for the artifacts covered by
  `nodes_processed` at the time of interruption are already queryable via
  `vector_store_service` (they were persisted before the kill, per FR-002),
  even though the ingestion record itself is left in `running` (the
  separate, out-of-scope #161 lifecycle gap — not something this feature's
  harness needs to clean up, only needs to confirm doesn't destroy already-
  persisted work).
