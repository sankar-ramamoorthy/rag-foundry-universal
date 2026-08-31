# Tasks: WP-L6a — Language-Aware Retrieval Filter

**Input**: Design documents from `specs/003-language-aware-retrieval/`

**Tracking Issue**: #85
**Spec**: `specs/003-language-aware-retrieval/spec.md`
**Plan**: `specs/003-language-aware-retrieval/plan.md`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md (all present; no `contracts/` — the one API contract change, `RAGQuery.language`, is small enough to specify directly in tasks below rather than a separate contracts file)

**Tests**: Required by Constitution Principle VIII. Every implementation
task has a test task before or alongside it; all `pytest.mark.unit`, no
DB/Docker.

## Constitution Compliance

Plan.md's Constitution Check passed with one documented, justified
exception (deriving `language` centrally in `GraphAssembler` from file
suffix, rather than per-extractor metadata) — tracked in T004 below. No
task crosses a service/DB ownership boundary, changes retrieval/generation
architecture requiring evidence, or bypasses the issue/PR/test requirement.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Three services touched: `ingestion_service/`, `vector_store_service/`,
`rag_orchestrator/`, plus repo-root `migrations/versions/` — see plan.md's
Project Structure.

---

## Phase 1: Setup

- [x] T001 Confirm the migration chain head: `grep -H "^revision\|^down_revision" migrations/versions/*.py | tail -5` and verify `20260829_src_type` has no existing `down_revision` reference (research.md) before authoring the new migration in T008.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: language must exist on graph nodes and vector chunks before the retrieval-filter phase has anything to filter on.

- [x] T002 Add `LANGUAGE_BY_SUFFIX` constant (`.py`→`python`, `.ts`/`.tsx`→`typescript`, `.js`/`.jsx`/`.mjs`/`.cjs`→`javascript`) to `ingestion_service/src/core/codebase/graph_assembler.py`, module-level alongside the existing `DOCUMENTABLE_TYPES`/`INHERITABLE_TYPES` constants
- [x] T003 [P] Unit tests for `LANGUAGE_BY_SUFFIX` lookup behavior (recognized suffixes, unrecognized suffix → `None`, empty string → `None`) in `ingestion_service/tests/codebase/test_graph_assembler_language.py` (new file)
- [x] T004 In `GraphAssembler._lower_symbol` and `_lower_import` (`ingestion_service/src/core/codebase/graph_assembler.py`), add a top-level `"language"` key to the returned entity dict, derived via `LANGUAGE_BY_SUFFIX.get(Path(relative_path).suffix)` — mirrors the existing `doc_type` promotion pattern exactly (plan.md Constitution Exception)
- [x] T005 Unit tests: ingesting a mixed-suffix fixture (or reusing `ingestion_service/tests/fixtures/ts_repo/` plus one `.py` file) via `RepoGraphBuilder` produces `language="python"` on Python symbols, `language="typescript"`/`"javascript"` on the corresponding TS/JS symbols, and no `language` key on MARKDOWN_SECTION/EXTERNAL_MODULE/EXTERNAL_SYMBOL nodes, in `ingestion_service/tests/codebase/test_graph_assembler_language.py`
- [x] T006 Add `chunk.metadata["language"] = node.get("language")` in `_embed_repo_artifacts` (`ingestion_service/src/api/v1/codebase_ingest.py`, alongside the existing `chunk.metadata["doc_type"] = node.get("doc_type", "code")` line)
- [x] T007 [P] Add `"language"` to `PgVectorStore.TYPED_FILTER_COLUMNS` (`vector_store_service/src/core/vectorstore/pgvector_store.py`, currently `frozenset({"repo_id", "doc_type", "source_type"})`), add `language` to the `add()` INSERT column list + `%s` placeholder, and add `source_metadata.get("language")` to the typed-copy tuple (research.md's exact line references)
- [x] T008 [P] New Alembic migration `migrations/versions/20260831_add_language_typed_column.py` (revision `20260831_language_col`, `down_revision = "20260829_src_type"`) adding `language TEXT` to `ingestion_service.vector_chunks`, backfilling from `source_metadata->>'language'`, and creating `ix_vector_chunks_repo_language (repo_id, language)` + `ix_vector_chunks_language_col (language)` — exact structural mirror of `20260829_add_source_type_typed_column.py`, including a symmetric `downgrade()`
- [x] T009 [P] Unit tests for the new typed column in `vector_store_service/tests/core/vectorstore/test_typed_filter_columns.py`: `test_language_equality_uses_typed_column`, `test_in_operator_on_language_typed_column`, `test_ne_operator_on_language_typed_column` — mirrors the existing `doc_type`/`source_type` test triads exactly

**Checkpoint**: language exists end-to-end from extraction through the vector store schema; nothing filters on it yet.

---

## Phase 3: User Story 1 - Distinguish extraction failures from retrieval leakage (Priority: P1) 🎯 MVP

**Goal**: `/v1/rag` accepts an optional `language` field that scopes seed retrieval to one language, with zero change to unscoped behavior.

**Independent Test**: ingest a mixed-language repo, query scoped to each language, confirm sources never cross languages; query unscoped, confirm unchanged behavior.

### Tests for User Story 1

- [x] T010 [P] [US1] Unit tests in new `rag_orchestrator/tests/test_language_scoping.py` (mirrors `test_repo_scoping.py`'s `_run_hybrid_with_empty_store` harness, extended with an optional `language` kwarg): `test_seed_search_is_language_scoped_python`, `test_seed_search_is_language_scoped_typescript`, `test_seed_search_is_language_scoped_javascript`, `test_seed_search_has_no_language_key_when_omitted` (asserts the exact dict `{"source_type": "code", "repo_id": repo_id}` — no `language` key at all, not `language: None`)

### Implementation for User Story 1

- [x] T011 [US1] Add `language: Optional[str] = None` to `RAGQuery` in `rag_orchestrator/src/api/v1/models.py`
- [x] T012 [US1] Add `language=rag_query.language` to the `run_rag(...)` call in `rag_endpoint` (`rag_orchestrator/src/api/v1/routes.py`)
- [x] T013 [US1] Add `language: Optional[str] = None` parameter to `run_rag` (`rag_orchestrator/src/core/service.py`), threaded into its `hybrid_retrieve(...)` call
- [x] T014 [US1] Add `language: Optional[str] = None` parameter to `hybrid_retrieve` (`rag_orchestrator/src/core/service.py`); build the primary seed-search `metadata_filter` conditionally including `"language": language` only when truthy (data-model.md's exact dict shapes) — depends on T013
- [x] T015 [US1] Route-level test: `test_route_forwards_language` / `test_route_forwards_none_when_language_omitted` in `test_language_scoping.py`, mirroring `test_repo_scoping.py`'s `test_route_forwards_repo_id` pattern exactly (monkeypatch `routes.run_rag`, `TestClient(app)`, assert captured kwargs)

**Checkpoint**: User Story 1 fully functional — a mixed-language repo can be queried per-language via the API, unscoped behavior provably unchanged.

---

## Phase 4: User Story 2 - Language scope survives the fallback relaxation (Priority: P2)

**Goal**: when the primary seed search returns nothing and the existing `source_type` relaxation runs, an applied language scope is not silently dropped.

**Independent Test**: force an empty primary search result with a language scope applied; confirm the fallback payload still excludes other languages.

### Tests for User Story 2

- [x] T016 [P] [US2] `test_fallback_keeps_language_scope` in `test_language_scoping.py`, mirroring `test_repo_scoping.py`'s `test_fallback_relaxes_source_type_but_keeps_repo_scope`: assert the second (fallback) payload's `metadata_filter == {"repo_id": repo_id, "language": language}` (no `source_type` key, `language` key present)
- [x] T017 [P] [US2] `test_fallback_has_no_language_key_when_omitted` — the existing no-language fallback case (`{"repo_id": repo_id}` exactly) stays a passing regression check, not just inherited from `test_repo_scoping.py`

### Implementation for User Story 2

- [x] T018 [US2] In `hybrid_retrieve`'s fallback branch (`rag_orchestrator/src/core/service.py`, currently `payload["metadata_filter"] = {"repo_id": repo_id}`), rebuild the fallback filter conditionally including `"language": language` the same way the primary filter does (depends on T014)

**Checkpoint**: both user stories independently functional; language scoping is reliable even in the sparse-results fallback path.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [x] T019 Run every existing `rag_orchestrator` unit test (`uv run pytest -m unit` from `rag_orchestrator/`) and confirm `test_repo_scoping.py`'s exact `metadata_filter` dict-equality assertions still pass unchanged (Required Non-Regressions in plan.md)
- [x] T020 [P] Run every existing `vector_store_service` unit test and confirm all `test_typed_filter_columns.py` cases (existing + new) pass
- [x] T021 [P] Run every existing `ingestion_service` unit test, in particular `test_ts_repo_graph_golden.py`/`test_repo_graph_builder.py`, and confirm they remain green with the new `language` entity key present (Required Non-Regressions)
- [x] T022 Applied the new migration against a real `docker-compose.test.yml` Postgres (`alembic upgrade head`, verified resulting schema via `\d ingestion_service.vector_chunks`), confirmed `alembic downgrade -1` cleanly removes the column + both indexes, then re-upgraded to head
- [x] T023 [P] Updated `DOCS/audit/03-Multi-Language-Graph-Plan.md` §3 WP-L6 (retrieval-filter acceptance criteria checked off, Gradio dropdown noted as remaining) and `DOCS/audit/04-Scalability-Plan.md`'s WP-S4B entry (closes the loop on its own "language in a follow-up migration" note)
- [x] T024 Ran `vector_store_service/tests/core/vectorstore/test_ann_index_usage.py` (the real `docker-compose.test.yml`-backed integration suite CI's `integration-tests` job runs) against the migrated DB — **caught and fixed a real regression**: the new `(repo_id, language)` index changed the query planner's choice for two pre-existing `repo_id`+`doc_type`/`source_type` EXPLAIN-plan assertions (both tests hardcoded an index-name allow-list that didn't yet include the new index as an acceptable alternative, even though the underlying behavior — index-backed, no seq scan — was unaffected). Fixed by extending both allow-lists, and added three new tests (`test_language_filter_uses_typed_column_index`, `test_repo_language_filter_uses_typed_column_indexes`, `test_language_scoped_search_returns_only_that_language`) plus a language backfill assertion, mirroring the existing doc_type/source_type coverage exactly. The manual mixed-language-repo comparison in quickstart.md remains a documented follow-up (no such repo fixture exists in this environment yet).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — BLOCKS both user stories (nothing to filter on before `language` exists on nodes/chunks/columns)
- **User Story 1 (Phase 3)**: depends on Foundational only
- **User Story 2 (Phase 4)**: depends on Foundational and on T014 (US1's primary-filter implementation) since it edits the same function's fallback branch — this is a within-file sequencing dependency, not a cross-story design dependency (US2 is still independently testable once T014 lands)
- **Polish (Phase 5)**: depends on both user stories being complete

### Parallel Opportunities

- T003, T007, T008, T009 in parallel (Foundational, distinct files)
- T016, T017 in parallel (US2 tests, same new test file but independent test functions — verify no fixture collision before landing both)
- T020, T021, T023 in parallel (Polish, independent services/docs)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup → Phase 2 Foundational → Phase 3 (US1)
2. **STOP and VALIDATE**: `uv run pytest tests/test_language_scoping.py tests/test_repo_scoping.py -v` from `rag_orchestrator/` — per-language scoping works, existing repo-scoping regression tests still pass

### Incremental Delivery

1. Setup + Foundational → `language` flows end-to-end, nothing filters on it yet
2. + US1 → per-language retrieval scoping (MVP)
3. + US2 → scoping survives the fallback path
4. + Polish → full regression suite green, migration verified, docs updated
