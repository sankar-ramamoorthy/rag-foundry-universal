# Feature Specification: WP-L2 — TypeScript/JavaScript Extractor

**Feature Branch**: `feat/wp-l2-typescript-js-extractor-issue-83`

**Created**: 2026-08-30

**Status**: Draft

**Tracking Issue**: #83

**Roadmap Context**: Phase 3 (multi-language support), WP-L2 per
`DOCS/audit/03-Multi-Language-Graph-Plan.md` §3. Depends on WP-L1 (#81,
shipped in #82).

**Input**: User description: "WP-L2: tree-sitter TypeScript/JavaScript
extractor — extend the read-only, graph-aware ingestion pipeline to support
TypeScript/JavaScript source files alongside the existing Python extractor,
through the language-agnostic IR and GraphAssembler introduced in WP-L1, with
symbols, imports, calls, and inheritance edges verified via a checked-in
fixture repo and golden-file/determinism tests."

## Scenarios & Testing *(mandatory)*

### User Story 1 - Symbol extraction from TS/JS source (Priority: P1)

An operator ingests a repository containing TypeScript/JavaScript files. The
system produces graph nodes for the code's structural symbols (modules,
classes, interfaces, functions, methods) so the repository is queryable the
same way a Python repository already is.

**Why this priority**: without symbol nodes, nothing else in this feature
(imports, calls, inheritance) has anything to attach to — this is the
foundation every other scenario depends on.

**Independent Test**: ingest a fixture `.ts`/`.js` file containing a class, an
interface, a top-level function, and a class method; confirm one node exists
per symbol with the correct kind, name, and containment (module defines
class, class defines method).

**Acceptance Scenarios**:

1. **Given** a `.ts` file with a named class and two methods, **When** it is
   ingested, **Then** one MODULE node, one CLASS node, and two METHOD nodes
   exist, and the module/class DEFINES relationships connect them.
2. **Given** a `.ts` file with a top-level `interface` declaration, **When**
   it is ingested, **Then** one INTERFACE node exists and is documentable and
   traversable the same way a CLASS node is.
3. **Given** a `.js` file with `const helper = () => {...}` at module scope
   and an anonymous callback passed to `setTimeout(() => {...})`, **When** it
   is ingested, **Then** `helper` produces a FUNCTION node but the anonymous
   callback does not produce a symbol node (its presence is only reflected in
   a metadata count).

---

### User Story 2 - Import resolution to graph edges (Priority: P1)

An operator wants to see which files depend on which other files in a
TS/JS codebase, the same way Python's IMPORTS edges already work.

**Why this priority**: import edges are the primary cross-file navigation
signal graph traversal relies on (BFS expansion) — without them, TS/JS
repositories are a set of disconnected per-file symbol islands.

**Independent Test**: ingest two fixture files where one imports a named
export from the other via a relative specifier, plus a third file importing
from an external package; confirm the in-repo edge resolves to the target
module and the external import resolves to a single shared external-package
node.

**Acceptance Scenarios**:

1. **Given** `a.ts` contains `import { helper } from "./util"` and `util.ts`
   defines `helper`, **When** both are ingested, **Then** an IMPORTS edge
   exists from `a.ts`'s module node to `util.ts`'s module node.
2. **Given** `a.ts` contains `import React from "react"`, **When** it is
   ingested, **Then** one external-package node named `react` exists and
   `a.ts` has an IMPORTS edge to it (no attempt to resolve into
   `node_modules`).
3. **Given** `index.ts` inside a directory is imported via the directory path
   with no filename (`import x from "./sub"` resolving to `./sub/index.ts`),
   **When** ingested, **Then** the edge resolves to `sub/index.ts`'s module
   node.
4. **Given** a file uses CommonJS `const { helper } = require("./util")`,
   **When** ingested, **Then** it resolves the same as the equivalent ESM
   named import.

---

### User Story 3 - Call and inheritance resolution (Priority: P2)

An operator wants call-graph and class-hierarchy edges for TS/JS code, so
that "what calls this" and "what does this extend/implement" queries work
the same way they already do for Python.

**Why this priority**: this is the deepest layer of graph value (call/
inheritance BFS), but it depends on User Stories 1 and 2 already working, and
a repository is still useful for symbol/import-level queries without it —
hence P2, not P1.

**Independent Test**: ingest a fixture class hierarchy with a method calling
`this.other()` and a subclass `extends`ing a base class; confirm the CALL
edge lands on the correct method and an INHERITS edge connects the classes.

**Acceptance Scenarios**:

1. **Given** a class method containing `this.other()` where `other` is
   defined on the same class, **When** ingested, **Then** a CALL edge exists
   from the calling method to `other`.
2. **Given** `class Dog extends Animal` where both are defined in-repo,
   **When** ingested, **Then** an INHERITS edge exists from `Dog` to
   `Animal`.
3. **Given** `class Dog implements Movable` where `Movable` is an in-repo
   `interface`, **When** ingested, **Then** an INHERITS edge exists from
   `Dog` to the `Movable` INTERFACE node.
4. **Given** `interface Named extends Titled`, **When** ingested, **Then** an
   INHERITS edge exists between the two INTERFACE nodes.

---

### Edge Cases

- A bare specifier with a subpath (`import x from "lodash/fp"`) is treated as
  external, grouped under one node per top-level package.
- A relative import that doesn't resolve to any in-repo file (typo, or a file
  type not covered by this extractor) becomes an external node rather than
  being silently dropped — consistent with how Python's unresolved imports
  are handled today.
- `.tsx`/`.jsx` files are parsed with JSX syntax enabled; JSX markup itself
  produces no symbol nodes.
- A file that fails to parse (syntax error) is skipped the same way a
  Python file with a syntax error is skipped today — it does not abort the
  rest of the ingestion run.
- A repository mixing Python and TypeScript/JavaScript files ingests both
  correctly in one pass, each resolved through its own module-naming
  convention, with no cross-contamination of import resolution between them.

## Non-Goals

- No tsconfig `paths`/path-alias resolution (`@app/*` style aliases) — v1
  supports only relative (`./`, `../`) and bare specifiers. Documented as a
  known limitation, not silently attempted.
- No new language extractors beyond TypeScript/JavaScript (Rust/Java are
  WP-L3/WP-L4, tracked separately).
- No migration of the existing Python extractor to tree-sitter (WP-L5).
- No language-aware filtering in the query/retrieval API or the Gradio UI
  (WP-L6).
- No semantic type-checking or full TypeScript compiler integration — this
  extractor performs syntactic structural extraction only, the same
  syntactic-not-semantic posture the Python `ast`-based extractor already
  has.
- No validation against a large, real-world external TypeScript repository —
  this environment has no guaranteed network access; coverage is via a
  checked-in fixture repo only. Broader real-repo validation is deferred to
  manual follow-up outside this issue's acceptance criteria.

## Governing References

- Constitution: `.specify/memory/constitution.md`
- ADRs: ADR-030 (unified artifact graph / rebuild determinism), ADR-031
  (canonical identity model), ADR-032 (symbol resolution & call graph),
  ADR-036 (rebuild determinism, referenced by the multi-language plan),
  ADR-038 (pipeline construction ownership), ADR-048 (cross-artifact linking)
- Audit/roadmap: `DOCS/audit/03-Multi-Language-Graph-Plan.md` §2 (IR/target
  architecture) and §3 WP-L2 (this feature's own scope, files, and
  acceptance criteria)
- Tracking issue: #83

**Known conflicts**: None. This feature extends WP-L1's `GraphAssembler`
with a new symbol kind (INTERFACE) and a per-suffix module-convention
dispatcher; both are additive to the resolution logic WP-L1 established and
do not change identity, storage, or retrieval behavior for existing (Python)
content — see `plan.md` for why these two touches to `GraphAssembler` are
necessary and why they don't violate WP-L1's "registry + new file only"
intent for behaviorally-compatible extractors.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST extract MODULE, CLASS, INTERFACE, FUNCTION,
  and METHOD symbol nodes from `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, and
  `.cjs` files, through the same `SymbolRecord` IR contract Python symbols
  use today (no new node-shape or storage changes).
- **FR-002**: The system MUST recognize only named function declarations,
  `const name = () => {...}` / `const name = function() {...}` bindings, and
  class-property arrow functions as symbol-bearing; anonymous function
  expressions/arrows passed as arguments (e.g. callbacks) MUST NOT produce
  symbol nodes, but their count MUST be recorded in the enclosing symbol's
  metadata.
- **FR-003**: The system MUST resolve ESM `import`/`export ... from` and
  CommonJS `require()` to IMPORTS edges, using the same `ImportRecord` IR and
  edge-resolution machinery Python imports use today (no changes to
  `GraphAssembler`'s import-resolution algorithm itself).
- **FR-004**: Relative import specifiers (`./x`, `../x`) MUST resolve against
  the importing file's own directory, including resolving a bare directory
  reference to that directory's `index.{ts,tsx,js,jsx}` file, and resolving
  regardless of whether the specifier includes a file extension.
- **FR-005**: Bare (non-relative) import specifiers MUST resolve to one
  shared external-package node per top-level package name, consistent with
  how Python's external imports collapse to one node per root package.
- **FR-006**: The system MUST emit call-site evidence (`CallSite` IR) for
  function/method calls, including `this.method()` calls, so the existing
  `GraphAssembler` call-resolution logic (same-file → import binding →
  unique-global → external) produces CALL edges without any changes to that
  resolution algorithm.
- **FR-007**: The system MUST emit inheritance evidence for `extends` and
  `implements` clauses on classes, and `extends` on interfaces, sufficient
  for `GraphAssembler` to produce INHERITS edges between CLASS/INTERFACE
  nodes using its existing base-resolution algorithm.
- **FR-008**: `GraphAssembler` MUST treat INTERFACE nodes as eligible for
  DEFINES (containment), INHERITS (as both source and target), and DOCUMENTS
  (doc-to-code linking) relationships, matching how CLASS nodes are already
  treated — this is the one deliberate, additive change to `GraphAssembler`
  itself required by this feature (see Governing References above).
- **FR-009**: The repo builder MUST select the correct per-language
  module-naming convention (dotted-path for Python, extension-less relative
  path for TypeScript/JavaScript) based on each file's own suffix, so a
  single repository containing both Python and TS/JS files resolves each
  language's imports correctly in the same ingestion run.
- **FR-010**: A file that fails to parse MUST be skipped without aborting the
  rest of the ingestion run, consistent with existing per-file failure
  handling.
- **FR-011**: Re-ingesting the same unchanged TS/JS repository content MUST
  produce an identical set of nodes and edges (ADR-036 rebuild determinism),
  verified by an automated test.

### Key Entities

- **SymbolRecord (reused from WP-L1 IR)**: one instance per MODULE, CLASS,
  INTERFACE, FUNCTION, or METHOD found in a TS/JS file; `kind` gains the new
  value `INTERFACE` alongside the existing vocabulary.
- **ImportRecord (reused from WP-L1 IR)**: one instance per ESM import
  specifier or CommonJS `require()` binding.
- **CallSite (reused from WP-L1 IR)**: one instance per function/method
  invocation, including `this.`-qualified calls.
- **Fixture repo**: a small, checked-in TypeScript/JavaScript sample
  repository under `ingestion_service/tests/fixtures/ts_repo/`, covering
  classes, interfaces, arrow-function exports, `require`, ESM imports, and
  `extends`/`implements` — the golden-file basis for this feature's tests.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ingesting the fixture TS/JS repository produces the expected
  node and edge set (golden-file comparison), with zero unhandled exceptions.
- **SC-002**: 100% of relative-specifier imports in the fixture repo resolve
  to their correct in-repo target module; 100% of bare-specifier imports
  resolve to one external-package node per top-level package.
- **SC-003**: `this`-qualified calls within a class resolve to the correct
  method in the fixture repo in 100% of cases where the callee is defined on
  the same class.
- **SC-004**: `extends`/`implements` relationships in the fixture repo
  produce the expected INHERITS edges in 100% of cases.
- **SC-005**: Re-running ingestion on the unchanged fixture repo twice
  produces byte-identical node/edge sets (rebuild determinism, ADR-036).
- **SC-006**: A repository mixing Python and TS/JS files ingests both
  languages correctly in a single run, with no import-resolution
  cross-contamination between the two.

## Evaluation Evidence

**Evaluation Required**: No — this is an ingestion/extraction feature (new
graph nodes/edges from a new language), not a change to retrieval ranking,
generation, chunking, embedding, or prompt/context assembly. Principle III's
evidence-before-architecture-change gate does not apply; Principle VIII's
test-guided development (acceptance-criteria tests) applies instead and is
covered under Success Criteria and `tasks.md`.

## Assumptions

- The fixture repository is authored specifically for this feature (not
  cloned from an external source) so its exact expected graph shape can be
  known and checked into a golden file, given no guaranteed network access
  in this environment.
- "TypeScript/JavaScript" for this feature means the syntax tree-sitter's
  `typescript`/`tsx`/`javascript` grammars parse; Flow-type-only syntax
  (a JS type-annotation dialect predating TypeScript's dominance) is out of
  scope.
- Decorators (`@Component`), generics, and type annotations are recorded as
  metadata where cheaply available (mirroring how Python decorators/type
  hints are handled today) but are not required for any acceptance
  criterion in this feature.
- Overloaded function signatures (multiple `declare function f(...)` heads
  for one implementation) collapse to a single symbol, consistent with the
  multi-language plan's general overload-handling stance.
