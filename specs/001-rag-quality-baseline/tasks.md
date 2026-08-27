---

description: "Task list for RAG Quality Baseline (WP-Q0)"
---

# Tasks: RAG Quality Baseline (WP-Q0)

**Input**: Design documents from `/specs/001-rag-quality-baseline/`

**Tracking Issue**: #49
**Spec**: `specs/001-rag-quality-baseline/spec.md`
**Plan**: `specs/001-rag-quality-baseline/plan.md`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, quickstart.md ✓ (no `contracts/` — this feature exposes no new interface, per plan.md)

**Tests**: Required by Constitution Principle VIII. For this evaluation
feature there is no new production code to unit-test, so "tests" here means
a skeletal verification/dry-run of each scenario's procedure against one
pilot question before running it across the full set — not a pytest suite.

**Organization**: Tasks are grouped by evaluation scenario (spec.md
Scenarios 1-4), executed in strict sequence — see Dependencies below for why
this deviates from the default independent-user-story assumption.

## Constitution Compliance

Before executing these tasks, note the plan's Constitution Check
(`plan.md`): no EXCEPTION REQUIRED entries. Per spec.md Non-Goals and
plan.md's Architecture Impact, if any task below would:

- fix a correctness bug found during evaluation (e.g. cross-repo leakage,
  double-chunking) instead of filing it as a separate issue,
- implement a reranker, hybrid retrieval, an embedding change, a chunking
  change, or a prompt/model change, or
- turn the evaluation procedure into a reusable service, framework,
  database, API, or abstraction layer,

STOP — that task is out of scope for SPEC 001 and must be filed as a
separate issue instead of executed here.

## Format: `[ID] [P?] [Scenario] Description`

- **[P]**: Can run in parallel (different files/questions, no dependencies)
- **[Scenario]**: Which spec.md scenario this task belongs to (S1-S4)
- Include exact endpoints/file paths in descriptions

## Path Conventions

This is a multi-service repository (`ingestion_service`,
`vector_store_service`, `llm_service`, `rag_orchestrator`, `shared/`,
`gradio`). Per plan.md's Architecture Impact, **no task below modifies any
file in those service directories** — every task is either an HTTP call
against their existing endpoints, or a write to `DOCS/test_results/` or
`specs/001-rag-quality-baseline/scripts/`.

---

## Phase 1: Setup

**Purpose**: Confirm the environment this evaluation runs against is ready — no new infrastructure is created.

- [ ] T001 [P] Verify the stack is running (`docker compose up --build`, migrations applied) and Ollama is reachable, per `quickstart.md` Prerequisites
- [ ] T002 [P] Confirm `shared/smoke_repo` exists and is ingestable without modification

**Checkpoint**: environment ready; no code or schema was touched to get here.

---

## Phase 2: Foundational

**Not applicable to this feature.** There is no shared infrastructure to
build — each scenario below reads directly from the existing, unmodified
system (plan.md's Architecture Impact: "No production architecture change").
Introducing a foundational-infrastructure phase here would itself be scope
drift; skipped deliberately, not by oversight.

---

## Phase 3: Scenario 1 - Establish the evaluation corpus and known-answer question set (Priority: P1)

**Goal**: An ingested corpus and a reviewable question set with known-correct sources, per spec.md Scenario 1.

**Independent Test**: the corpus is ingested and queryable, and the question set exists as a reviewable artifact independent of any later measurement.

### Tests for Scenario 1

> **NOTE:** Skeletal verification before the full pass, per Constitution Principle VIII.

- [ ] T003 [S1] Verify each corpus artifact is present in the index via `GET /v1/graph/repos/{repo_id}` / `GET /v1/graph/docs` (`ingestion_service`) before any question is drafted against it (spec.md Scenario 1, Acceptance Scenario 1)

### Implementation for Scenario 1

- [ ] T004 [P] [S1] Ingest `shared/smoke_repo` via `POST /v1/ingest-repo` (`ingestion_service`); record the returned `repo_id` in the evidence file at `DOCS/test_results/2026-08-26-wp-q0-rag-quality-baseline.md` (research.md Decision 2)
- [ ] T005 [P] [S1] Select and ingest 2-3 representative existing documents via `POST /v1/ingest/file` (`ingestion_service`), per research.md Decision 1 (pre-existing project docs, not newly authored text); record the returned document IDs in the evidence file
- [ ] T006 [S1] Draft 8-12 known-answer questions per `data-model.md`'s Known-Answer Question shape (question, `query_type`, `repo_id`, `expected_canonical_id` or `expected_passage`), mixing code and document queries; record them in the evidence file (depends on T004, T005)

**Checkpoint**: corpus ingested, question set defined and reviewable — independent of any measurement being run yet (spec.md SC-001, SC-002).

---

## Phase 4: Scenario 2 - Record the full diagnostic surface per question (Priority: P1)

**Goal**: One complete Diagnostic Record row per question, per spec.md Scenario 2 / FR-003.

**Independent Test**: the diagnostic table is complete for all questions and independently reviewable, regardless of whether Scenario 3/4 has run.

### Tests for Scenario 2

- [ ] T007 [S2] Dry-run the full diagnostic procedure (source presence → seed rank → expanded rank → duplicate count → repo-leakage check → end-to-end answer quality) against one pilot question before running it across the full set

### Implementation for Scenario 2

- [ ] T008 [S2] For each question, call the production retrieval path (`/v1/rag` for code, `/v1/rag/simple` for documents, or `/v1/vectors/search` directly for seed rank per methodology §2) and record `source_present_in_index` (depends on T006)
- [ ] T009 [S2] If a question's expected source is absent from the index, stop the diagnostic pass for that question and record it as `ingestion-defect` (spec.md Edge Cases) — do not score it against the ranking decision table, and file a separate GitHub issue if this represents a real ingestion bug (spec.md FR-008)
- [ ] T010 [S2] For each question with a present source, record `seed_rank` and `expanded_rank` (data-model.md)
- [ ] T011 [S2] For each question, record `duplicate_count` in the top-20 candidate set
- [ ] T012 [S2] For each question, record `repo_leakage`; if leakage is found, file it as a separate GitHub issue (an ADR-030 correctness bug, spec.md Non-Goals) — do not fix it here
- [ ] T013 [S2] For each question, record `end_to_end_answer_quality` (pass/fail) via the actual production path

**Checkpoint**: 100% of questions have a complete Diagnostic Record (spec.md SC-003), independently reviewable.

---

## Phase 5: Scenario 3 - Isolate generation quality with clean context (Priority: P2)

**Goal**: A Clean-Context Score for every question whose end-to-end answer failed, per spec.md Scenario 3 / FR-004. Runs only against Scenario 2's failures.

**Independent Test**: every failed question (and only failed questions) has a recorded grounding/citation/omission score.

### Tests for Scenario 3

- [ ] T014 [S3] Dry-run the clean-context procedure (research.md Decision 4: direct Ollama call, bypassing `/generate`) against one failed question before running it across all failures

### Implementation for Scenario 3

- [ ] T015 [P] [S3] For each question where `end_to_end_answer_quality = fail` (from T013), hand-pick the correct 2-4 chunks and call Ollama directly with only those chunks as context (research.md Decision 4) — parallelizable across different failed questions
- [ ] T016 [S3] Record `grounding`, `citation`, `omission`, `latency_cold`, `latency_warm` per failed question in the evidence file (depends on T015)
- [ ] T017 [S3] Confirm no clean-context test was run for any question that already passed end-to-end (spec.md FR-004 — a completeness check on T015/T016, not new work)

**Checkpoint**: 100% of failed questions have a Clean-Context Score (spec.md SC-004); passing questions are untouched.

---

## Phase 6: Scenario 4 - Classify every failure and produce an evidence-backed decision (Priority: P1)

**Goal**: Every failure classified against the decision table, and an explicit go/no-go verdict on reranking, per spec.md Scenario 4 / FR-005 / FR-006.

**Independent Test**: a written verdict exists with the failure-count breakdown that justifies it.

### Tests for Scenario 4

- [ ] T018 [S4] Dry-run the decision-table classification against one known failure case before classifying the full set

### Implementation for Scenario 4

- [ ] T019 [S4] Classify every recorded failure (from T009-T013) against the decision table — `ingestion-defect` / `absent-from-top-20` / `rank-8-to-20` / `top-3-but-poor-answer` / `cross-repo-leakage` / `duplicate-crowding` — **before** any chunking, retrieval, or generation change is proposed anywhere in the project (spec.md FR-005 — hard gate, depends on T009-T013 and T016)
- [ ] T020 [P] [S4] Compute Recall@5, Recall@20, and other aggregate rates from the recorded evidence — by hand, or via an optional scratch script at `specs/001-rag-quality-baseline/scripts/` (plan.md's scratch-script allowance: deterministic aggregation only, no new eval framework)
- [ ] T021 [S4] Apply the reranker decision gate (`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §4) and record an explicit go/no-go verdict in the evidence file, with the failure-count breakdown, or the identified next lever (chunking / filtering / dedup / traversal / prompting) if reranking isn't justified, or the explicit negative result if no pattern dominates (spec.md FR-006, depends on T019, T020)
- [ ] T022 [S4] File separate GitHub issues for every correctness bug discovered during evaluation (cross-repo leakage, double-chunking, ingestion defects, etc.) — none are fixed as part of this spec (spec.md Non-Goals / FR-008)

**Checkpoint**: evidence file complete with a recorded verdict (spec.md SC-006). No reranker, hybrid retrieval, embedding, chunking, or prompt/model work has been implemented anywhere in the repo as part of this spec.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Close out the spec without expanding its scope.

- [ ] T023 Review the evidence file against spec.md's Success Criteria (SC-001 through SC-006) for completeness
- [ ] T024 Commit the evidence file (and any scratch script) via the standard branch + PR flow (Constitution Governance — no direct commits to main)
- [ ] T025 Post the verdict summary as a comment on issue #49, linking the evidence file — closing the issue (or opening a follow-up issue for whichever lever the evidence points to) is a judgment call for review, not automatic
- [ ] T026 Update `DOCS/audit/07-Roadmap.md` to mark Phase 2.75 / WP-Q0 complete, linking the evidence file (documentation only — no code change)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — can start immediately
- **Foundational (Phase 2)**: not applicable — skipped (see above)
- **Scenarios (Phase 3-6)**: **strictly sequential, not independently parallelizable across scenarios** — this deviates from the tasks-template's default assumption that user stories are independent. Each scenario's input is the previous scenario's output: Scenario 2 needs Scenario 1's corpus/questions; Scenario 3 needs Scenario 2's failure list; Scenario 4 needs both Scenario 2's diagnostic table and Scenario 3's clean-context scores. This is inherent to the evaluation pipeline the methodology defines, not a modeling choice.
- **Polish (Phase 7)**: depends on Scenario 4 completing

### Scenario Dependencies

- **Scenario 1 (P1)**: no dependencies — first
- **Scenario 2 (P1)**: depends on Scenario 1 (needs corpus + question set)
- **Scenario 3 (P2)**: depends on Scenario 2 (runs only against its recorded failures)
- **Scenario 4 (P1)**: depends on Scenario 2 and Scenario 3 (classifies using both)

### Parallel Opportunities

- T001/T002 (Setup) can run in parallel
- T004/T005 (ingesting the repo vs. the documents) can run in parallel
- Within Scenario 2, per-question diagnostic recording (T008-T013) should be done as one pass per question (methodology's "single pass per question" rule), but different *questions* can be worked in parallel
- T015 (clean-context calls) can run in parallel across different failed questions
- T020 (aggregate metric computation) can run in parallel with T019 only in the sense that they read the same completed data; T021's verdict depends on both

---

## Implementation Strategy

### Sequential Execution (this feature has no independent MVP slice)

Unlike a typical product feature, there is no meaningful "MVP" subset here —
Scenario 1 alone produces no evidence, and skipping any scenario breaks the
evidence chain the reranker decision depends on. Execute in order:

1. Phase 1: Setup
2. Phase 3: Scenario 1 (corpus + questions)
3. Phase 4: Scenario 2 (diagnostic table) — **stop and check**: are failures showing up as expected, or does everything pass? Either is a valid outcome, but if literally nothing failed, reconsider whether the question set is genuinely testing retrieval difficulty before proceeding.
4. Phase 5: Scenario 3 (clean-context, failures only — skip entirely if T013 found zero failures)
5. Phase 6: Scenario 4 (classification + verdict)
6. Phase 7: Polish

---

## Notes

- [P] tasks = different files/questions, no dependencies
- [Scenario] label maps task to the spec.md scenario it belongs to
- Verify each scenario's dry-run task (T003, T007, T014, T018) before running its full pass
- Commit coherent, reviewable logical units; all changes ultimately land through a pull request per the constitution
- Stop at any checkpoint to validate a scenario's output independently
- Avoid: classifying failures before Scenario 2/3 are complete, running clean-context tests on passing questions, fixing any discovered defect instead of filing it, or building anything resembling a reusable evaluation service
