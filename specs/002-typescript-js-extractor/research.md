# Phase 0 Research: WP-L2 TypeScript/JavaScript Extractor

All items below were resolved by inspecting the live repo/venv, not assumed
from the audit doc.

## tree-sitter Python API (installed version, verified in-venv)

**Decision**: Use the modern (0.22+) API shape, since the installed
`tree_sitter` is 0.25.2 despite `pyproject.toml`'s permissive `>=0.20.0`
pin:

```python
from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_javascript as ts_js
import tree_sitter_typescript as ts_ts

JS_LANGUAGE = Language(ts_js.language())
TS_LANGUAGE = Language(ts_ts.language_typescript())
TSX_LANGUAGE = Language(ts_ts.language_tsx())

parser = Parser(JS_LANGUAGE)
tree = parser.parse(source_bytes)

query = Query(JS_LANGUAGE, query_source)
cursor = QueryCursor(query)
captures: dict[str, list[Node]] = cursor.captures(tree.root_node)
```

**Rationale**: Verified directly against
`ingestion_service/.venv/Lib/site-packages/tree_sitter/__init__.pyi` — the
older `Parser().set_language(...)` and `Language.query(...)` calls are
deprecated in this installed version (`Language.query` carries a
`@deprecated` decorator directing to the `Query()` constructor; `Parser`
takes `language` as a direct constructor argument). Writing to the
deprecated shape would emit warnings today and risks breaking on the next
`tree_sitter` bump.

**Alternatives considered**: Pinning `tree_sitter` down to a 0.20.x-compatible
API was rejected — the installed lockfile already resolved 0.25.2
transitively (verified in `uv.lock`), so pinning backwards would fight the
existing lock rather than work with it, for no benefit.

## Grammar packages

**Decision**: `tree-sitter-javascript` (installed: 0.25.0, exposes
`language()`) and `tree-sitter-typescript` (installed: 0.23.2, exposes
`language_typescript()` and `language_tsx()` as two distinct grammars).

**Rationale**: Both packages are already present in
`ingestion_service/uv.lock` (confirmed via `grep tree-sitter uv.lock`) as
transitive dependencies of an existing package in the lock graph, but
neither is a *direct* dependency in `pyproject.toml` yet — importing them
without declaring them would work today by accident and break silently on
the next relock if the transitive chain changes. This feature adds both as
direct dependencies.

**Alternatives considered**: `tree-sitter-language-pack` (bundles many
grammars behind one package, mentioned as an option in the audit doc) was
rejected — the two specific grammars needed are already resolved in the
lockfile at compatible versions; pulling in a large bundle package would
add ~40 unused grammars for no benefit and risk a version conflict with the
already-resolved `tree_sitter` core version.

## `.tsx`/`.jsx` grammar selection

**Decision**: extractor picks the parser by file suffix: `.tsx` → `TSX_LANGUAGE`;
`.ts` → `TS_LANGUAGE`; `.js`/`.jsx`/`.mjs`/`.cjs` → `JS_LANGUAGE`. JSX syntax
inside `.jsx`/`.js` files parses under the JavaScript grammar (which
includes JSX support) rather than needing a separate TSX-equivalent
JS grammar — verified from `tree-sitter-javascript`'s own grammar (it
already handles JSX node types; there is no separate "JS+JSX" package).

**Rationale**: matches the plan doc's suffix list exactly and avoids a
misparse (parsing `.tsx` under the plain TS grammar rejects JSX syntax).

## Module resolution string shape (`ModulePathConvention` reuse)

**Decision**: `TypeScriptModuleConvention.dotted_path(relative_path)` returns
an extension-stripped, `index`-collapsed relative path using forward
slashes as its separator (e.g. `src/util.ts` → `src/util`; `src/sub/index.ts`
→ `src/sub`) — reusing the *string-keyed map* mechanism `GraphAssembler`
already has, just with slash-separated keys instead of Python's
dot-separated ones. `absolute_import_base(relative_path, base, level)`
ignores `level` (always 0 for TS/JS — there is no dot-counting relative-import
syntax) and instead inspects whether `base` starts with `.`/`..`: if so, it
resolves `base` against `posixpath.dirname(relative_path)`, normalizes `..`
segments, and returns the same extension-stripped/index-collapsed shape; if
`base` is a bare specifier (`react`, `lodash/fp`), it is returned unchanged
so `GraphAssembler`'s existing miss-path (`root = name.split(".")[0]`,
external-module fallback) takes over exactly as it does for an unresolvable
Python import.

**Rationale**: `GraphAssembler`'s `_resolve_imports`/`_resolve_import_target`
code (`ingestion_service/src/core/codebase/graph_assembler.py`) never
assumes the map keys are dot-separated Python names — it only builds a
`dict[str, str]` from `dotted_path()` output and does exact-string /
prefix-split lookups. Confirmed by reading the method: the only
Python-specific literal is `.split(".")[0]` for computing an external
module's root name, which for a TS bare specifier with no dots (`"react"`)
returns the specifier itself unchanged — exactly the desired behavior. This
means **zero changes to `GraphAssembler`'s import-resolution algorithm are
needed** — only a new `ModulePathConvention` implementation, confirming the
plan doc's stated bet that "if the `ModulePathConvention` abstraction
survives TS, Rust and Java are easy."

**Alternatives considered**: Making TS import records always shaped as
`ImportRecord(raw_module=specifier, imported_name=None, ...)` (mirroring
Python's plain `import X` shape) was rejected — that code path in
`_resolve_import_target` looks up `name` (the raw literal specifier)
directly in `module_map` without first resolving relative specifiers
through `absolute_import_base`, which only the `from X import name` shaped
branch calls. Every TS/JS import (named, default, namespace, and CJS
`require`) is therefore emitted with a non-`None` `imported_name` — `"default"`
for default imports (matching the plan doc's "TS default exports: synthesize
`default` symbol name"), and `"*"` as a sentinel for namespace imports/whole-module
`require()` binds — so all of them route through the branch that actually
calls `absolute_import_base`. This is a property of how `ImportRecord` is
lowered/consumed today, not a new resolution rule.

## `this.method()` and class body resolution

**Decision**: emit `CallSite(callee_name=<method>, receiver="this", ...)`
for `this.x()` calls. No change needed in `GraphAssembler._resolve_call_site`:
it already special-cases `receiver in ("self", "cls")` for Python; this
feature extends that tuple to include `"this"`.

**Rationale**: `self`/`cls`/`this` all mean the same thing structurally
(enclosing-class-method lookup) — the existing branch's logic (walk to
enclosing CLASS via `parent_id` chain, look up method in hierarchy) is
language-agnostic already; only the receiver-name literal set was
Python-specific. This is a one-tuple-literal change, not new logic,
verified by reading `_resolve_call_site`'s exact implementation.

## Anonymous-callback counting (FR-002)

**Decision**: track a per-enclosing-symbol integer counter
(`metadata["anonymous_functions_skipped"]`) incremented whenever the
extractor visits a function/arrow expression with no enclosing `const name =`
or class-property binding, attached to the nearest enclosing symbol (MODULE
if at top level).

**Rationale**: matches plan doc's "anonymous callbacks are skipped
(metadata counts them)" directive at the cheapest correct granularity
(count only, no identity) — consistent with F-03's precedent (call sites
are evidence, not identity-bearing).

## Fixture repo shape

**Decision**: a small, hand-authored fixture at
`ingestion_service/tests/fixtures/ts_repo/` (not cloned from any external
source, since this environment has no guaranteed network access):

- `src/util.ts` — named export function (`export function helper() {}`),
  target of a relative import.
- `src/index.ts` — re-export/import consumer; also demonstrates a directory
  import resolving to `src/sub/index.ts`.
- `src/movable.ts` — `export interface Movable { move(): void }`.
- `src/animal.ts` — `export class Animal { speak() {} }`.
- `src/dog.ts` — `export class Dog extends Animal implements Movable { move() { this.speak(); } }`
  (exercises INHERITS ×2 and a `this.`-qualified CALL).
- `src/legacy.js` — CommonJS `const { helper } = require("./util")`, plus
  one arrow-function export and one anonymous callback (`setTimeout(() => {...})`)
  to exercise FR-002.
- `src/sub/index.ts` — target of the directory-import scenario.
- `src/external.ts` — `import React from "react"` to exercise the
  EXTERNAL_MODULE case.

**Rationale**: covers every acceptance scenario in spec.md (User Stories
1-3, all Edge Cases except the "file that fails to parse" case, which is
covered by a standalone malformed-source unit test rather than living in
the golden-file fixture, so the golden snapshot itself stays a clean
success case).
