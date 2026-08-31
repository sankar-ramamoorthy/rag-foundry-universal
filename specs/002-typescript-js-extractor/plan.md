# Implementation Plan: WP-L2 — TypeScript/JavaScript Extractor

**Branch**: `feat/wp-l2-typescript-js-extractor-issue-83` | **Date**: 2026-08-30 | **Spec**: [spec.md](./spec.md)

**Tracking Issue**: #83

**Roadmap Context**: Phase 3 (multi-language support), WP-L2 per
`DOCS/audit/03-Multi-Language-Graph-Plan.md` §3.

**Input**: Feature specification from `specs/002-typescript-js-extractor/spec.md`

## Summary

Add a tree-sitter-based TypeScript/JavaScript extractor
(`.ts/.tsx/.js/.jsx/.mjs/.cjs`) that emits the same WP-L1 IR
(`SymbolRecord`/`ImportRecord`/`CallSite`) the Python extractor already
emits, so the existing `GraphAssembler` produces MODULE/CLASS/INTERFACE/
FUNCTION/METHOD nodes, IMPORTS/CALL/INHERITS edges for TS/JS code with no
change to identity, storage, or retrieval. Two small, additive touches to
`GraphAssembler`/`RepoGraphBuilder` are required beyond "registry + new
file" (see Constitution Exceptions below): INTERFACE becomes a recognized
symbol kind, and module-convention selection becomes per-file-suffix instead
of hardcoded to Python.

## Technical Context

**Language/Version**: Python 3.10-3.12 (matches `ingestion_service`'s
existing `requires-python`); target source files are TypeScript/JavaScript,
parsed but not executed.

**Primary Dependencies**: `tree_sitter` (already declared, `>=0.20.0`;
installed version in the venv is 0.25.2 — modern API: `Language(lang_fn())`,
`Parser(language)`, `Query(language, source)`, `QueryCursor(query).captures(node)`).
`tree-sitter-typescript` (0.23.x, exposes `language_typescript()` and
`language_tsx()`) and `tree-sitter-javascript` (0.25.x, exposes
`language()`) — both already present in `ingestion_service/uv.lock` as
transitive dependencies of an existing package, but not yet declared as
direct dependencies in `ingestion_service/pyproject.toml`; this feature adds
them as direct deps (CLAUDE.md: declare deps in the specific service's
`pyproject.toml`, not just root) and runs `uv lock --upgrade-package` per
this repo's established convention (`[[memory:docker-dev-runtime-architecture]]`),
not a full relock.

**Storage**: N/A for this feature directly — reuses `document_nodes`/
`document_relationships` unchanged (ADR-030); no schema/migration work.

**Testing**: `pytest`, `pytest.mark.unit` (no DB/Docker), run from
`ingestion_service/` via `uv run pytest`, mirroring
`tests/codebase/test_repo_graph_builder.py` and `tests/codebase/test_python_extractor.py`.

**Target Platform**: Linux container (`ingestion_service` Docker image) and
local dev on Windows/macOS — tree-sitter grammar wheels are already prebuilt
per-platform via PyPI, no native toolchain required at build time.

**Project Type**: Backend service module (extraction layer within
`ingestion_service`) — not a new service, not a UI change.

**Performance Goals**: N/A — no throughput/latency target specified for this
feature; existing per-file walk-and-extract pattern is reused unchanged.

**Constraints**: Fixture-only verification (no guaranteed network access in
this environment — see spec Non-Goals); v1 has no tsconfig path-alias
resolution.

**Scale/Scope**: One new extractor module + query files + a small checked-in
fixture repo (~6-10 files). Not a rewrite of any existing extractor.

## Constitution Check

**GATE: Must pass before Phase 0 research and MUST be re-checked after
Phase 1 design.**

1. Canonical identity / deterministic ingestion impact — PASS. Identity
   assignment (`build_canonical_id`) is untouched; TS/JS symbols get IDs via
   the same `relative_path#symbol_path` scheme (ADR-031). No LLM calls
   anywhere in this extractor (parsing is purely syntactic).
2. Service and database boundary impact — N/A. No new service, no direct DB
   access added; this extractor runs inside `ingestion_service`'s existing
   pipeline, constructed the same way (`repo_graph_builder.py`, not
   `pipeline_factory.py` — codebase ingestion doesn't go through
   `build_pipeline()`, consistent with the existing Python extractor).
3. Retrieval/generation architecture change + evaluation evidence — N/A.
   This is a new extraction source, not a change to ranking, chunking,
   embedding, or generation (spec's Evaluation Evidence section: Not
   Required).
4. Model-routing provenance/fallback non-regression — N/A. No LLM/model
   routing code touched.
5. Embedding-index compatibility — N/A. No embedding model change; new
   TS/JS artifact text is embedded through the existing embedder unchanged
   (per WP-L6, language-aware embedding is explicitly future work, not this
   feature).
6. GitHub issue traceability — PASS. Tracking issue #83.
7. ADR/audit references without restatement or conflict — PASS. See
   Relevant ADRs below; no conflicts identified.
8. Test and evaluation obligations — PASS. Principle VIII (test-guided
   development) satisfied via fixture + golden-file + determinism tests
   defined in this plan/tasks; Principle III evaluation evidence is N/A per
   item 3.

Two EXCEPTION REQUIRED items are raised under Constitution Governance's
"exception must be justified explicitly" clause — see **Constitution
Exceptions / Complexity Tracking** below. Both are additive-only changes to
WP-L1 infrastructure, not violations of any Core Principle.

## Architecture Impact

**Services touched**:
- `ingestion_service` only (`src/core/extractors/`, `src/core/codebase/`)

**Database ownership impact**:
- None — no schema change, no new table, no new service touching Postgres.

**Public/API contract impact**:
- None — no new/changed HTTP endpoint. `/v1/ingest-repo` behavior is
  unchanged for Python-only repos; it additionally now processes TS/JS files
  it previously skipped.

**Canonical identity / graph impact**:
- Additive only: new `artifact_type` value `INTERFACE`; new `EXTERNAL_MODULE`/
  `EXTERNAL_SYMBOL` nodes may appear for TS/JS repos (same mechanism Python
  already uses for unresolved imports/calls). No existing Python-repo
  identity or edge changes.

**Embedding/index impact**:
- TS/JS symbol text is embedded through the existing single embedder
  (`mxbai-embed-large`), same as Python/Markdown text today — no new model,
  no re-embedding job needed (WP-L6's per-language benchmarking is future
  work, explicitly out of scope here).

**Model-routing impact**:
- None.

**Relevant ADRs**:
- ADR-030 (unified artifact graph), ADR-031 (canonical identity), ADR-032
  (symbol resolution & call graph), ADR-036 (rebuild determinism), ADR-038
  (pipeline construction ownership — N/A here, codebase ingestion doesn't
  route through it, consistent with existing Python extractor), ADR-048
  (cross-artifact linking / DOCUMENTS edges)

**Known conflicts**:
- None.

## Evaluation Plan

**Evaluation required**: No
**Reason**: Principle III/VIII applicability — this is an ingestion/
extraction feature (new graph source), not a retrieval/ranking/generation
change. See spec.md's Evaluation Evidence section.

## Required Non-Regressions

- All existing Python-repo ingestion tests remain green (`test_repo_graph_builder.py`,
  `test_python_extractor.py`, `test_call_resolution.py`, `test_imports_edges.py`,
  `test_inheritance_edges.py`, `test_graph_build_linear.py`, `test_extractor_fixes.py`,
  `test_walk_repo_ignore.py`, `test_atomic_graph_persistence.py`, `test_batch_embedding.py`).
- `GraphAssembler`'s CLASS-only behavior for a repo containing no INTERFACE
  nodes is byte-identical to today (the INTERFACE addition only widens a
  set membership check; it adds no new code path for CLASS-only inputs).
- `RepoGraphBuilder`'s Python-only behavior (single `PythonModuleConvention`)
  is preserved exactly when a repo contains no TS/JS files — the per-suffix
  dispatcher must be a strict superset of current behavior, verified by
  re-running `test_repo_graph_builder.py`'s existing self-ingestion smoke
  test (which walks `ingestion_service/src`, a Python-only tree) unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/002-typescript-js-extractor/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code (repository root)

```text
ingestion_service/
├── pyproject.toml                              # + tree-sitter-typescript, tree-sitter-javascript
├── uv.lock                                      # uv lock --upgrade-package (both)
├── src/core/
│   ├── codebase/
│   │   ├── ir.py                                # unchanged (kind vocabulary already open-ended)
│   │   ├── module_conventions.py                # + TypeScriptModuleConvention, + CompositeModuleConvention
│   │   ├── graph_assembler.py                   # + INTERFACE in definition_types/DOCUMENTABLE_TYPES/inheritance filter
│   │   └── repo_graph_builder.py                # + registry entries; assembler built with CompositeModuleConvention
│   └── extractors/
│       └── treesitter/                          # NEW package
│           ├── __init__.py
│           ├── base.py                          # parser cache, .scm query loader/runner
│           ├── typescript.py                    # TypeScriptExtractor (covers .ts/.tsx/.js/.jsx/.mjs/.cjs)
│           └── queries/
│               └── typescript/
│                   ├── symbols.scm
│                   ├── imports.scm
│                   └── calls.scm
└── tests/
    ├── fixtures/
    │   └── ts_repo/                              # NEW checked-in fixture repo
    │       ├── src/util.ts
    │       ├── src/index.ts
    │       ├── src/animal.ts
    │       ├── src/dog.ts
    │       ├── src/movable.ts
    │       ├── src/legacy.js
    │       └── src/sub/index.ts
    └── codebase/
        ├── test_typescript_extractor.py         # NEW — unit tests on the extractor in isolation
        └── test_ts_repo_graph_golden.py          # NEW — golden-file + determinism test over the fixture
```

**Structure Decision**: All changes live inside `ingestion_service`, the
sole owner of ingestion per Constitution Principle II. The new extractor
follows the existing `src/core/extractors/` convention (sibling to
`python_extractor.py`, `markdown_extractor.py`) rather than a new top-level
package, since it's the same architectural role (one extractor per
language). `extractors/treesitter/` is a sub-package (not a single file)
because, unlike the ~250-line stdlib-`ast`-based `PythonASTExtractor`, this
extractor needs a parser-instance cache (tree-sitter parsers are
per-language, reused across files) and `.scm` query text, both of which the
audit plan explicitly directs to keep separate from hand-walked visitor
code (`DOCS/audit/03-Multi-Language-Graph-Plan.md` §3 WP-L2 Directions:
"declarative tree-sitter queries per concept, not hand-walked cursors").

## Constitution Exceptions / Complexity Tracking

| Principle / Constraint | Proposed Exception or Added Complexity | Why Necessary | Simpler Compliant Alternative Rejected Because |
|-------------------------|------------------------------------------|----------------|--------------------------------------------------|
| WP-L1 acceptance criterion: "adding a new extractor requires touching only the registry + a new extractor file" (`DOCS/audit/03-Multi-Language-Graph-Plan.md` §3 WP-L1, not a Core Principle but a stated design invariant this feature must either honor or explicitly break) | Add `INTERFACE` to `GraphAssembler._attach_defines`'s `definition_types`, `DOCUMENTABLE_TYPES`, and the CLASS-only filter in `_resolve_inheritance` (3 set/filter edits, no new resolution algorithm) | TypeScript's `interface` has no Python equivalent; without this, `interface`/`extends`/`implements` on interfaces would silently produce no DEFINES/INHERITS/DOCUMENTS edges — an acceptance-criterion failure (spec FR-008, User Story 3 scenarios 3-4), not a cosmetic gap | Emitting interfaces with `kind="CLASS"` plus `metadata.is_interface=True` was considered and rejected: it would make `CLASS` do double duty as an identity concept for two different TS/JS language constructs, which ADR-031 canonical-identity discipline treats as a modeling decision, not a query hack — a real `artifact_type` value is the honest representation, and the plan doc's own target architecture table already names `INTERFACE` as a first-class kind (§2) |
| Same WP-L1 acceptance criterion | Replace `RepoGraphBuilder`'s single hardcoded `GraphAssembler(module_convention=PythonModuleConvention())` with a small per-suffix dispatching convention (new `CompositeModuleConvention` in `module_conventions.py`) | A repo can contain both `.py` and `.ts` files; Python's dotted-path convention and TypeScript's relative-path convention produce incompatible module-map keys — a single global convention cannot resolve both correctly in one ingestion run (spec FR-009, Edge Cases, SC-006) | Running two separate `GraphAssembler.assemble()` passes (one per language) over disjoint file subsets was considered and rejected: cross-language import/call resolution would need to merge two independently-built `RepoGraph`/symbol-table instances after the fact, which is strictly more code and a new merge-correctness burden, for a repo shape (mixed-language) the single-dispatcher approach handles for free by construction |

Both exceptions are additive/widening changes to WP-L1 code, not
algorithmic rewrites: no existing resolution branch changes behavior for
inputs it already handled (verified by the Required Non-Regressions above
and the regression suite in `tasks.md`).
