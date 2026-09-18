# Tasks: Incremental ingestion + repository/file snapshot lineage

**Input**: Design documents from `specs/006-incremental-ingestion-lineage/`

**Tracking Issue**: #196
**Spec**: `specs/006-incremental-ingestion-lineage/spec.md`
**Plan**: `specs/006-incremental-ingestion-lineage/plan.md`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md — all present.

**Tests**: Required by Constitution Principle VIII — each phase below
includes skeletal behavioral tests before or alongside its first
implementation task. Evaluation Evidence (Principles III/VIII) is
**not applicable** — confirmed N/A in spec.md and plan.md (no
retrieval/ranking/generation change) — so no Evaluation & Evidence
phase appears below.

**Organization**: Tasks are grouped by user story per spec.md's
priorities (US1, US2 both P1; US3 P2), after a Foundational phase that
**must** land first per explicit review: the persistence-invariant
change (stable `document_id` across generations) is its own
standalone, independently testable unit of work, landing and verified
before any incremental-classification/reuse logic is built on top of
it — not folded into a broader orchestration task.

**Out of scope, do not create tasks for**: issue #165
(`pipeline_factory.py` does not exist, pre-existing gap, disclosed in
plan.md's Constitution Check). Every task below that touches
`codebase_ingest.py` follows the existing `_build_pipeline`/
`_background_ingest_repo` pattern as-is.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)

## Path Conventions

All paths are under `ingestion_service/` and `shared/models/`
(existing service boundaries, Constitution Principle II) plus one new
Alembic migration under `migrations/versions/`.

---

## Phase 1: Setup (Schema)

**Purpose**: Additive schema changes every later task depends on. No
new table (FR-011) — all new columns on existing tables, all nullable
or defaulted, no data backfill required (data-model.md's opening note).

- [X] T001 Write additive Alembic migration in `migrations/versions/<timestamp>_incremental_ingestion_lineage.py`: `ingestion_requests` gains `commit_sha` (String, nullable), `parent_generation_id` (UUID, nullable), `is_incremental` (Boolean, not null, default `false`), `chunking_config_version` (String, nullable), `embedding_config_version` (String, nullable); `document_nodes` gains `content_hash` (String, nullable); `document_relationships` gains `repo_id` (String, not null) plus an index on it. Verify `alembic upgrade head` and `alembic downgrade -1` both run clean against the test DB (`docker-compose.test.yml`).
- [X] T002 [P] Add `commit_sha`, `parent_generation_id`, `is_incremental`, `chunking_config_version`, `embedding_config_version` columns to the `IngestionRequest` model in `ingestion_service/src/core/models.py`, matching T001 exactly.
- [X] T003 [P] Add `content_hash` column to `DocumentNode` in `shared/models/document_node.py`, matching T001 exactly.
- [X] T004 [P] Add `repo_id` column (and matching `Index`) to `DocumentRelationship` in `shared/models/document_relationship.py`, matching T001 exactly.

**Checkpoint**: Schema exists and ORM models match it; nothing yet reads or writes the new columns.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The persistence-invariant change every user story below
depends on. **Must be complete, tested, and verifiable in isolation
before any Phase 3+ task begins** — this is the explicit scope
boundary from design review, not an implementation convenience.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Foundational Tests (write first — Constitution Principle VIII)

- [X] T005 [P] Integration test in `ingestion_service/tests/core/codebase/test_persist_graph_upsert.py` (real PostgreSQL, per `docker-compose.test.yml`): a `canonical_id` present in both an old and a new `persist_graph` call keeps the **same `document_id`** across the two calls (update-in-place, not delete-and-reinsert).
- [X] T006 [P] Same file: a `canonical_id` present in the old call but absent from the new call's node set is deleted, and its `document_relationships`/`vectors` rows are gone too (cascade still fires for genuine removals).
- [X] T007 [P] Same file: a `vectors` row created against a reused `document_id` from the first `persist_graph` call is still valid (FK intact, not cascade-deleted) after the second call updates that row's owning `document_nodes` row in place.
- [X] T008 [P] Same file: a `persist_graph` call that raises mid-transaction (simulate via a forced `SQLAlchemyError`) leaves the previous generation's `document_nodes`/`document_relationships` rows completely unchanged — same rollback guarantee the current docstring already claims, now verified against the upsert path specifically.
- [X] T009 [P] Integration test in `ingestion_service/tests/core/codebase/test_persist_graph_relationships.py`: a `document_relationships` row from a prior `persist_graph` call, touching a node that is *reused unchanged* in the next call, is removed and replaced by that call's freshly supplied relationship set (not left stale) — proves the `repo_id`-scoped relationship replace (research.md R2) doesn't rely on node-cascade to clean up edges.

### Foundational Implementation

- [X] T010 [US: none — shared] Rewrite the node-persistence step of `persist_graph` in `ingestion_service/src/core/codebase/codebase_persistence.py`: replace the unconditional `DELETE FROM document_nodes WHERE repo_id=...` + bulk-insert-with-fresh-UUIDs with `INSERT ... ON CONFLICT (repo_id, canonical_id) DO UPDATE SET <every column except document_id>` (upsert), plus an explicit `DELETE ... WHERE repo_id=... AND canonical_id NOT IN (<current canonical_ids>)` for genuinely removed rows. `ingestion_id` MUST be included in `DO UPDATE SET` on every row. Must satisfy T005-T008.
- [X] T011 Replace the relationship-persistence step in the same file: before inserting the freshly resolved relationship set, `DELETE FROM document_relationships WHERE repo_id = :repo_id` (using the new column from T004), then insert with `repo_id` populated on every row. Must satisfy T009. Depends on T010 (same transaction, same method).
- [X] T012 [P] Create `ingestion_service/src/core/codebase/snapshot_diff.py`: a focused module (not a framework) exposing one classification function taking the current checkout's file set + freshly computed content hashes, and the prior generation's file-level `(canonical_id -> content_hash)` map, returning four sets: unchanged, changed, new, deleted. No I/O of its own — pure function over data the caller already has.
- [X] T013 [P] Unit tests for `snapshot_diff.py` in `ingestion_service/tests/core/codebase/test_snapshot_diff.py`: empty prior-generation map classifies everything as new; a file present in both with matching hash classifies unchanged; mismatched hash classifies changed; a prior-generation `canonical_id` absent from the current set classifies deleted; whitespace-only content change still classifies changed (spec Edge Cases — no semantic hashing).

**Interim fix (discovered during Foundational verification, not in original task list)**:
R1's document_id-stability change means a reused node's old `vector_chunks`
rows are no longer cascade-cleaned between full rebuilds (previously
"free" via delete-all). Until Phase 3's T023/T024 reuse-aware embed logic
lands, `_embed_repo_artifacts` (`ingestion_service/src/api/v1/codebase_ingest.py`)
now calls `vector_store.delete_by_ingestion_id(ingestion_id)` at the start
of each embed pass — a no-op in the normal fresh-ingestion_id case, and a
guard against duplicate vector rows on a retried/duplicate invocation of
the same generation. Regression test:
`test_embed_repo_artifacts_clears_stale_vectors_before_writing` in
`ingestion_service/tests/codebase/test_batch_embedding.py`. Test doubles
in `test_artifact_paging.py`/`test_batch_embedding.py`/
`test_streaming_embedding_stage.py` updated to stub the new call.

**Checkpoint**: `persist_graph` now supports document-identity-stable
upserts and correctly-scoped relationship replacement, independently
verified. `snapshot_diff.py` can classify files given data, independently
verified. Nothing yet calls `snapshot_diff.py` from the real ingestion
flow, and nothing yet skips embedding — that's Phase 3.

---

## Phase 3: User Story 1 - Re-ingest a mostly-unchanged repository fast (Priority: P1) 🎯 MVP

**Goal**: A re-ingestion whose prior generation is `completed` classifies
files via `snapshot_diff`, skips re-chunking/re-embedding for files
that pass the FR-006 reuse gate, and carries their existing vectors
forward under the new generation.

**Independent Test**: Per quickstart.md steps 1-2 — ingest a fixture
repo, edit 1 file, re-ingest, confirm only that file's artifacts are
re-embedded and the run completes within SC-001's bound.

### Tests for User Story 1

- [X] T014 [P] [US1] Integration test in `ingestion_service/tests/api/test_incremental_ingest.py`: re-ingesting with an unchanged file present reuses that file's `document_id` and `vectors` rows (no new embedding call made — assert on a mocked/counted embedder), and re-tags them to the new `ingestion_id` (FR-007b).
- [X] T015 [P] [US1] Same file: FR-006 reuse gate — a content-hash match with a *different* `chunking_config_version` or `embedding_config_version` than the prior generation forces re-embedding anyway.
- [X] T016 [P] [US1] Same file: FR-005 — a re-ingestion whose prior generation for the `repo_id` is `building` or `failed` (not `completed`) performs a full ingestion (every file re-embedded, `is_incremental: false`).
- [X] T017 [P] [US1] Same file: FR-005a — `force_full_rebuild: true` performs a full ingestion even with a valid prior `completed` generation, and still records `parent_generation_id`.
- [X] T018 [US1] Performance test per quickstart.md step 2 / SC-001, in `ingestion_service/tests/integration/test_incremental_performance.py` (may be marked slow/opt-in given fixture size): a ~2,000-file fixture repo with 1 file edited re-embeds only that file's artifacts and completes in under 30 seconds.

### Implementation for User Story 1

- [X] T019 [US1] Add `force_full_rebuild: bool = False` to `RepoIngestRequest` and the multipart `Form(...)` parameters in `ingestion_service/src/api/v1/codebase_ingest.py`, per `contracts/ingest-repo.md`.
- [X] T020 [US1] In `_background_ingest_repo` (`codebase_ingest.py`), before cloning: call `db_utils.resolve_current_generation(repo_id)`/`generation_status(repo_id)` to determine whether a valid prior `completed` generation exists; combine with `force_full_rebuild` to decide `is_incremental` for this run (FR-004/FR-005/FR-005a). Depends on T019.
- [X] T021 [US1] When incremental: before `persist_graph` runs, read the prior generation's file-level `content_hash` values (query `document_nodes` filtered by `repo_id`, current owner `ingestion_id`, `symbol_path IS NULL`). Depends on T020, T003.
- [X] T022 [US1] In `RepoGraphBuilder`/`_walk_repo` (`ingestion_service/src/core/codebase/repo_graph_builder.py`), compute each file's SHA-256 content hash during the existing walk and attach it to the file-level node dict passed through to `persist_graph` (FR-003). Depends on T003.
- [X] T023 [US1] Wire `snapshot_diff.classify(...)` (T012) into `_background_ingest_repo` using T021's prior-hash map and T022's fresh hashes; pass the resulting changed/new/unchanged/deleted sets through to the persist and embed steps. Depends on T012, T021, T022.
- [X] T024 [US1] In the embedding step (`_embed_repo_artifacts` or equivalent in `codebase_ingest.py`), skip chunk+embed for files in the "unchanged and eligible" set from T023 (FR-006/FR-007); for their existing `vectors` rows, bulk `UPDATE ingestion_id` to the new generation's value instead (FR-007b vector half — no re-embedding). Depends on T023, T010.
- [X] T025 [US1] Record `chunking_config_version` (active `chunk_strategy`) and `embedding_config_version` (`settings.OLLAMA_EMBED_MODEL`) on the new `ingestion_requests` row at ingestion start (research.md R4). Depends on T002.
- [X] T026 [US1] Record `is_incremental` on the `ingestion_requests` row when the run completes. Depends on T020, T002.

**Checkpoint**: User Story 1 is independently functional — re-ingestion
of a mostly-unchanged repo skips embedding for unchanged files and
completes fast, verified by T014-T018. All Phase 1-3 tests (Foundational
control suite + new US1 suite + performance test) green together;
Foundational tests unmodified except one exception-type generalization
required by R1 itself (test_failed_rebuild_preserves_previous_graph now
expects SQLAlchemyError, not the narrower IntegrityError, since ON
CONFLICT DO UPDATE raises CardinalityViolation for the same fixture that
used to raise a uq_repo_canonical IntegrityError — same invariant
verified, different exception subtype).

**Interim fix carried forward from Phase 2** (see that phase's note):
`_embed_repo_artifacts` unconditionally cleared this ingestion_id's
vectors before writing (idempotency guard). Superseded by T024's proper
reuse-gate wiring for the normal case; the guard call still runs and
remains a correct no-op/safety-net for retried invocations, now sitting
alongside (not instead of) real reuse.

---

## Phase 4: User Story 2 - Know exactly which source snapshot a corpus/generation represents (Priority: P1)

**Goal**: Every completed ingestion (full, incremental, or forced-full)
records its source commit SHA, timestamp, and parent generation, all
queryable via the existing generation endpoint.

**Independent Test**: Per quickstart.md step 1 — after any ingestion,
`GET /v1/repos/{repo_id}/generation` returns commit SHA, timestamp, and
(for incremental/forced-full) parent generation.

### Tests for User Story 2

- [X] T027 [P] [US2] Contract test in `ingestion_service/tests/api/test_repo_generation_lineage.py`: response shape matches `contracts/repo-generation-lineage.md` — `commit_sha`, `ingested_at`, `parent_generation_id`, `is_incremental` present and `None`/`false`-appropriate for a repo's first-ever (non-incremental) generation.
- [X] T028 [P] [US2] Same file: for a git-backed ingestion, `commit_sha` matches the fixture repo's actual resolved HEAD SHA at clone time (not a placeholder).
- [X] T029 [P] [US2] Same file: for a `local_path` ingestion, `commit_sha` is `None` (spec Non-Goals — non-git sources out of scope for commit identity).

### Implementation for User Story 2

- [X] T030 [US2] In `_background_ingest_repo` (`codebase_ingest.py`), immediately after `git.Repo.clone_from(git_url, temp_dir)`, resolve `git.Repo(temp_dir).head.commit.hexsha` (research.md R5). Leave `commit_sha` unset for `local_path` ingestions.
- [X] T031 [US2] Thread the resolved `commit_sha`, and (from Phase 3's T020) `parent_generation_id`/`is_incremental`, through to wherever ingestion completion is recorded (alongside the existing `StatusManager` completion call) so they land on the `ingestion_requests` row. Depends on T030, T002, T020.
- [X] T032 [US2] Extend `RepoGenerationResponse` and `get_repo_generation` in `ingestion_service/src/api/v1/repos.py` with `commit_sha`, `ingested_at`, `parent_generation_id`, `is_incremental`, populated only when `generation_status == "ready"` (see implementation note below — the contract's original wording said `"completed"`, corrected), per `contracts/repo-generation-lineage.md`. Depends on T031.

**Checkpoint**: User Stories 1 AND 2 both work independently — lineage
is recorded and queryable regardless of whether Phase 3's reuse path
was exercised.

**Implementation notes**:
- `db_utils.generation_status()` returns the established ADR-051
  vocabulary (`ready`/`building`/`failed`/`unknown`), never the literal
  string `"completed"` — the contract's "populated only when
  generation_status == completed" is satisfied by gating on
  `resolve_current_generation(repo_id) is not None` (already exactly
  the "ready" condition), not a string comparison against `"completed"`.
- `StatusManager.record_is_incremental` (Phase 3) was extended in place
  to `record_completion_lineage(..., is_incremental=..., commit_sha=...)`
  rather than adding a second near-duplicate completion-time write.
- Found and fixed a real, independent bug while writing T028's git-backed
  test: `_background_ingest_repo`'s `finally` block called
  `shutil.rmtree(temp_dir)` unguarded — a lingering git-process/pack-file
  handle (observed on Windows; not exercised by any prior test since none
  used a real `git_url` clone) raised `PermissionError` there, which
  would propagate out of the *whole* worker and could mark an otherwise-
  successfully-completed ingestion as failed. Now caught and logged,
  matching the existing best-effort cleanup pattern already used for
  superseded-generation cleanup in the same function.

---

## Phase 5: User Story 3 - Deletions are fully reflected, never orphaned (Priority: P2)

**Goal**: Files removed between snapshots leave no graph or vector rows
behind in the new generation.

**Independent Test**: Per quickstart.md step 3 — ingest, delete a file
with graph/vector rows, re-ingest, confirm no rows for its canonical
IDs remain.

### Tests for User Story 3

- [X] T033 [P] [US3] Integration test in `ingestion_service/tests/api/test_incremental_deletes.py`: a file present in generation N but absent from generation N+1's checkout has no `document_nodes`, `document_relationships`, or `vectors` rows referencing its canonical IDs (file-level or symbol-level) after N+1 completes (FR-008/SC-003).
- [X] T034 [P] [US3] Same file: Acceptance Scenario 2 — a symbol that a deleted file used to define, still referenced by an unrelated *unchanged* file, resolves the same way a full rebuild would (e.g. to an `EXTERNAL_*` node), not to stale graph state — proves Phase 2's repo-scoped relationship replace (T011) plus Phase 3's whole-repo re-resolution (already always-on, FR-002) combine correctly for this case.

### Implementation for User Story 3

- [X] T035 [US3] Confirm/wire `snapshot_diff`'s "deleted" set (T012/T023) into the explicit delete scope Phase 2's T010 already added to `persist_graph` — this should require no new deletion logic (T010 already deletes any `canonical_id` absent from the new node set), only confirming the caller correctly omits deleted files' canonical IDs from that set. Depends on T010, T023.

**Implementation notes**:
- Confirmed, no new code required: `_build_and_persist_graph`
  (`codebase_ingest.py`) always runs `RepoGraphBuilder` over the *current*
  checkout on disk regardless of `is_incremental`, so a deleted file's
  nodes are simply never in `graph.all_entities()` — `persist_graph`'s
  existing "delete any `canonical_id` absent from the new node set"
  logic (T010) handles it with zero awareness of `snapshot_diff.deleted`.
  `snapshot_diff.deleted` is consumed only for logging
  (`codebase_ingest.py`'s diff-summary log line), never as a second
  deletion path — there is only one.
- T033/T034 (`test_incremental_deletes.py`) verified this against real
  Postgres + a real vector_store_service process: a deleted file's
  file-level *and* symbol-level canonical IDs leave no
  `document_nodes`/`document_relationships`/`vector_chunks` rows behind,
  and an unrelated unchanged file's CALL edge to a symbol the deleted
  file used to define re-resolves to an `EXTERNAL_SYMBOL:` node on the
  next generation — proving the always-on whole-repo re-resolution
  (FR-002) and the repo-scoped relationship replace (T011/R2) compose
  correctly even when the calling node itself keeps its `document_id`
  (R1, never cascade-deleted).

**Checkpoint**: All three user stories are independently functional and
verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: The equivalence guarantee tying every prior phase
together, plus documentation.

- [X] T036 Build the FR-012/SC-002 equivalence fixture and CI test in `ingestion_service/tests/integration/test_incremental_equivalence.py`: script add/change/delete edits against a fixture repo; ingest full (baseline) and separately full-then-incremental (same target commit); assert equivalent `(canonical_id, relation_type)` edge sets, equivalent `(canonical_id, chunk_index, chunk_text)` vector tuples, and matching `commit_sha` lineage between the two — per quickstart.md step 4. Depends on Phases 3-5 all being complete.
- [X] T037 [P] Run `quickstart.md` end to end against `docker-compose.test.yml` and record results.
- [X] T038 [P] Update `DOCS/status.md` to record #196's shipped scope (per this repo's convention of recording merged work there, not a dated snapshot), and close/comment on #180 per spec.md's Governing References note (verify #180's acceptance criteria are actually satisfied before closing — don't assume subsumed).

**Implementation notes**:
- T036's fixture uses `local_path` ingestion for both the baseline and
  incremental flows (not `git_url`), so the "matching `commit_sha`
  lineage" assertion is `None == None` rather than a real SHA
  comparison — see the test module's docstring for why real git-SHA
  parity between two independently-created repos would add fragility
  without adding coverage (T028 already independently proves git-backed
  `commit_sha` correctness).
- Writing T036 surfaced a real local-test-harness gap (not a production
  bug): `_background_ingest_repo`'s post-completion superseded-
  generation cleanup (`codebase_ingest.py`, #166) builds its own
  `HttpVectorStore` from `settings.VECTOR_STORE_SERVICE_URL` rather than
  reusing the pipeline's `vector_store` — correct under docker-compose
  (that hostname resolves there) but silently a no-op (best-effort/
  non-fatal, so no test failure) against an isolated-process test
  vector service on a random port. This meant a changed file's *prior*-
  generation vector rows were never actually swept in any test that
  didn't specifically check for their absence — T036 is the first test
  to check, so it patches `get_settings().VECTOR_STORE_SERVICE_URL` to
  the test's own vector service URL before asserting equivalence,
  rather than silently passing on a masked no-op. No source change
  needed; this is a test-fixture-only finding.
- T037: ran the equivalent of quickstart.md steps 1-6 as the full
  `ingestion_service` Phase 3-6 integration suite (`test_incremental_
  ingest.py`, `test_incremental_deletes.py`, `test_repo_generation_
  lineage.py`, `test_persist_graph_upsert.py`, `test_persist_graph_
  relationships.py`, `test_incremental_equivalence.py`) against
  `docker-compose.test.yml`'s Postgres (localhost:5433) — 15/15 passed.
  quickstart.md's own manual/`docker-compose.test.yml` steps mirror
  these automated tests 1:1 (steps 1-3 → Phase 3/5, step 4 → T036,
  step 5 → T017, step 6 → T016); no divergence found between the
  documented manual flow and actual runtime behavior. `docker-compose.
  test.yml` in this environment runs only the isolated Postgres
  container — `vector_store_service`/`ingestion_service` are exercised
  via the tests' own subprocess fixtures (matching every other Phase
  3-5 test file's existing pattern), not additional long-running
  containers.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (needs the new columns to exist). **Blocks all of Phase 3/4/5.**
- **US1 (Phase 3)**: Depends on Phase 2 (T010 upsert, T012 classifier) and Phase 1 (T002, T003).
- **US2 (Phase 4)**: Depends on Phase 1 (T002) and Phase 3's T020 for `parent_generation_id`/`is_incremental` values, but its own core work (commit SHA resolution, endpoint fields) is otherwise independent of Phase 3's embedding-skip logic — could be staffed in parallel with Phase 3 by a different developer, converging at T031.
- **US3 (Phase 5)**: Depends on Phase 2 (T010's delete scope, T011's relationship replace) and Phase 3's T023 (classifier wiring) for the "deleted" set to consume. Thin phase — most of the work is already done by Phase 2/3; this phase is primarily verification (T033/T034) plus a small confirmation task (T035).
- **Polish (Phase 6)**: Depends on Phases 3, 4, and 5 all complete (T036 exercises the full feature).

### Parallel Opportunities

- T002, T003, T004 (Phase 1 model updates) — different files, parallel.
- T005-T009 (Foundational tests) — different test files/cases, parallel, all before T010.
- T012/T013 (snapshot_diff + its tests) — parallel with T010/T011 (different files, no shared dependency until Phase 3 wires them together).
- T014-T017 (US1 tests) — parallel.
- T027-T029 (US2 tests) — parallel.
- T033-T034 (US3 tests) — parallel.
- US2 (Phase 4) can be staffed in parallel with US1 (Phase 3) by a different developer once Phase 2 completes, per the phase-dependency note above.

---

## Parallel Example: Foundational Phase

```bash
# Launch all Foundational tests together (before T010/T011 implementation):
Task: "Integration test: document_id stability across persist_graph calls in ingestion_service/tests/core/codebase/test_persist_graph_upsert.py"
Task: "Integration test: deleted canonical_id removes node+relationships+vectors, same file"
Task: "Integration test: reused document_id keeps vectors FK-valid, same file"
Task: "Integration test: failed upsert leaves previous generation intact, same file"
Task: "Integration test: repo-scoped relationship replace in ingestion_service/tests/core/codebase/test_persist_graph_relationships.py"

# In parallel, unrelated to the above:
Task: "Create snapshot_diff.py classifier in ingestion_service/src/core/codebase/snapshot_diff.py"
Task: "Unit tests for snapshot_diff.py in ingestion_service/tests/core/codebase/test_snapshot_diff.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational — **stop and validate the persistence
   invariant in isolation (T005-T009 all green) before writing a single
   line of Phase 3 code.** This is the explicit checkpoint design review
   called for.
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: SC-001 passes (T018), reuse gate correct (T015).

### Incremental Delivery

1. Setup + Foundational → foundation ready, persistence invariant proven standalone.
2. Add US1 → fast re-ingestion works → validate independently.
3. Add US2 → lineage queryable → validate independently (can overlap with US1's staffing per the parallel note above).
4. Add US3 → deletes fully reflected → validate independently (thin phase, mostly verification of Phase 2/3 work already done).
5. Phase 6 → equivalence proof ties all three together, closing FR-012/SC-002.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability; Phase 1/2/6 tasks carry no story label per template convention (shared/cross-cutting).
- Commit coherent, reviewable logical units; all changes land via PR per the constitution's Governance section (no direct commits to `main`).
- Do not create any task that builds `pipeline_factory.py` or refactors pipeline construction beyond `force_full_rebuild` plumbing — #165 stays out of scope (see plan.md's Constitution Check).
