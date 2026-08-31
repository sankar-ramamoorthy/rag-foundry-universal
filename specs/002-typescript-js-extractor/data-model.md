# Phase 1 Data Model: WP-L2 TypeScript/JavaScript Extractor

No new persisted schema. This feature reuses `document_nodes`/
`document_relationships` (ADR-030) and the WP-L1 IR dataclasses
(`ingestion_service/src/core/codebase/ir.py`) exactly as-is. What follows is
the *mapping* from TS/JS syntax to those existing shapes — not new entities.

## SymbolRecord.kind values produced by this extractor

| TS/JS construct | `kind` | `symbol_path` shape | Notes |
|---|---|---|---|
| One file | `MODULE` | `None` | one per extracted file, same as Python |
| `class X { ... }` | `CLASS` | `X` (or `Parent.X` if nested) | `metadata.bases` holds `extends`/`implements` target name strings (reuses the same field Python uses for base classes) |
| `interface X { ... }` | `INTERFACE` | `X` | **new kind** (see plan.md Constitution Exceptions); `metadata.bases` holds `extends` target name strings |
| `function f() {}` (top-level) | `FUNCTION` | `f` | |
| `const f = () => {}` / `const f = function() {}` (top-level, named binding only) | `FUNCTION` | `f` | anonymous arrows/functions do NOT produce a symbol (FR-002) |
| method inside `class`/interface method signature | `METHOD` | `X.method` | |
| class-property arrow (`method = () => {}`) | `METHOD` | `X.method` | treated identically to a declared method |

`metadata` additionally carries: `lineno`, `col_offset`, `doc_type`
(`"typescript source"` / `"javascript source"`), `is_async` (bool),
`anonymous_functions_skipped` (int, only meaningful on MODULE/CLASS/FUNCTION/
METHOD nodes whose body contains skipped anonymous callbacks — default 0).

## ImportRecord shapes produced by this extractor

Every TS/JS import is emitted with a non-`None` `imported_name` (see
research.md's "Alternatives considered" for why), so it always routes
through `GraphAssembler`'s `from X import name`-shaped resolution branch:

| TS/JS syntax | `raw_module` | `imported_name` | `alias` |
|---|---|---|---|
| `import { helper } from "./util"` | `./util` | `helper` | `None` |
| `import { helper as h } from "./util"` | `./util` | `helper` | `h` |
| `import Default from "./mod"` | `./mod` | `default` | `Default` (if renamed from the synthetic name, else `None`) |
| `import * as ns from "./mod"` | `./mod` | `*` | `ns` |
| `import "./side-effect"` | `./side-effect` | `*` | `None` — binds nothing usable, but still produces an IMPORTS edge to the target module |
| `const { helper } = require("./util")` | `./util` | `helper` | `None` |
| `const utils = require("./util")` | `./util` | `*` | `utils` |
| `export { helper } from "./util"` (re-export) | `./util` | `helper` | `None` |

`metadata.level` is always `0` (TS/JS has no dot-counted relative-import
depth — resolution of `./`/`../` happens entirely inside
`TypeScriptModuleConvention.absolute_import_base`, per research.md).

## CallSite shapes produced by this extractor

| TS/JS syntax | `callee_name` | `receiver` |
|---|---|---|
| `foo()` | `foo` | `None` |
| `this.method()` | `method` | `"this"` (new receiver literal recognized by `GraphAssembler`, alongside existing `self`/`cls`) |
| `obj.method()` | `method` | `obj` (source text of the receiver expression) |
| `ns.helper()` (namespace-imported) | `helper` | `ns` |

## InheritRecord / bases metadata

This extractor follows Python's existing precedent (`CLASS.metadata["bases"]`,
consumed by `GraphAssembler._resolve_inheritance`) rather than emitting the
unused `InheritRecord` IR dataclass — consistent with `ir.py`'s own
docstring ("`InheritRecord`... is unused until a future extractor needs
it" — this extractor doesn't need it either, since `extends`/`implements`
both reduce to "a name string this symbol's bases list should resolve
against"):

- `class Dog extends Animal implements Movable` → `metadata.bases = ["Animal", "Movable"]`
- `interface Named extends Titled` → `metadata.bases = ["Titled"]`

`GraphAssembler._resolve_inheritance` is widened (Constitution Exception #1)
to iterate CLASS **and** INTERFACE nodes when resolving `bases`, so both
produce INHERITS edges through the exact same resolution algorithm
(same-file → import binding → unique-global → EXTERNAL_SYMBOL) already used
for Python.

## Fixture repo entity/edge inventory (golden-file basis)

See `research.md`'s "Fixture repo shape" for the file list. The golden test
(`tests/codebase/test_ts_repo_graph_golden.py`) asserts on this exact
inventory — the authoritative list lives in the test itself (as sorted
tuples of `(artifact_type, canonical_id)` for nodes and
`(relation_type, from_canonical_id, to_canonical_id)` for edges), not
duplicated here, to avoid two sources of truth drifting apart.
