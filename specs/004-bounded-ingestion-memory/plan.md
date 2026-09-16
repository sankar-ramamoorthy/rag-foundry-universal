# Implementation Plan: Bounded Ingestion Memory

**Branch**: `004-bounded-ingestion-memory` | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Tracking Issue**: #160

**Roadmap Context**: Not tied to a pre-existing roadmap phase — scoped directly from a confirmed live-incident postmortem.

**Input**: Feature specification from `specs/004-bounded-ingestion-memory/spec.md`

## Summary

Bound `ingestion_service`'s codebase-ingestion chunk→embed→persist stage so
its peak resident memory tracks a configured working-set size, not total
repo chunk count. The approach has two parts: (1) restructure
`_embed_repo_artifacts` to process embeddable nodes in bounded-size slices,
persisting each slice's vectors before starting the next, instead of
building one whole-repo `all_chunks`/`embeddings`/`records` set before any
persistence happens; and (2) source each slice's node text from a new paged
query against the already-committed `document_nodes` rows, rather than
reusing the in-memory `RepoGraph` entity list — this lets the graph-build
stage's memory be released before the embed stage's memory is allocated,
instead of the two being additive. No change to `IngestionPipeline`,
`OllamaEmbedder`, or `HttpVectorStore`'s internals is required — they
already accept arbitrary-sized chunk lists; only the caller's batching
behavior changes.

## Technical Context

**Language/Version**: Python 3.12 (`ingestion_service`)

**Primary Dependencies**: FastAPI, SQLAlchemy (`document_nodes` table),
`requests` (HTTP calls to `vector_store_service`'s `/v1/vectors/batch` and
Ollama's `/api/embed`) — all existing; no new dependency required.

**Storage**: PostgreSQL + pgvector — `document_nodes`
(`ingestion_service`-owned) for graph/text; vector tables remain owned by
`vector_store_service` as today. No schema change to existing columns; see
Data Model for the one new read-path query.

**Testing**: pytest, per `ingestion_service/pytest.ini`'s existing markers —
`unit` for the bounded-loop and paging-query logic (embedder/vector-store
mocked), `integration` for the DocsGPT-scale regression harness (requires
Postgres+pgvector; Ollama needed only if run against the real embedder
rather than a stub).

**Target Platform**: Linux Docker containers via `docker-compose.yml`,
CPython 3.12, single `ingestion_service` process with the existing
`threading.Thread` background-ingestion worker — unchanged by this feature.

**Project Type**: Existing multi-service web backend; this feature is
entirely internal to `ingestion_service`, no other service's code changes.

**Performance Goals**: N/A — this is a memory-boundedness and
completion-reliability fix, not a throughput target (spec Non-Goals). Wall-
clock time is recorded by the regression harness as an observed side effect,
not optimized for.

**Constraints**: Peak resident memory for chunk text, embedding vectors, and
persistence records during the chunk-embed-persist stage must be bounded by
a configured working-set size (FR-001); final persisted graph and vector
output for a given repo snapshot must be identical regardless of that size
(FR-007).

**Scale/Scope**: Must complete the `arc53/DocsGPT` snapshot from issue #160
(44,884 graph nodes, ~23,354 embeddable chunks) under the same memory
allocation that previously produced an OOM-kill (exit 137).

## Constitution Check

**GATE: Must pass before Phase 0 research and MUST be re-checked after
Phase 1 design.**

1. **Canonical identity / deterministic ingestion impact** — PASS. FR-007
   requires the final graph and vector output to be identical regardless of
   working-set size; the structural graph-resolution pass
   (`RepoGraphBuilder`/`GraphAssembler`) is untouched (FR-003). Principle I.
2. **Service and database boundary impact** — PASS, with one pre-existing
   caveat surfaced below (see Known Conflicts). All changes stay inside
   `ingestion_service`; no other service gains direct Postgres access; no
   service URL is hardcoded outside `shared/config/service_urls.py`.
3. **Retrieval/generation architecture change + evaluation evidence** — N/A.
   No chunking-semantics, embedding-model, or prompt/context-assembly change
   is made (FR-007 explicitly forbids output changes); Principle III's
   evidence gate governs quality changes, which this is not.
4. **Model-routing provenance/fallback non-regression** — N/A. No LLM/model-
   routing code is touched; ingestion makes no LLM calls (Principle I) and
   this feature doesn't change that.
5. **Embedding-index compatibility / re-embedding implications** — PASS. Same
   embedder, same model (`mxbai-embed-large`, 1024-dim), same vectors for a
   given input — only the batching of calls into it changes.
6. **GitHub issue traceability** — PASS. Tracking issue #160.
7. **ADR/audit references without restatement or conflict** — PASS. See
   Governing References in spec.md and Relevant ADRs below; no restatement.
8. **Test and evaluation obligations** — PASS. Acceptance criteria are
   observable (ingestion status, vector count, memory bound) per Principle
   VIII; no RAG-quality evaluation-methodology gate applies (same reasoning
   as #3). A regression/benchmark harness is defined in quickstart.md.

**Post-Phase-1 re-check**: Design artifacts (research.md, data-model.md,
contracts/status-endpoint.md, quickstart.md) introduce one new read query
against the existing `document_nodes` table and one additive, optional field
on an existing status endpoint — no new table, no schema migration, no new
service, no change to embedding model/chunking semantics, no retrieval/
generation behavior change. All eight items above still hold; no new
EXCEPTION REQUIRED entries. `embed_progress` reuses the existing
`ingestion_metadata` JSON column (already used by `mark_failed`) rather than
adding a column, keeping this a code-only change to `ingestion_service`.

## Architecture Impact

**Services touched**:
- `ingestion_service` only.

**Database ownership impact**:
- None. No new tables; no schema change. One new **read-path query** against
  the existing `document_nodes` table (paged, filtered by `repo_id`) — see
  Data Model.

**Public/API contract impact**:
- Additive only: `GET /v1/codebase/ingest-repo/{ingestion_id}` gains
  optional progress fields (see contracts/status-endpoint.md). No existing
  field changes meaning or is removed.

**Canonical identity / graph impact**:
- None (FR-003, FR-007).

**Embedding/index impact**:
- None — same model, same dimension, same per-chunk vectors.

**Model-routing impact**:
- N/A.

**Relevant ADRs**:
- ADR-030 (repo scoping / rebuild determinism)
- ADR-038 (pipeline construction ownership)
- ADR-039 / ADR-040 (artifact-level embedding strategy)
- ADR-041 (text persisted on `DocumentNode.text`)

**Known conflicts**:
- `ingestion_service/src/api/v1/codebase_ingest.py`'s `_build_pipeline()` (and
  its duplicate in `ingest.py`) constructs `IngestionPipeline`, the embedder,
  and the vector store directly in an API module — the code's own comment
  marks this `# Temporary pipeline builder (TECH DEBT - see issue)`, but no
  `pipeline_factory.py` exists yet and no tracking issue number is present in
  that comment. This is a **pre-existing** gap against ADR-038/Principle II,
  not introduced or worsened by this feature: this plan's changes are
  confined to `_embed_repo_artifacts`'s internal batching logic and a new
  persistence-layer read method, and do not add a new direct-construction
  call site. Fixing it is out of scope here and should be tracked as its own
  issue if the project wants it addressed — surfaced per Governance's
  conflict-disclosure requirement, not silently resolved either way.

## Evaluation Plan

**Evaluation required**: No.

**Reason**: Principle III/VIII's RAG-quality evaluation-methodology gate
governs retrieval/ranking/generation quality changes. This feature holds
chunking, embedding model, and retrieval/generation behavior fixed (FR-007)
— it changes memory lifetime and call batching only. The applicable
acceptance mechanism instead is the regression/benchmark harness in
quickstart.md (observable behavior: completion status, vector count, memory
bound — per Principle VIII's test-guided-development requirement, not the
RAG-quality methodology).

## Required Non-Regressions

- Existing `RepoGraphBuilder`/`GraphAssembler`/`symbol_table` tests remain
  green — the structural graph pass is untouched.
- The single-artifact pipeline entry points (`IngestionPipeline.run()`,
  `run_with_chunks()`, `run_with_sections()`), used by document/PDF/Markdown
  ingestion, are unaffected — this feature only changes the whole-repo
  codebase path (`_embed_repo_artifacts`).
- `IngestionPipeline.embed_and_persist_batch()`, `OllamaEmbedder.embed()`
  (`OLLAMA_BATCH_SIZE`), and `HttpVectorStore.persist_batch()`
  (`PERSIST_BATCH_SIZE`) keep their current signatures and internal
  HTTP-batching behavior unchanged — the working-set slice is an outer loop
  around these, not a rewrite of them (see research.md).
- `CodebaseGraphPersistence.get_canonical_id_map()` continues to be used
  as-is (it already selects only two short columns — confirmed not a memory
  concern at DocsGPT scale; see research.md).
- `DELETE /v1/repos/{repo_id}` (#158/PR #159) and the Gradio delete button
  (#162/PR #163) continue to work unchanged — this feature does not touch
  deletion paths.

## Project Structure

### Documentation (this feature)

```text
specs/004-bounded-ingestion-memory/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output (includes the regression/benchmark harness)
├── contracts/
│   └── status-endpoint.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
ingestion_service/src/api/v1/codebase_ingest.py       # _embed_repo_artifacts restructured into a bounded per-slice loop; status response model gains progress fields
ingestion_service/src/core/codebase/codebase_persistence.py  # new paged read method for embeddable nodes
ingestion_service/src/core/status_manager.py          # progress recording (reuses existing ingestion_metadata JSON column)
ingestion_service/tests/api/                          # new unit tests for the bounded loop
ingestion_service/tests/codebase/                     # new unit tests for the paged query
ingestion_service/tests/integration/                  # new DocsGPT-scale regression/benchmark harness (marker: integration)
docker-compose.yml                                    # optional: mem_limit backstop for ingestion_service (FR-006, secondary, not the primary mechanism)
```

**Structure Decision**: All changes stay inside `ingestion_service`, extending
its existing `codebase_ingest.py` / `codebase_persistence.py` /
`status_manager.py` modules rather than introducing new ones — consistent
with Constitution Principle II (no new service boundary) and with how prior
incremental work in this codebase (e.g. WP-L2–L4 extractor additions) has
extended existing modules rather than creating parallel structures.
`IngestionPipeline`, `OllamaEmbedder`, and `HttpVectorStore` are not
modified — see Summary and research.md for why the existing interfaces
already suffice once the caller batches correctly.

## Constitution Exceptions / Complexity Tracking

None. No Constitution Check item above resulted in EXCEPTION REQUIRED. The
pre-existing `_build_pipeline()`/ADR-038 gap noted under Known Conflicts is
disclosed, not an exception this plan is requesting — this plan neither
relies on nor worsens it.
