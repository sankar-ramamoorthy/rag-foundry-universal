# Phase 0 Research: Bounded Ingestion Memory

No `[NEEDS CLARIFICATION]` markers were left in the Technical Context — this
document instead resolves the design questions FR-001 raises once you try to
make "peak memory proportional to batch size, not repo size" literally true
rather than approximately true. Each decision traces to a specific
create/retain/release point identified by re-reading the current pipeline
(`ingestion_service/src/core/codebase/repo_graph_builder.py`,
`ingestion_service/src/api/v1/codebase_ingest.py`,
`ingestion_service/src/core/pipeline.py`,
`ingestion_service/src/core/http_vectorstore.py`,
`shared/embedders/ollama.py`) during this investigation (issue #160).

## Current memory ownership map (as-is, verified against source)

| Stage | Structure | Created | Retained until | Scales with |
|---|---|---|---|---|
| `RepoGraphBuilder.build()` | `extracted_files` (source text + IR per file) | Walking the repo (`build()` line ~212-230) | `build()` returns (local var, refcounted away) | total repo file count/size |
| `GraphAssembler.assemble()` | `RepoGraph` entities (incl. `text` per node) | During `assemble()` | Returned to caller — see next row | total repo node count |
| `_background_ingest_repo` | `repo_graph` / `nodes = repo_graph.all_entities()` | After `builder.build()` returns | Held in a local variable for the **rest of the function** — through `persist_graph()` and all of `_embed_repo_artifacts()` | total repo node count (≈34MB text at DocsGPT scale) |
| `_embed_repo_artifacts` | `all_chunks`, `document_ids` | Iterating **all** of `nodes` before calling `embed_and_persist_batch` once | Until `embed_and_persist_batch` returns | total repo embeddable-chunk count |
| `OllamaEmbedder.embed()` | `texts` (truncated copies), `embeddings` (accumulated via `.extend()` across every `OLLAMA_BATCH_SIZE` HTTP call) | Per call to `_embed()` | Until `embed()` returns — `OLLAMA_BATCH_SIZE` bounds only the outbound HTTP payload, never this list | total chunks passed in (today: whole repo) |
| `HttpVectorStore.persist_batch` | `records` (chunk text duplicated again via `_build_record`'s `chunk_text`) | Before the `PERSIST_BATCH_SIZE`-sliced send loop | Until `persist_batch` returns — same pattern: batching bounds wire size only | total chunks passed in (today: whole repo) |

Peak point today: immediately before `persist_batch`'s send loop starts,
`nodes`, `all_chunks`, `texts`, `embeddings`, and `records` are all
simultaneously resident — one base copy of repo text plus up to four
derived copies/expansions of it, all sized by total repo chunk count.

## Decision 1: What "bounded by working-set size" actually bounds

**Decision**: FR-001's bound applies to the chunk-embed-persist working
state (`all_chunks`, `texts`, `embeddings`, `records`) — the structures that
today are built once for the *entire* repo before any persistence happens.
It does not require the structural graph-build stage
(`RepoGraphBuilder`/`GraphAssembler`) to also process in slices; FR-003
explicitly requires that stage to remain a single repo-wide pass, since
cross-file symbol/import/call resolution needs repo-wide structural
knowledge no per-file or per-slice view can supply (this is the same
tradeoff issue #160 itself flagged: "do not assume file-by-file streaming is
automatically safe... cross-file resolution may require repository-wide
structural indexes").

**Rationale**: The four-to-five-times duplication in the chunk-embed-persist
stage (see table above) is unbounded *and* multiplicative — it grows with
total chunk count on every one of four structures at once. The graph-build
stage's `nodes`/text residency is a single, non-multiplied copy, and
required by FR-003 to stay repo-wide. Trying to bound both stages
identically would either violate FR-003 or fail to fix the actual
multiplicative blowup that caused the OOM.

**Alternatives considered**:
- *Bound everything, including the structural pass, to per-file slices*:
  rejected — breaks cross-file symbol resolution (FR-003), and the DocsGPT
  incident's own evidence shows the structural pass was not what OOM'd (it
  completed; the failure was after it).
- *Leave the structural pass's `nodes` residency completely out of scope*:
  considered, but see Decision 2 — its residency can be made non-additive
  with the embed stage's residency without touching the structural pass
  itself.

## Decision 2: Sequencing the two stages so their peaks don't add

**Decision**: The chunk-embed-persist stage sources each slice's node data
(canonical_id, text, relative_path, doc_type) from a **new paged query**
against the already-committed `document_nodes` rows
(`persist_graph()` commits before `_embed_repo_artifacts` is called), rather
than continuing to iterate the in-memory `nodes` list built during the graph
pass. `repo_graph`/`nodes` becomes eligible for release as soon as
`persist_graph()` returns, before the embed stage allocates anything.

**Rationale**: Without this, slicing only the *iteration* over `all_chunks`
construction still leaves the full `nodes` list (all repo text) resident for
the whole embed stage, because slicing a `for` loop doesn't release memory
the list backing it already holds. That would make peak memory
`nodes_size + slice_size` — smaller than today's
`nodes_size + all_chunks_size + texts_size + embeddings_size + records_size`,
but still growing with total repo size via the `nodes_size` term, which
would make SC-002 (peak memory not scaling linearly with chunk count) false
for large enough repos. Re-querying already-persisted rows in pages turns
the two stages into **sequential** peaks (`max(graph-build peak, embed-slice
peak)`) instead of an **additive** one (`graph-build peak + embed-slice
peak`), and makes the embed stage's own peak depend only on slice size —
literally satisfying FR-001, not just approximately.

**Alternatives considered**:
- *Keep iterating the in-memory `nodes` list, `del` chunks/embeddings/records
  per slice*: rejected — reduces the 4-5x multiplication (a real win) but
  leaves the base `nodes` residency proportional to repo size, undermining
  the "not repo size" half of FR-001/SC-002.
- *Stream node text during the graph-build walk itself, never materializing
  `nodes` in memory*: rejected as out of scope — `GraphAssembler` needs the
  full in-memory entity set for symbol-table construction and cross-file
  resolution (FR-003); changing that is a structural-pass redesign this
  feature explicitly does not undertake.
- *Have `persist_graph()` return only lightweight identity data (no `text`)
  and always re-query text later*: this is effectively what Decision 2
  does, scoped specifically to the embed stage's consumption rather than
  changing what `persist_graph()`/`all_entities()` return more broadly
  (which other, unrelated call sites may still depend on).

## Decision 3: `language` is not a persisted column — reconstruct it, don't add one

**Decision**: The paged query selects `canonical_id`, `document_id`,
`relative_path`, `doc_type`, and `text` from `document_nodes`; `language` is
re-derived from `relative_path`'s suffix using the same mapping
`GraphAssembler` already uses (`LANGUAGE_BY_SUFFIX`), rather than added as a
new persisted column.

**Rationale**: Verified against `shared/models/document_node.py` — there is
no `language` column; `_embed_repo_artifacts` currently gets `language` from
the in-memory entity dict, which `GraphAssembler` populated via a pure
function of `relative_path`. No schema migration is needed to preserve this
metadata on chunks once the embed stage switches to a DB-sourced page.

**Alternatives considered**:
- *Add a `language` column and backfill it*: rejected as unnecessary schema
  churn — the value is a pure, cheap function of an already-selected column.

## Decision 4: `get_canonical_id_map()` stays a single repo-wide query

**Decision**: `CodebaseGraphPersistence.get_canonical_id_map()` is retired in
favor of the paged query itself returning `document_id` per row directly
(Decision 2's page already needs `canonical_id → document_id` to build each
chunk's metadata, so a separate whole-repo map becomes redundant rather than
merely "safe to keep").

**Rationale**: Re-checked against source
(`ingestion_service/src/core/codebase/codebase_persistence.py:218-228`):
the existing map query selects exactly two short string columns
(`canonical_id`, `document_id`) for every row — at DocsGPT scale (44,884
rows) this is on the order of a few MB, not a contributor to the OOM. It was
a reasonable thing to keep unchanged (per the spec's Assumptions). Once the
embed stage pages `document_nodes` directly, though, each page's rows
already carry their own `document_id` — building a second, separate
repo-wide structure with the same information is pure redundancy, not a
memory-safety requirement. Removing it slightly simplifies the design
without weakening the memory-boundedness argument.

## Decision 5: Working-set size is a single new setting, not per-call-site tuning

**Decision**: One new setting (e.g. `INGESTION_EMBED_BATCH_SIZE`, exact name
finalized in tasks) controls the paged query's page size and therefore the
size of `all_chunks`/`embeddings`/`records` per slice. It is independent of
`OLLAMA_BATCH_SIZE` (HTTP request size to Ollama) and `PERSIST_BATCH_SIZE`
(HTTP request size to `vector_store_service`) — those remain inner batching
details nested inside one outer working-set slice, unchanged (FR-004,
Required Non-Regressions).

**Rationale**: Conflating the working-set size with either inner HTTP-batch
size would re-couple "how much memory is resident at once" with "how big one
HTTP request is," which is exactly the confusion issue #160 identified
(`OLLAMA_BATCH_SIZE`/`PERSIST_BATCH_SIZE` already exist today and did not
prevent the OOM, because they only ever bounded request size, not the
surrounding Python lists). Keeping them as independent, nested settings
means the outer slice size can be tuned for memory while the inner HTTP
batch sizes stay tuned for network/provider throughput.

**Alternatives considered**:
- *Repurpose `OLLAMA_BATCH_SIZE` as the working-set size*: rejected — it is
  read by `OllamaEmbedder`, which has no visibility into vector-store
  persistence or DB paging; overloading its meaning would make the two
  concerns (HTTP request size vs. process memory bound) inseparable again.

## Decision 6: Regression/benchmark harness shape

**Decision**: Two fixtures, not one — (a) the real `arc53/DocsGPT` snapshot
from issue #160 as the authoritative real-world reproduction, run against a
memory ceiling matched to the one that produced the original OOM; and (b) a
smaller synthetic fixture with a configurable, comparable chunk count for
fast local/CI iteration that doesn't depend on cloning a large external repo
on every run. Both are driven through the same harness: ingest, poll
resident memory of the `ingestion_service` process for the run's duration,
and assert on final state (status, node count, vector count) plus the
memory-vs-chunk-count relationship. Full harness steps are in
`quickstart.md`, per the project's existing measure-first approach
(`DOCS/audit/04-Scalability-Plan.md`) rather than an unverified scaling
claim.

**Rationale**: The real repo is the only fixture that actually reproduces
the incident end-to-end (real file mix, real symbol density, real embedding
call latency); the synthetic fixture is what makes "peak memory doesn't grow
linearly with chunk count" (SC-002) checkable in CI without a slow external
clone every run, and without depending on GitHub availability.

**Alternatives considered**:
- *Real repo only*: rejected as the sole fixture — too slow/network-
  dependent for routine CI, and doesn't let SC-002's growth-rate claim be
  checked at multiple chunk counts on demand.
- *Synthetic fixture only*: rejected as the sole fixture — risks the
  harness passing on a corpus shape that doesn't resemble the actual
  incident (e.g. DocsGPT's ~48% empty-text node ratio, mixed Python/TS/docs
  file types).
