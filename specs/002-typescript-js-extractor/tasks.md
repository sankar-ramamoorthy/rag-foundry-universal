# Tasks: WP-L2 — TypeScript/JavaScript Extractor

**Input**: Design documents from `specs/002-typescript-js-extractor/`

**Tracking Issue**: #83
**Spec**: `specs/002-typescript-js-extractor/spec.md`
**Plan**: `specs/002-typescript-js-extractor/plan.md`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md (all present; no `contracts/` — internal extraction feature, no external interface contract per plan.md's "skip if purely internal" guidance)

**Tests**: Required by Constitution Principle VIII. Every implementation task below has a test task before or alongside it; all tests are `pytest.mark.unit` (no DB/Docker), matching this feature's existing test posture (plan.md Technical Context).

## Constitution Compliance

Plan.md's Constitution Check passed with two documented, justified exceptions
(INTERFACE as a new symbol kind; per-suffix `CompositeModuleConvention`) —
both additive-only to `GraphAssembler`/`RepoGraphBuilder`, tracked in tasks
T015 and T007-T008 below. No task in this list crosses a service/DB
boundary, changes retrieval/generation architecture, or bypasses the
issue/PR/test requirement.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

All paths are under `ingestion_service/` (the sole owner of ingestion per
Constitution Principle II) — see plan.md's Project Structure.

---

## Phase 1: Setup

- [ ] T001 Add `tree-sitter-typescript` and `tree-sitter-javascript` as direct dependencies in `ingestion_service/pyproject.toml` (versions matching what's already resolved in `uv.lock` per research.md: tree-sitter-typescript 0.23.x, tree-sitter-javascript 0.25.x)
- [ ] T002 Run `uv lock --upgrade-package tree-sitter-typescript --upgrade-package tree-sitter-javascript` from `ingestion_service/` (not a full relock, per project convention) and verify `uv sync` succeeds
- [ ] T003 [P] Create the `ingestion_service/src/core/extractors/treesitter/` package (`__init__.py`, empty `queries/typescript/` directory)
- [ ] T004 [P] Create the fixture repo directory `ingestion_service/tests/fixtures/ts_repo/src/` with empty placeholder files matching research.md's fixture shape (`util.ts`, `index.ts`, `movable.ts`, `animal.ts`, `dog.ts`, `legacy.js`, `external.ts`, `sub/index.ts`) — content filled in per-story below

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 Implement the tree-sitter parser/language cache and `.scm` query runner in `ingestion_service/src/core/extractors/treesitter/base.py`, using the verified modern API from research.md (`Language(lang_fn())`, `Parser(language)`, `Query(language, source)`, `QueryCursor(query).captures(node)`), selecting `TS_LANGUAGE`/`TSX_LANGUAGE`/`JS_LANGUAGE` by file suffix
- [ ] T006 [P] Add `TypeScriptModuleConvention` to `ingestion_service/src/core/codebase/module_conventions.py` implementing `dotted_path`/`absolute_import_base` per research.md's extension-stripped, index-collapsed, slash-separated scheme
- [ ] T007 [P] Add `CompositeModuleConvention` to `ingestion_service/src/core/codebase/module_conventions.py` that dispatches `dotted_path`/`absolute_import_base` to a per-suffix `ModulePathConvention` (this is the plan.md Constitution Exception #2)
- [ ] T008 Update `ingestion_service/src/core/codebase/repo_graph_builder.py` to build its `GraphAssembler` with a `CompositeModuleConvention` mapping `.py` → `PythonModuleConvention()` and the new TS/JS suffixes → `TypeScriptModuleConvention()` (depends on T006, T007)
- [ ] T009 Create a minimal `TypeScriptExtractor` stub (constructor + `extract()` returning an empty `ExtractionResult` plus a MODULE symbol, matching `PythonASTExtractor`'s shape) in `ingestion_service/src/core/extractors/treesitter/typescript.py`, and register it in `EXTRACTORS` in `repo_graph_builder.py` for `.ts`/`.tsx`/`.js`/`.jsx`/`.mjs`/`.cjs` (depends on T005)
- [ ] T010 Regression check: re-run `ingestion_service/tests/codebase/test_repo_graph_builder.py` (walks the Python-only `ingestion_service/src` tree) and confirm it is unchanged after T006-T009 — required non-regression from plan.md

**Checkpoint**: Foundation ready — TS/JS files are recognized and produce an empty-but-valid MODULE node; Python-only behavior is provably unchanged.

---

## Phase 3: User Story 1 - Symbol extraction from TS/JS source (Priority: P1) 🎯 MVP

**Goal**: TS/JS files produce correctly-typed MODULE/CLASS/INTERFACE/FUNCTION/METHOD nodes with correct DEFINES containment.

**Independent Test**: ingest a fixture `.ts` file with a class, an interface, a top-level function, and a class method; confirm one node per symbol with correct kind/name/containment (spec User Story 1).

### Tests for User Story 1

- [ ] T011 [P] [US1] Unit tests for symbol-kind extraction (MODULE/CLASS/INTERFACE/FUNCTION/METHOD, named-binding arrow functions, class-property arrows, anonymous-callback counting per FR-002) in `ingestion_service/tests/codebase/test_typescript_extractor.py`, using inline source snippets

### Implementation for User Story 1

- [ ] T012 [US1] Author `ingestion_service/tests/fixtures/ts_repo/src/animal.ts` (`export class Animal { speak() {} }`), `movable.ts` (`export interface Movable { move(): void }`), and the symbol-only parts of `legacy.js` (a named arrow export + one anonymous `setTimeout` callback) — content only, no import/call/inherits wiring yet (that lands in US2/US3)
- [ ] T013 [US1] Write `ingestion_service/src/core/extractors/treesitter/queries/typescript/symbols.scm` capturing class/interface/function-declaration/method/class-property-arrow/const-arrow nodes
- [ ] T014 [US1] Implement symbol extraction in `TypeScriptExtractor.extract()` (`ingestion_service/src/core/extractors/treesitter/typescript.py`): MODULE/CLASS/INTERFACE/FUNCTION/METHOD `SymbolRecord`s, `metadata.anonymous_functions_skipped` counting, `metadata.is_async`, raising on `tree.root_node.has_error` so `RepoGraphBuilder`'s existing per-file `except Exception: continue` skips unparseable files exactly like Python's `ast.parse` does today (depends on T013)
- [ ] T015 [US1] Widen `GraphAssembler` in `ingestion_service/src/core/codebase/graph_assembler.py` to treat `INTERFACE` like `CLASS` for `_attach_defines`'s `definition_types`, `DOCUMENTABLE_TYPES`, and the class-selection filter in `_resolve_inheritance` (plan.md Constitution Exception #1 — set/filter widening only, no new resolution branch)
- [ ] T016 [US1] Unit tests: ingesting `animal.ts`/`movable.ts`/`legacy.js` via `RepoGraphBuilder` produces one CLASS, one INTERFACE, correctly-typed FUNCTION/METHOD nodes, correct DEFINES edges, and `anonymous_functions_skipped == 1` on `legacy.js`'s MODULE metadata, in `ingestion_service/tests/codebase/test_ts_repo_graph_golden.py`

**Checkpoint**: User Story 1 fully functional and independently testable — symbol nodes exist and are correctly typed/contained.

---

## Phase 4: User Story 2 - Import resolution to graph edges (Priority: P1)

**Goal**: ESM and CommonJS imports resolve to IMPORTS edges, matching Python's import-resolution behavior.

**Independent Test**: two fixture files where one imports a named export from the other via a relative specifier, plus a third importing from an external package (spec User Story 2).

### Tests for User Story 2

- [ ] T017 [P] [US2] Unit tests for `ImportRecord` shapes emitted per data-model.md's table (named/default/namespace ESM imports, side-effect import, CJS `require` destructured and whole-module) in `ingestion_service/tests/codebase/test_typescript_extractor.py`

### Implementation for User Story 2

- [ ] T018 [US2] Author `ingestion_service/tests/fixtures/ts_repo/src/util.ts` (`export function helper() {}`), `index.ts` (imports `helper` from `./util` and default-imports from `./sub`), `sub/index.ts` (default export target), and `external.ts` (`import React from "react"`)
- [ ] T019 [US2] Write `ingestion_service/src/core/extractors/treesitter/queries/typescript/imports.scm` capturing ESM `import`/`export ... from` specifiers and CommonJS `require()` call expressions
- [ ] T020 [US2] Implement import extraction in `TypeScriptExtractor` per data-model.md's `ImportRecord` table — every TS/JS import emitted with non-`None` `imported_name` (`"default"` / `"*"` sentinels as documented) so it always routes through `GraphAssembler`'s `from X import name`-shaped resolution branch (depends on T019)
- [ ] T021 [US2] Unit tests for `TypeScriptModuleConvention.absolute_import_base`: `./util` resolves relative to the importing file's directory, `./sub` resolves to `sub/index.ts`, bare `react` passes through unchanged, in `ingestion_service/tests/codebase/test_typescript_extractor.py`
- [ ] T022 [US2] Unit tests: ingesting `index.ts`/`util.ts`/`sub/index.ts`/`external.ts` produces an IMPORTS edge from `index.ts` to `util.ts`'s MODULE node, an IMPORTS edge from `index.ts` to `sub/index.ts`'s MODULE node, and one `EXTERNAL_MODULE:react` node with an IMPORTS edge from `external.ts`, in `ingestion_service/tests/codebase/test_ts_repo_graph_golden.py`

**Checkpoint**: User Stories 1 and 2 both work independently — symbol graph plus cross-file import edges.

---

## Phase 5: User Story 3 - Call and inheritance resolution (Priority: P2)

**Goal**: `this`-qualified calls and `extends`/`implements` clauses produce CALL and INHERITS edges through the existing resolution algorithm.

**Independent Test**: a class method calling `this.other()` and a subclass extending a base class (spec User Story 3).

### Tests for User Story 3

- [ ] T023 [P] [US3] Unit tests for `CallSite` extraction (bare call, `this.method()`, `obj.method()`, namespace-qualified call) in `ingestion_service/tests/codebase/test_typescript_extractor.py`

### Implementation for User Story 3

- [ ] T024 [US3] Author `ingestion_service/tests/fixtures/ts_repo/src/dog.ts`: `export class Dog extends Animal implements Movable { move() { this.speak(); } }`, and add an `interface Named extends Titled` pair for the interface-extends-interface scenario
- [ ] T025 [US3] Write `ingestion_service/src/core/extractors/treesitter/queries/typescript/calls.scm` capturing call-expression nodes (bare identifier calls and member-expression calls, including `this.`-qualified)
- [ ] T026 [US3] Implement call-site extraction in `TypeScriptExtractor` (`callee_name`/`receiver` split per data-model.md, `receiver="this"` for `this.x()`) (depends on T025)
- [ ] T027 [US3] Add `"this"` to the receiver tuple in `GraphAssembler._resolve_call_site` (`ingestion_service/src/core/codebase/graph_assembler.py`) alongside the existing `("self", "cls")` — one-literal widening, no new logic (research.md)
- [ ] T028 [US3] Implement `extends`/`implements` extraction as `metadata.bases` string lists on CLASS and INTERFACE `SymbolRecord`s in `TypeScriptExtractor`, reusing the existing field Python's `bases` metadata already populates (no new IR shape)
- [ ] T029 [US3] Unit tests: ingesting `dog.ts` produces a CALL edge from `Dog.move` to `Animal.speak` (via `this`), an INHERITS edge `Dog → Animal`, an INHERITS edge `Dog → Movable`, and an INHERITS edge `Named → Titled`, in `ingestion_service/tests/codebase/test_ts_repo_graph_golden.py`

**Checkpoint**: All three user stories independently functional; the full fixture repo now exercises every acceptance scenario in spec.md.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T030 [P] Golden-file snapshot test: assert the complete sorted node/edge inventory (`(artifact_type, canonical_id)` and `(relation_type, from_canonical_id, to_canonical_id)` tuples) for the full `ts_repo` fixture in `ingestion_service/tests/codebase/test_ts_repo_graph_golden.py` (SC-001)
- [ ] T031 [P] Rebuild-determinism test: run `RepoGraphBuilder` twice over the unchanged `ts_repo` fixture and assert byte-identical sorted node/edge sets, in `ingestion_service/tests/codebase/test_ts_repo_graph_golden.py` (ADR-036, SC-005)
- [ ] T032 [P] Malformed-source unit test: a `.ts` file with a deliberate syntax error is skipped by `RepoGraphBuilder.build()` without aborting the rest of ingestion, in `ingestion_service/tests/codebase/test_typescript_extractor.py` (verifies T014's `has_error` → raise → skip behavior)
- [ ] T033 [P] Mixed-language regression test: a small fixture directory containing both a `.py` file and a `.ts` file ingests both correctly in one `RepoGraphBuilder.build()` call with no import-resolution cross-contamination, in `ingestion_service/tests/codebase/test_repo_graph_builder.py` (SC-006)
- [ ] T034 Run the full existing unit suite (`uv run pytest -m unit` from `ingestion_service/`) and confirm every pre-existing test remains green (Required Non-Regressions in plan.md)
- [ ] T035 [P] Update `DOCS/audit/03-Multi-Language-Graph-Plan.md` §3 WP-L2 to check off delivered acceptance criteria and note the two `GraphAssembler`/`RepoGraphBuilder` exceptions actually landed (cross-reference plan.md's Constitution Exceptions table)
- [ ] T036 [P] Add a `DOCS/log.md` entry recording WP-L2's delivery, per this repo's established log convention
- [ ] T037 Run `specs/002-typescript-js-extractor/quickstart.md` end-to-end and confirm every documented expected outcome holds

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — BLOCKS all user stories (T008/T009 need T005-T007; nothing in TS/JS ingestion works before this phase completes)
- **User Story 1 (Phase 3)**: depends on Foundational only
- **User Story 2 (Phase 4)**: depends on Foundational only; independently testable without US1, though the shared `ts_repo` fixture accumulates files across stories (US2's own fixture files don't require US1's)
- **User Story 3 (Phase 5)**: depends on Foundational and on T015 (INTERFACE support, from US1) for the interface-extends-interface scenario in T024/T029 — this is the one cross-story dependency, and it's a read-only dependency (US3 doesn't modify anything US1 built)
- **Polish (Phase 6)**: depends on all three user stories being complete

### Parallel Opportunities

- T003, T004 in parallel (Setup)
- T006, T007 in parallel (Foundational, same file but non-overlapping additions — verify no merge conflict before landing both)
- T011 can start as soon as T009 lands (stub extractor), in parallel with T012
- T017, T023 similarly parallel with their respective fixture-authoring tasks once Foundational is done
- T030-T033, T035, T036 are independent files/concerns and can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup → Phase 2 Foundational → Phase 3 (US1)
2. **STOP and VALIDATE**: `uv run pytest tests/codebase/test_typescript_extractor.py tests/codebase/test_ts_repo_graph_golden.py -v` — symbol nodes for a TS/JS repo now exist and are correctly typed, independent of import/call resolution working at all

### Incremental Delivery

1. Setup + Foundational → TS/JS files recognized, Python behavior provably unchanged (T010)
2. + US1 → symbol graph (MVP)
3. + US2 → cross-file import edges
4. + US3 → call graph + class hierarchy
5. + Polish → golden snapshot, determinism, mixed-language regression, docs updated, full suite green
