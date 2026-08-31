# Implementation Plan: WP-L6a — Language-Aware Retrieval Filter

**Branch**: `feat/wp-l6a-language-aware-retrieval-issue-85` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Tracking Issue**: #85

**Roadmap Context**: Phase 3, pulled forward from WP-L6 per
`DOCS/audit/03-Multi-Language-Graph-Plan.md` §3.

**Input**: Feature specification from `specs/003-language-aware-retrieval/spec.md`

## Summary

Add a dedicated `language` value to code graph nodes (derived from file
suffix in `GraphAssembler`, not from per-extractor metadata — see
Constitution Exceptions), carry it through embedding into vector chunk
`source_metadata`, promote it to a typed indexed column on `vector_chunks`
(the fourth column WP-S4B already anticipated but never implemented), and
let `/v1/rag` accept an optional `language` field that scopes the seed
vector search and survives the existing `source_type`-relaxation fallback.

## Technical Context

**Language/Version**: Python 3.10-3.12 (`ingestion_service`), 3.12
(`vector_store_service`, `rag_orchestrator` — per each service's own
`pyproject.toml`).

**Primary Dependencies**: No new dependencies. Alembic (existing) for the
new migration; psycopg (existing) for the typed-column write/filter path;
FastAPI/Pydantic (existing) for the `/v1/rag` request model.

**Storage**: `ingestion_service.vector_chunks` (Postgres+pgvector) gains
one new `TEXT` column (`language`) plus a `(repo_id, language)` composite
index, following the exact precedent of `migrations/versions/
20260719_typed_filter_columns.py` and `20260829_add_source_type_typed_column.py`.
No change to `document_nodes` — the spec's acceptance criteria only require
language on vector chunks and the retrieval filter, not a graph-storage
column (confirmed: `shared/models/document_node.py` is out of scope).

**Testing**: `pytest`, `pytest.mark.unit` (no DB/Docker) in both
`vector_store_service/tests/core/vectorstore/test_typed_filter_columns.py`
(new tests appended) and a new `rag_orchestrator/tests/test_language_scoping.py`
mirroring `rag_orchestrator/tests/test_repo_scoping.py`'s exact style
(monkeypatched `httpx.AsyncClient` capturing payloads; `TestClient` for the
route layer).

**Target Platform**: No change — same three services, same Docker/Postgres
setup.

**Project Type**: Backend services (extraction/graph layer in
`ingestion_service`, storage layer in `vector_store_service`, retrieval
layer in `rag_orchestrator`) — no UI change (Non-Goals).

**Performance Goals**: N/A beyond "stays as fast as the existing
`repo_id`/`doc_type`/`source_type` typed-column filters" — same query
shape, same index strategy.

**Constraints**: Must not change behavior for any query that omits
`language` (spec FR-006, SC-002, SC-004) — this is the primary regression
risk and gets its own explicit test.

**Scale/Scope**: One migration, one new module-level constant + 2-3 line
change in `GraphAssembler`, a 4-line change in `codebase_ingest.py`, a
1-line change + 1 new frozenset entry in `pgvector_store.py`, a new
optional Pydantic field + 2 call-site threads in `rag_orchestrator`. No
new files except the migration and the new test file.

## Constitution Check

**GATE: Must pass before Phase 0 research and MUST be re-checked after
Phase 1 design.**

1. Canonical identity / deterministic ingestion impact — PASS. `language`
   is metadata only, never part of `canonical_id` (ADR-031) or the
   module-path/import-resolution logic (ADR-032) — confirmed by design:
   it's derived read-only from `relative_path`'s suffix, the same input
   `build_canonical_id` already uses, so it can never cause a rebuild-time
   identity or determinism difference (ADR-036).
2. Service and database boundary impact — PASS. The new column lives in
   `vector_store_service`'s own table (`ingestion_service.vector_chunks`,
   owned per Constitution Principle II's stated exception for
   `vector_store_service`'s own tables); `ingestion_service` continues to
   write to it only via the existing HTTP `/v1/vectors/batch` call, never
   direct DB access.
3. Retrieval/generation architecture change + evaluation evidence — N/A
   per spec's Evaluation Evidence section: this is an optional,
   off-by-default metadata filter on an existing search, not a ranking,
   hybrid-strategy, chunking, embedding, or prompt-assembly change.
4. Model-routing provenance/fallback non-regression — N/A, no model
   routing code touched.
5. Embedding-index compatibility — PASS/N/A. No embedding model change;
   `language` is a filter key alongside existing ones, not a change to
   what gets embedded or how.
6. GitHub issue traceability — PASS. Tracking issue #85.
7. ADR/audit references without restatement or conflict — PASS. See
   Relevant ADRs below.
8. Test and evaluation obligations — PASS. Principle VIII satisfied by
   the unit tests in Success Criteria/tasks.md; Principle III N/A per
   item 3.

One EXCEPTION REQUIRED item — see **Constitution Exceptions / Complexity
Tracking** below.

## Architecture Impact

**Services touched**:
- `ingestion_service` (`src/core/codebase/graph_assembler.py`,
  `src/api/v1/codebase_ingest.py`)
- `vector_store_service` (`src/core/vectorstore/pgvector_store.py`, new
  Alembic migration)
- `rag_orchestrator` (`src/api/v1/models.py`, `src/api/v1/routes.py`,
  `src/core/service.py`)

**Database ownership impact**:
- Additive column + index on `vector_store_service`'s own
  `vector_chunks` table (owned per Constitution Principle II's stated
  vector-store exception). No new table, no cross-service DB access.

**Public/API contract impact**:
- `POST /v1/rag` (rag_orchestrator): new optional request field
  `language: Optional[str] = None`. Fully backward compatible — omitting
  it is the existing behavior exactly (FR-006).
- No change to `/v1/rag/simple`, `/v1/vectors/search`'s schema (its
  `metadata_filter: Optional[Dict[str, Any]]` is already fully generic —
  no schema change needed there, only a new key value flowing through
  it), or `/v1/vectors/batch`'s schema (same reasoning: `source_metadata`
  is already an opaque dict).

**Canonical identity / graph impact**:
- None (see Constitution Check item 1).

**Embedding/index impact**:
- None to the embedding model. New Postgres btree index
  `ix_vector_chunks_repo_language` (naming mirrors
  `ix_vector_chunks_repo_doc` / `ix_vector_chunks_repo_source_type`).

**Model-routing impact**:
- None.

**Relevant ADRs**:
- ADR-030 (unified artifact graph), ADR-031 (canonical identity —
  language is metadata, confirmed not identity-bearing), ADR-045 (hybrid
  vector+graph RAG pipeline — this feature adds one optional filter key
  to its existing seed-search step, no change to the BFS expansion logic
  itself)

**Known conflicts**:
- None.

## Evaluation Plan

**Evaluation required**: No
**Reason**: Principle III/VIII applicability — see spec.md's Evaluation
Evidence section. A manual filtered-vs-unfiltered comparison against a
real mixed-language repo is documented in `quickstart.md` as a follow-up
validation exercise supporting WP-L2 confidence-building, not a
merge-blocking evaluation artifact.

## Required Non-Regressions

- Every existing `rag_orchestrator` test remains green, in particular
  `test_repo_scoping.py`'s `test_seed_search_is_repo_scoped` and
  `test_fallback_relaxes_source_type_but_keeps_repo_scope` — the
  `metadata_filter` dict shape they assert on must stay exactly
  `{"source_type": "code", "repo_id": repo_id}` / `{"repo_id": repo_id}`
  when `language` is not passed (dict key must not appear with a `None`
  value, or these exact-equality assertions break — confirmed by reading
  both tests' `assert payloads[...]["metadata_filter"] == {...}` exact-dict
  comparisons).
- Every existing `vector_store_service` `test_typed_filter_columns.py`
  test remains green — `TYPED_FILTER_COLUMNS` gains one entry, no existing
  entry's behavior changes.
- Existing ingestion tests (`ingestion_service/tests/codebase/test_ts_repo_graph_golden.py`,
  `test_repo_graph_builder.py`, etc.) continue to pass; adding a
  `language` key to entity dicts must not break any test that does exact
  dict-equality or exact-key-set assertions on entities — checked directly
  during implementation (Phase 3 below) since some existing WP-L2 golden
  tests assert `(artifact_type, canonical_id)` tuples only, not whole-dict
  equality, so they're unaffected — confirmed by reading
  `test_ts_repo_graph_golden.py`'s `_entity_inventory` helper, which
  projects only `artifact_type`/`canonical_id`.

## Project Structure

### Documentation (this feature)

```text
specs/003-language-aware-retrieval/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
ingestion_service/
├── src/core/codebase/graph_assembler.py     # + LANGUAGE_BY_SUFFIX, + language on lowered entities
└── src/api/v1/codebase_ingest.py            # + chunk.metadata["language"] = node.get("language")

vector_store_service/
├── src/core/vectorstore/pgvector_store.py   # + "language" in TYPED_FILTER_COLUMNS, + INSERT column
└── tests/core/vectorstore/test_typed_filter_columns.py   # + language typed-column tests

migrations/versions/
└── <new>_add_language_typed_column.py       # NEW — mirrors 20260829_add_source_type_typed_column.py

rag_orchestrator/
├── src/api/v1/models.py                     # + RAGQuery.language: Optional[str] = None
├── src/api/v1/routes.py                     # + language=rag_query.language
├── src/core/service.py                      # + run_rag(language=...), hybrid_retrieve(language=...)
└── tests/test_language_scoping.py           # NEW — mirrors test_repo_scoping.py
```

**Structure Decision**: All three touched services already own the exact
files being changed (no new service, no new module boundary). The new
Alembic migration lives in the existing repo-root `migrations/versions/`
directory alongside every prior typed-filter-column migration it mirrors.

## Constitution Exceptions / Complexity Tracking

| Principle / Constraint | Proposed Exception or Added Complexity | Why Necessary | Simpler Compliant Alternative Rejected Because |
|-------------------------|------------------------------------------|----------------|--------------------------------------------------|
| WP-L1/WP-L2's established pattern of extractors setting their own metadata (`doc_type` is set per-extractor, e.g. `PythonASTExtractor`'s `DEFAULT_DOC_TYPE`) | `language` is instead derived centrally in `GraphAssembler` from `relative_path`'s file suffix (a new `LANGUAGE_BY_SUFFIX` constant), not set by each extractor | The plan doc's own WP-L6 directive says "assembler sets it from extractor," but a file's language is intrinsic to its path — the exact same input `ModulePathConvention`/`CompositeModuleConvention` (WP-L2) already dispatches on. Deriving centrally means zero changes to `python_extractor.py` or `treesitter/typescript.py`, and guarantees Python/TS/JS can never disagree on the string spelling of their own language (a real risk if three extractor files each hand-wrote `"language": "python"` independently) | Adding `metadata["language"]` to every `SymbolRecord`/`ImportRecord` construction site in both existing extractors was considered and rejected: it's strictly more code (touching two extractor files instead of one assembler constant), for a value that's 100% determined by the file suffix the assembler already has in hand — the extractor doesn't know anything about its own language that the assembler couldn't derive itself from the very `relative_path` it's already being called with |

This is additive-only (a new constant + a few lines reading it), not a
change to any existing resolution algorithm, and follows exactly the
precedent WP-L2's plan.md itself set for justified, minimal exceptions to
a stated ideal.
