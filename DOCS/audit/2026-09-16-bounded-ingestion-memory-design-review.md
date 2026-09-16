---
title: "Bounded ingestion memory: independent design and task review"
date: 2026-09-16
type: audit
status: complete
source_commit: 308f0ac068fb0a8bdbb30ceba34cc6777abfb304
tags: [audit, architecture, ingestion, memory, reliability]
related:
  - "[Repository audit](./2026-09-16-repository-architecture-audit.md)"
  - "[Feature specification](/specs/004-bounded-ingestion-memory/spec.md)"
  - "[Implementation plan](/specs/004-bounded-ingestion-memory/plan.md)"
  - "[Tasks](/specs/004-bounded-ingestion-memory/tasks.md)"
---

# Design verdict

**Keep the paged database read and sequential chunk/embed/persist direction. Amend the design and acceptance tests before implementing it.** The current tasks can produce a substantial memory improvement without proving the bound they claim. Several acceptance criteria cannot pass without either changing their wording or expanding implementation scope.

The checked-out branch contains specification, plan, research, and tasks, but no implementation of this feature. GitHub CLI access returned HTTP 401 and browser access did not retrieve the PR, so this review does not establish PR #164's current remote state. The incident measurements are supplied production evidence, not measurements repeated by this audit.

## What the proposal gets right

The actual repository ingestion path accumulates all chunks before embedding, the embedder accumulates all returned vectors, and persistence constructs all records before issuing its first write. Existing HTTP batch sizes do not bound those lists. Sources: [_embed_repo_artifacts](/ingestion_service/src/api/v1/codebase_ingest.py#L79), [embed_and_persist_batch](/ingestion_service/src/core/pipeline.py#L187), [OllamaEmbedder](/shared/embedders/ollama.py#L47), [persist_batch](/ingestion_service/src/core/http_vectorstore.py#L71).

Reading already-persisted node text in keyset pages is a sensible way to decouple the embedding stage from graph ownership. Keeping cross-file graph resolution intact is appropriate. Reconstructing language with the same suffix helper avoids a needless schema change. Separating the outer working-set controls from provider/write HTTP batch sizes is also correct. Neither a queue platform nor a pipeline-factory refactor is required to make this improvement.

## Required corrections

### M1. Node pages do not bound chunk or embedding counts

T006 requires each pipeline call's chunk count to be at most the node page size, and total chunks to equal total non-empty nodes. T009 calls the pipeline once per node page. These assertions contradict the real chunker.

The [current selector](/shared/chunkers/selector.py#L25) uses fixed-character splitting for text of at least 10,000 characters. The audit probe passed one 128,000-character artifact through the actual selector and chunker: **143 chunks from one node**. A page containing 200 similarly sized artifacts would produce 28,600 chunks before embedding. This is a constructed illustration, not a measurement of DocsGPT's size distribution.

The quickstart's expected vector count of approximately 23,354 is derived as if non-empty nodes were vectors. The brief uses this figure as an embeddable-chunk count, while the design alternates between nodes and chunks. Recount both against the pinned fixture. Expected vector cardinality is the sum of actual emitted chunks, not the number of text-bearing rows.

**Amendment:** distinguish database node-page size from embedding chunk count and byte budget. Limit the chunk/embedding buffer itself. Define what happens to one oversized artifact. Retaining one artifact's complete text and chunk list gives a bound that still depends on the largest artifact; it is acceptable only as an explicitly measured MVP limitation. A strict bound independent of artifact size needs streaming chunk production or an explicit oversized-input policy. A SQL row limit alone cannot provide a byte bound on arbitrary TEXT values.

Do not silently truncate source or change chunk boundaries as a memory fix. Those would invalidate the promised output parity and require quality evaluation.

### M2. Splitting artifacts across calls resets chunk indices

[HttpVectorStore.persist_batch](/ingestion_service/src/core/http_vectorstore.py#L94) initializes `index_by_doc = {}` on every call. It works when an entire artifact stays in one call. Splitting a large artifact into bounded chunk buffers produces repeated indices starting at zero. The audit probe reproduced `[0, 0]` for two successive pieces of the same artifact.

**Amendment:** preserve each chunk's document-local ordinal across buffers. This requires a small persistence contract extension or equivalent explicit ordinal handling; relax the blanket prohibition on changing persistence internals where necessary. Keeping its signature unchanged is less important than maintaining source order and identity. Avoid a new repo-wide counter map: sorted artifact processing can retain only the active artifact's ordinal.

### M3. Removing function arguments does not release caller locals

T010 says graph data becomes eligible for release when `persist_graph()` returns once it is no longer passed to `_embed_repo_artifacts`. However, `_background_ingest_repo` still owns `repo_graph` and `nodes` until those references are deleted, overwritten, or their scope ends. Not passing them into the next function changes no such ownership.

**Amendment:** place graph build/persistence in a helper scope returning only scalar results, or explicitly release every remaining graph reference before beginning embedding. Verify object lifetime. Include references retained by any future builder changes, generators, debug state, or ORM objects. Avoid fetching ORM entities that accumulate in long-lived structures; use the proposed narrow projections.

The [research ownership map](/specs/004-bounded-ingestion-memory/research.md) also overstates simultaneous copies. The embedder's `texts` local normally expires when `embed()` returns, before persistence creates `records`. Repeating an immutable text object in dictionaries adds references, not necessarily another in-memory text copy. Serialization does create additional transient allocations. The whole-repo retention defect remains valid, but the stated four-to-five-times duplication is not a measured or exact allocation model.

### M4. Partial durability is not resumability

SC-003 promises at most one slice of reprocessing on retry. Neither the proposal nor current code records a resumable checkpoint or skips completed slices. A normal retry starts a new ingestion, replaces graph nodes with new document IDs, cascades away their vectors, and re-embeds the repository. The graph advisory lock protects the replacement transaction, not an entire ingestion attempt.

**Amendment:** for this MVP, promise that successfully committed write batches survive process death until explicit cleanup/rebuild. Remove the one-slice retry-work guarantee. True resume would require stable generation identity, durable checkpoints, idempotent vector writes, and a retry API/workflow; keep it a separate feature.

Also clarify that an outer slice can partially persist: `persist_batch` may issue multiple independently committed HTTP write batches. A kill during a slice can leave some of that slice's vectors too. The old implementation was not transactionally all-or-nothing across repository persistence; it delayed the *first* write until all embeddings were available.

Direct vector-store queryability of partial data is different from serving it through `/v1/rag`: repository resolution uses completed ingestions. Do not weaken completed-only serving to demonstrate durability.

### M5. Paging must bind to one ingestion attempt

The new page query filters only by `repo_id`. Two background ingestions of the same repository can run concurrently. After attempt A persists its graph, attempt B can replace it while A pages through text. Fresh page reads can therefore read B's rows while writing vectors labeled with A's ingestion ID; count/page consistency can fail too. Existing embedding has related replacement races, but database paging adds this specific exposure.

**Amendment:** scope count and pages to `repo_id` plus the intended ingestion ID, and reject or fail when the expected generation disappears. Serialize same-repository ingestion and deletion over the whole operation, not just the graph transaction. For the present single-process deployment, a small explicit admission policy is preferable to silently accepting overlapping writes. If a process-local guard is used, document that it is not sufficient for multiple workers/replicas. Do not hold a database transaction open for hours of remote embedding merely to keep a paging snapshot.

Per-ingestion bounded memory also does not bound service memory with unlimited concurrent daemon threads. At minimum establish a one-active-ingestion operational envelope and reject/defer excess work explicitly. This can accompany #160 without introducing a durable queue.

### M6. The benchmark currently cannot isolate the claimed stage

T014 requires an embedding-stage peak, but the proposed stage marker appears only after the first page completes and the progress feature is deferred to US3. `VmHWM` is a process lifetime high-water mark, so a graph-build peak remains visible during embedding. Freed Python objects also do not guarantee an immediate fall in resident memory.

**Amendment:** add cheap stage-boundary events to US1, before the first page is allocated. Sample current process RSS and container memory over time; record high-water marks separately. Use fresh processes for comparable runs and report both whole-ingestion peak and embedding-stage incremental allocation relative to its start. Track live buffer maxima as a deterministic complement to RSS. Include graph build and persistence in the end-to-end ceiling test even though their algorithmic memory growth remains outside this feature.

Pin the real repository to a commit, not a moving default-branch clone. The current HTTP form cannot select a revision; use a prepared checkout in an isolated accessible environment until pinning is implemented. Record the exact incident ceiling if recoverable. If unknown, state that exact-ceiling reproduction is unavailable and declare a new test ceiling; do not call it the same allocation.

Use both many-small-artifact and few-large-artifact fixtures, mixed languages, whitespace-only nodes, empty graphs, a failure after a committed write batch, and an oversized artifact. Define the acceptable memory-growth threshold before the validation run, after a separately labeled tuning run.

The production machine is Linux with a GTX 1080 Ti. The relevant process/container RAM measurements must be distinguished from Ollama GPU VRAM. This audit has HTTP access only and did not rerun an OOM fixture or inspect cgroups.

### M7. Output parity must compare content, not just counts

T007 compares selected metadata; T008 compares graph/vector counts. Equal counts can hide changed chunk text, wrong document assignment, lost suffixes, language drift, and duplicate ordinals. Raw database IDs cannot be byte-identical between ordinary ingestions: nodes and chunks currently use UUID4.

**Amendment:** compare normalized records keyed by canonical ID and document-local chunk ordinal, including exact chunk text, metadata, and vectors generated by a deterministic stub. Compare graph edges by canonical endpoint IDs. Assert no gaps/duplicates in ordinals. For the real embedder, record model identity and use an explicit numerical tolerance if needed. Define normalized parity in FR-007 rather than literal UUID equality.

### M8. Smaller contradictions should be resolved in the task list

- `text != ''` does not match the current `not text.strip()` exclusion. Keep count and page semantics consistent for spaces, tabs, and newlines.
- T022 updates progress only inside the loop. An empty repository needs an explicit initialized/final zero-total progress record for T026; otherwise the promised field never appears.
- T021 proposes copying `mark_failed`'s JSON mutation pattern. It mutates the existing plain JSON object in place; use a fresh outer dictionary and test committed data with a new database session. A mock assertion on assignment is insufficient to establish persistence.
- The plan's non-regressions require retaining `get_canonical_id_map`, while research Decision 4 and T011 retire it. Choose the page-row design consistently.
- The spec says no architectural conflicts, but invokes artifact-level 1:1 embedding despite actual sub-chunking. [ADR-039](/DOCS/adr/ADR-039-artifact-level-embedding-strategy.md) is proposed; [ADR-040](/DOCS/adr/ADR-040-code-intelligence-embedding-strategy.md) accepts 1:1 artifact embedding. Disclose this pre-existing drift and preserve actual chunking for the memory change.
- `PERSIST_BATCH_SIZE` is currently a class constant, not an environment setting. Configuration guidance should distinguish what is operator-configurable today from new controls.
- T005's SQL paging guarantees need a real PostgreSQL integration test, including selective repo filters. A primary-key index on random document IDs does not automatically make `(repo_id, document_id)` paging efficient across a large shared table; inspect the query plan before deciding whether a composite index is needed.
- SC-004's progress-after-ingestion-start wording exceeds embed-only progress. Narrow it or expose clone/build/persist stages too. Polls can legitimately repeat the same count; require monotonicity plus eventual advancement, not strict increase on every poll.

## Revised MVP task sequence

1. Correct M1-M8's contracts and define the oversized-artifact and concurrency envelope. Keep #165 and durable workers outside this change.
2. Write acceptance fixtures/probes for many chunks per node, ordinal continuity, normalized output parity, object release, and count/page filtering.
3. Add generation-scoped keyset paging and explicit graph-reference release.
4. Implement bounded chunk/byte buffers with stable ordinals; persist each buffer before continuing. Record stage boundaries and committed counts from the first iteration, including the empty case.
5. Test interruptions and provider failures: earlier commits survive, the job does not falsely complete, and a repeated request is not described as resume. Set an explicit embedding timeout; the current Ollama POST has none.
6. Measure synthetic N/4N and large-artifact cases, then the pinned DocsGPT fixture under a declared memory ceiling in an isolated environment. Record complete normalized vector coverage and whole-run peak.

The architectural acceptance condition is **a known maximum live embedding working set and complete, unchanged output under a declared input/concurrency envelope**. Successful ingestion of one repository is necessary incident validation, but does not alone prove boundedness.
