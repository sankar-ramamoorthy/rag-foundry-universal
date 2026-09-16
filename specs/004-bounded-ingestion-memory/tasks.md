---

description: "Task list for Bounded Ingestion Memory"
---

# Tasks: Bounded Ingestion Memory

**Input**: Design documents from `specs/004-bounded-ingestion-memory/`

**Tracking Issue**: #160
**Spec**: `specs/004-bounded-ingestion-memory/spec.md`
**Plan**: `specs/004-bounded-ingestion-memory/plan.md`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/status-endpoint.md, quickstart.md — all present.

**Tests**: Required by Constitution Principle VIII. Each user story below
includes skeletal test tasks before or alongside its first implementation
task. This feature does not touch retrieval, ranking, generation, or
chunking/embedding *semantics* (spec.md's Evaluation Evidence: No; plan.md's
Evaluation Plan: No) — the Principle III/VIII RAG-quality evaluation
methodology does not apply, so no separate "Evaluation & Evidence" phase is
included. FR-001/SC-001/SC-002's measure-first acceptance criteria are
instead covered by the quickstart.md regression/benchmark harness tasks
inside User Story 1.

**Organization**: Tasks are grouped by user story (spec.md) to enable
independent implementation and testing of each.

## Constitution Compliance

plan.md's Constitution Check passed all 8 applicable items both pre- and
post-Phase-1 design, with no EXCEPTION REQUIRED entries. One pre-existing,
undisclosed-elsewhere gap (`_build_pipeline()` bypassing a not-yet-existing
`pipeline_factory.py`) was surfaced under plan.md's Known Conflicts as
out of scope for this feature — no task below touches pipeline construction,
so it is not re-litigated here.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, or US3 (spec.md priorities P1/P2/P3)
- File paths are exact, per plan.md's Project Structure.

---

## Phase 1: Setup

**Purpose**: Environment plumbing for the new working-set-size setting,
before any code references it.

- [ ] T001 [P] Add an `INGESTION_EMBED_BATCH_SIZE` entry (with an inline
      comment noting it is independent of `OLLAMA_BATCH_SIZE` and
      `PERSIST_BATCH_SIZE`, per research.md Decision 5) to `.env.example`,
      and pass it through in `docker-compose.yml`'s `ingestion_service`
      `env_file`/`environment` block and `.env.test`, so integration tests
      and the benchmark harness can override it per run.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure every user story's bounded-loop work
depends on. No user story task below may start until this phase is done.

**⚠️ CRITICAL**: Phase 3+ cannot begin until T002-T005 are complete.

- [ ] T002 [P] Add the `INGESTION_EMBED_BATCH_SIZE` field (int, sensible
      default, e.g. 200-500 embeddable nodes per slice — exact default is
      an implementation choice, tune during T014) to the `Settings` class in
      `ingestion_service/src/core/config.py`.
- [ ] T003 [P] Extract `LANGUAGE_BY_SUFFIX` and `_language_for_path` from
      `ingestion_service/src/core/codebase/graph_assembler.py` into a new
      shared module, e.g.
      `ingestion_service/src/core/codebase/language_by_suffix.py`, and
      import it back into `graph_assembler.py` with no behavior change
      (research.md Decision 3) — this lets the new paged query (T004)
      reconstruct `language` from `relative_path` without duplicating the
      mapping.
- [ ] T004 Add `count_embeddable_nodes(repo_id) -> int` and
      `iter_embeddable_node_pages(repo_id, page_size)` (keyset-paginated by
      `document_id`; selects `document_id`, `canonical_id`, `relative_path`,
      `doc_type`, `text`; filters `repo_id` match and non-null/non-empty
      `text`) to `CodebaseGraphPersistence` in
      `ingestion_service/src/core/codebase/codebase_persistence.py`
      (data-model.md "Embeddable Node Page").
- [ ] T005 [P] Unit tests for `count_embeddable_nodes` and
      `iter_embeddable_node_pages` in
      `ingestion_service/tests/codebase/test_codebase_persistence_paging.py`
      — cover pagination across page-size boundaries, empty/NULL-text
      exclusion, keyset-ordering stability (no skipped/duplicated rows
      across pages), and that the count matches the sum of all pages' row
      counts.

**Checkpoint**: Foundation ready — User Stories 1, 2, and 3 can now proceed
(US2 and US3 both build on US1's bounded loop, so in practice implement
US1 first; see Dependencies below).

---

## Phase 3: User Story 1 - Large repo ingests without exhausting memory (Priority: P1) 🎯 MVP

**Goal**: `ingestion_service` processes a repo's chunk-embed-persist stage in
bounded-size slices so peak memory tracks the configured working-set size,
not total repo chunk count, and a DocsGPT-scale repo completes successfully
under the memory allocation that previously OOM-killed it.

**Independent Test**: Re-ingest the `arc53/DocsGPT` snapshot (or the
synthetic Fixture B at an equivalent scale) under the original OOM-inducing
memory allocation and confirm `status: "completed"` with a full vector set
(spec.md Acceptance Scenario 1).

### Tests for User Story 1

- [ ] T006 [P] [US1] Unit test in
      `ingestion_service/tests/api/test_embed_repo_artifacts_bounded.py`:
      mock `CodebaseGraphPersistence.iter_embeddable_node_pages` (T004) and
      `IngestionPipeline.embed_and_persist_batch`; assert
      `embed_and_persist_batch` is called once per page, each call's
      `chunks` list length never exceeds `INGESTION_EMBED_BATCH_SIZE`
      (T002), and the total chunks across all calls equals the total
      embeddable nodes.
- [ ] T007 [P] [US1] Unit test in
      `ingestion_service/tests/api/test_embed_repo_artifacts_metadata_parity.py`:
      for a fixed set of fake node rows, assert the bounded loop's emitted
      chunk metadata (`canonical_id`, `repo_id`, `relative_path`,
      `doc_type`, `language` via T003's helper,
      `source_metadata.canonical_id`) is byte-identical to today's
      pre-change `_embed_repo_artifacts` output for the same input (FR-007
      parity check at the unit level).
- [ ] T008 [US1] Integration test (marker: `integration`) in
      `ingestion_service/tests/integration/test_bounded_ingest_repo.py`:
      against `docker-compose.test.yml`'s Postgres, ingest a small
      multi-page fixture repo twice at two different
      `INGESTION_EMBED_BATCH_SIZE` values and assert identical final
      `document_nodes` counts, relationship counts, and vector counts
      (FR-007).

### Implementation for User Story 1

- [ ] T009 [US1] Restructure `_embed_repo_artifacts` in
      `ingestion_service/src/api/v1/codebase_ingest.py` into a bounded loop
      over `CodebaseGraphPersistence.iter_embeddable_node_pages()` (T004):
      for each page, build `chunks`/`document_ids` (same per-chunk metadata
      logic as today, using T003's language helper), call
      `pipeline.embed_and_persist_batch()` once per page, and accumulate
      `chunks_persisted`/`skipped_missing` totals across pages before
      returning (same return shape as today).
- [ ] T010 [US1] Update `_background_ingest_repo` in the same file so
      `repo_graph`/`nodes` are not passed into or referenced by
      `_embed_repo_artifacts` — call the restructured function with
      `repo_id`/`ingestion_id` (and `count_embeddable_nodes`'s result, for
      T022 later) only, so `repo_graph`/`nodes` become eligible for release
      once `persist_graph()` returns, before the embed stage allocates
      anything (research.md Decision 2).
- [ ] T011 [US1] Remove the `get_canonical_id_map()` call from
      `_embed_repo_artifacts` (superseded by T004's page rows, which already
      carry `document_id`); if T005/T006 show no other caller depends on
      `CodebaseGraphPersistence.get_canonical_id_map()`, remove the method
      itself (research.md Decision 4).
- [ ] T012 [US1] Build the synthetic scalable fixture generator (quickstart
      Fixture B) in
      `ingestion_service/tests/integration/fixtures/synthetic_repo_generator.py`
      — generates a throwaway repo directory with a parameterized
      embeddable-artifact count N.
- [ ] T013 [US1] Implement a memory-sampling harness script in
      `ingestion_service/tests/scripts/measure_ingest_memory.py` that
      polls `ingestion_service`'s resident memory (e.g. container
      `VmHWM`/`docker stats`) for the duration of one ingestion run and
      writes a peak-memory-over-time series (quickstart.md Prerequisites).
- [ ] T014 [US1] Run the T013 harness against the T012 fixture at N and 4N
      embeddable nodes (same `INGESTION_EMBED_BATCH_SIZE`), and record the
      chunk-embed-persist-stage peak memory for each in
      `DOCS/test_results/` — confirm the 4x node-count increase does not
      produce a comparable increase in peak memory (SC-002), and tune
      T002's default batch size based on the observed numbers.
- [ ] T015 [US1] Run the T013 harness against the real `arc53/DocsGPT`
      snapshot (quickstart Fixture A) under the memory allocation that
      produced the original OOM-kill in issue #160, and record the
      resulting status, final vector count, and peak memory in
      `DOCS/test_results/` (SC-001).

**Checkpoint**: User Story 1 is fully functional and independently
deployable as the MVP — bounded memory, verified against both a synthetic
and the real incident fixture.

---

## Phase 4: User Story 2 - Partial progress survives an interruption (Priority: P2)

**Goal**: An ingestion killed partway through the chunk-embed-persist stage
leaves already-completed slices' vectors durably persisted and queryable.

**Independent Test**: Interrupt an ingestion after N pages complete but
before page N+1 finishes; confirm vectors for the first N pages' artifacts
are already queryable (spec.md Acceptance Scenario, User Story 2).

### Tests for User Story 2

- [ ] T016 [US2] Integration test (marker: `integration`) in
      `ingestion_service/tests/integration/test_bounded_ingest_interruption.py`:
      start an ingestion against the T012 fixture, kill the
      `ingestion_service` process/container after `embed_progress`
      (Phase 5) or an equivalent observable signal shows N pages complete,
      restart the service, and assert vectors for the first N pages'
      artifacts are already queryable via `vector_store_service` while
      later artifacts' vectors are absent.

### Implementation for User Story 2

- [ ] T017 [US2] Audit the T009 bounded loop for any prefetch/pipelining
      that could start fetching or chunking page K+1 before page K's
      `pipeline.embed_and_persist_batch()` call has returned successfully;
      remove any such overlap so persistence for page K is guaranteed
      complete (or the whole ingestion has failed) before page K+1 begins
      (FR-002) — this is a correctness audit of T009, not new production
      code, unless the audit finds an actual violation to fix.
- [ ] T018 [US2] Add a docstring to the T009 bounded loop documenting
      interruption semantics: already-persisted pages survive a hard kill;
      the ingestion record itself is not auto-resumed or reconciled (that
      lifecycle gap is issue #161, explicitly out of scope here per spec.md
      Non-Goals).

**Checkpoint**: User Stories 1 and 2 both independently functional — bounded
memory, and bounded blast radius on interruption.

---

## Phase 5: User Story 3 - Ingestion progress is observable (Priority: P3)

**Goal**: An operator can tell, from `GET
/v1/codebase/ingest-repo/{ingestion_id}`, that a running ingestion's
chunk-embed-persist stage is advancing rather than hung.

**Independent Test**: Poll the status endpoint twice during a running
ingestion and confirm `embed_progress.nodes_processed` has increased
(spec.md Acceptance Scenario, User Story 3).

### Tests for User Story 3

- [ ] T019 [P] [US3] Unit test in
      `ingestion_service/tests/core/test_status_manager_progress.py`:
      `StatusManager.update_embed_progress(ingestion_id, processed, total)`
      merges `{"embed_progress": {"nodes_processed": processed,
      "nodes_total": total}}` into the existing `ingestion_metadata` JSON
      without clobbering other keys (e.g. a prior `error` key), and rejects
      or clamps `processed > total` (data-model.md Validation Rules).
- [ ] T020 [P] [US3] Contract test in
      `ingestion_service/tests/api/test_codebase_ingest_status_progress.py`:
      `GET /v1/codebase/ingest-repo/{ingestion_id}` omits `embed_progress`
      before the embed stage starts, includes it with the documented shape
      once `update_embed_progress` has been called at least once, and
      leaves `ingestion_id`/`status` unchanged in both cases
      (contracts/status-endpoint.md).

### Implementation for User Story 3

- [ ] T021 [US3] Add `update_embed_progress(ingestion_id, processed,
      total)` to `StatusManager` in
      `ingestion_service/src/core/status_manager.py`, following the same
      read-modify-write pattern `mark_failed` already uses for its `error`
      key on `ingestion_metadata`.
- [ ] T022 [US3] Call `update_embed_progress` once per completed page inside
      the T009 bounded loop, using `count_embeddable_nodes` (T004, called
      once at the start of the embed stage) as `nodes_total`.
- [ ] T023 [US3] Extend `RepoIngestResponse` and `get_repo_ingest_status` in
      `ingestion_service/src/api/v1/codebase_ingest.py` to read
      `embed_progress` out of the `IngestionRequest.ingestion_metadata` JSON
      and include it in the response when present
      (contracts/status-endpoint.md).

**Checkpoint**: All three user stories independently functional — bounded
memory, bounded interruption blast radius, and observable progress (SC-004).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T024 [P] Optional: surface `embed_progress` in Gradio's
      `check_codebase_status` (`ingestion_service/src/ui/gradio_app.py`) —
      not required by SC-004 (contracts/status-endpoint.md explicitly marks
      this out of scope for the endpoint contract), a nice-to-have UI
      follow-up.
- [ ] T025 [P] Grep `DOCS/` and `CLAUDE.md` for any description of
      whole-repo-at-once embedding as current behavior and correct it to
      describe the bounded-slice approach, per the project's practice of
      keeping status claims verified against code.
- [ ] T026 Run quickstart.md's fixture-independent FR-008 check (a repo with
      zero embeddable artifacts still reaches `status: "completed"` with
      `embed_progress.nodes_total == 0`) and record the result.
- [ ] T027 [P] Add a `mem_limit` (or `deploy.resources.limits.memory`)
      backstop for `ingestion_service` in `docker-compose.yml`, sized
      comfortably above the peak observed in T014/T015 — defense-in-depth
      per FR-006, not a substitute for T009-T015.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001) for the env var name
  to exist before T002 references it; BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational (T002-T005) only.
- **User Story 2 (Phase 4)**: Depends on Foundational AND User Story 1's
  T009 (audits/documents the loop US1 builds) — not independent of US1's
  implementation, only of US3's.
- **User Story 3 (Phase 5)**: Depends on Foundational AND User Story 1's
  T009/T004 (calls into the loop and reuses `count_embeddable_nodes`) — not
  independent of US1's implementation, only of US2's.
- **Polish (Phase 6)**: Depends on whichever of US1/US2/US3 it touches
  (T024/T026 need US3; T027 needs US1's T014/T015 numbers).

Unlike the fully independent-stories template default, US2 and US3 both
build directly on US1's bounded loop (T009) — this is expected: US1 *is*
the core mechanism, and US2/US3 add a durability guarantee and an
observability surface on top of it, respectively. Each is still
independently *testable* and *valuable* on its own (spec.md's per-story
Independent Test), but not independently *implementable* before US1 exists.

### Within Each User Story

- Tests (T006-T008, T016, T019-T020) before or alongside their story's first
  implementation task, per Constitution Principle VIII.
- T009 (the bounded loop) before T010-T011 (which modify how it's called/
  what it calls), before T012-T015 (which validate it).

### Parallel Opportunities

- T001-T003 can run in parallel (different files).
- T005 can run in parallel with T003 (different files), but not before T004.
- T006 and T007 can run in parallel (different files); T008 depends on T009
  existing to have something to run against, so in practice write T008
  alongside T006/T007 but expect it to fail until T009 lands.
- T019 and T020 can run in parallel.
- T024, T025, T027 can run in parallel.

---

## Parallel Example: Foundational Phase

```bash
Task: "Add INGESTION_EMBED_BATCH_SIZE to ingestion_service/src/core/config.py"
Task: "Extract LANGUAGE_BY_SUFFIX into ingestion_service/src/core/codebase/language_by_suffix.py"
```

## Parallel Example: User Story 1 Tests

```bash
Task: "Unit test for bounded-loop page-size invariant in tests/api/test_embed_repo_artifacts_bounded.py"
Task: "Unit test for chunk-metadata parity in tests/api/test_embed_repo_artifacts_metadata_parity.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1).
3. **STOP and VALIDATE**: run T014/T015's harnesses; confirm SC-001 and
   SC-002 hold before proceeding.
4. This alone resolves issue #160's core failure mode and can ship as the
   MVP — US2 and US3 add durability/observability, not the memory fix
   itself.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. User Story 1 → validate against both fixtures → ship (resolves #160).
3. User Story 2 → validate interruption behavior → ship.
4. User Story 3 → validate progress observability → ship.
5. Polish as capacity allows.

---

## Notes

- [P] tasks touch different files with no unmet dependency.
- All changes land via branch + pull request per Constitution Governance;
  no direct commits to `main`.
- No `Co-Authored-By` trailers or AI-generation notices in commits/PRs, per
  Constitution Governance — AI-assisted development is credited in
  `README.md` instead.
- Stop at each Checkpoint to validate a story independently before moving on.
