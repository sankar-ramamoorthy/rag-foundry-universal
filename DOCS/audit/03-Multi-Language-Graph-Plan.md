---
title: "Multi-Language Graph Plan — Rust, TypeScript, Java, JavaScript"
date: 2026-07-09
type: audit-plan
status: proposed
languages: [python, rust, typescript, javascript, java]
tags:
  - audit
  - multi-language
  - tree-sitter
  - rag-foundry
related:
  - "[[02-Graph-Depth-Analysis]]"
  - "[[00-Audit-Overview]]"
  - "[[../adr/ADR-031-canonical-identity-model|ADR-031]]"
---

# 🌐 Multi-Language Graph Plan

> [!abstract] Goal
> Extend the artifact graph beyond Python to **Rust, TypeScript, JavaScript, and Java**, without forking the identity model, storage schema, or retrieval layer.

## 1 · Strategic assessment

> [!tip] Evidence for the "retrieval is already language-ready" row (2026-08-27)
> The WP-Q0 RAG-quality baseline (issue #49, `DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`) empirically confirms the retrieval-layer claim below, not just architecturally: on the eval corpus, raw vector search alone hit Recall@5 = 70%, while the production path (vector seed + deterministic BFS graph expansion) hit 90% — graph expansion recovered questions vector similarity missed on its own. Because that expansion is entirely language-agnostic (typed-edge BFS over `document_relationships`, never inspecting Python syntax), this result should carry forward unchanged as new language extractors land through the IR in §2 below — the retrieval/expansion layer is not something Rust/TS/Java support needs to touch.

The architecture is **already language-ready** in the places that matter:

| Layer | Language-coupled? | Evidence |
|---|---|---|
| Storage (`document_nodes` / `document_relationships`) | ❌ No | `artifact_type` and `relation_type` are strings; ADR-030 |
| Identity (`path#Symbol.path`) | ❌ No | ADR-031 format is language-neutral |
| Retrieval (BFS over typed edges) | ❌ No | `codebase_queries.py` never mentions Python; empirically measured in WP-Q0 (see callout above) |
| Extraction | ✅ **Hard-coupled** | `PythonASTExtractor` uses stdlib `ast`; `_select_extractor` switches on `.py`/`.md` only (`repo_graph_builder.py:273`) |
| Builder resolution passes | ⚠️ Semi-coupled | `_resolve_calls`/symbol table assume Python naming; logic is generic in shape |

So this is an **extraction-layer project**: introduce a language-agnostic intermediate representation (IR) and per-language extractors that emit it. `tree_sitter>=0.20.0` is *already declared* in `ingestion_service/pyproject.toml` but never imported — the dependency bet was placed and never executed.

> [!important] Decision required first: parser strategy
> **Recommendation: tree-sitter for all five languages, including migrating Python to it eventually.**
> - One parsing framework, one query idiom (`.scm` query files), incremental parsing for free, error-tolerant (parses broken/partial code — important for real repos).
> - Per-language official grammars: `tree-sitter-rust`, `tree-sitter-typescript` (covers TSX), `tree-sitter-javascript`, `tree-sitter-java`, `tree-sitter-python`.
> - Alternative rejected: per-language native parsers (rust-analyzer, TS compiler API, javac) — much richer semantics but 4 runtimes, 4 toolchains, and services in 3 languages. Wrong trade at this stage. Revisit per-language *semantic backends* (e.g. SCIP/LSIF indexers) as a **later enrichment pass**, not the foundation.
> - Keep the existing Python `ast` extractor working during the transition; migrate it to tree-sitter last, behind the same IR, once parity tests pass.

## 2 · Target architecture

```
                    ┌──────────────────────────────┐
 repo files ──────► │  ExtractorRegistry            │
                    │  (.py .rs .ts .tsx .js .java) │
                    └──────┬───────────────────────┘
                           ▼ emits IR (language-agnostic)
                    ┌──────────────────────────────┐
                    │ IR: SymbolRecord / ImportRecord / CallSite / InheritRecord
                    └──────┬───────────────────────┘
                           ▼
                    ┌──────────────────────────────┐
                    │ GraphAssembler (ONE impl)     │
                    │  identity · DEFINES · IMPORTS │
                    │  CALL · INHERITS · DOCUMENTS  │
                    └──────┬───────────────────────┘
                           ▼
                 document_nodes / document_relationships (unchanged)
```

### The IR (the heart of the plan)

```python
@dataclass(frozen=True)
class SymbolRecord:
    kind: str            # MODULE|CLASS|FUNCTION|METHOD|INTERFACE|TRAIT|IMPL|STRUCT|ENUM
    name: str
    symbol_path: str     # dot-separated, e.g. "MyStruct.new"  → canonical_id = f"{path}#{symbol_path}"
    parent_symbol_path: str | None
    span: tuple[int, int]        # (lineno, end_lineno)
    text: str                    # full source slice (ADR-039/041)
    signature: str | None
    docstring: str | None
    metadata: dict               # language, is_async, visibility, decorators/annotations/attributes…

@dataclass(frozen=True)
class ImportRecord:
    raw_module: str              # what the source says: "crate::util", "./util", "com.acme.Util"
    imported_name: str | None
    alias: str | None
    span: tuple[int, int]

@dataclass(frozen=True)
class CallSite:
    callee_name: str             # bare name
    receiver: str | None         # "self", "this", expr text, or None
    caller_symbol_path: str      # enclosing symbol
    span: tuple[int, int]

@dataclass(frozen=True)
class InheritRecord:
    child_symbol_path: str
    parent_name: str             # unresolved name/path text
    kind: str                    # EXTENDS|IMPLEMENTS|TRAIT_IMPL
```

Each language extractor is *only* responsible for producing correct IR. **All** resolution (imports → module map, calls → symbols, inheritance) lives once in `GraphAssembler` — which is exactly the fixed/deepened logic from [[02-Graph-Depth-Analysis#WP-G2]]–[[02-Graph-Depth-Analysis#WP-G5|WP-G5]], parameterized by a small per-language `ModulePathConvention` (how file paths map to importable module names).

### Language-specific mapping decisions (make them now, in code review, not ad hoc)

| Concept | Rust | TypeScript/JS | Java |
|---|---|---|---|
| MODULE | file (`mod.rs`/`lib.rs` naming rules) | file | file (class-per-file, package from `package` decl) |
| CLASS-like | `struct`, `enum`, `trait`, `impl` blocks → kinds `STRUCT`/`ENUM`/`TRAIT`/`IMPL` | `class`, `interface` | `class`, `interface`, `enum`, `record` |
| METHOD | fn inside `impl` → symbol_path `Type.method` (merge impl blocks into the type's namespace) | class methods; also arrow-function properties | methods |
| FUNCTION | free `fn` | function decls **and** exported arrow/function expressions bound to `const` | static methods only (no free functions) |
| IMPORTS | `use` paths (`crate::`, `super::`, `self::`) | ESM `import`/`export from`, CJS `require()` (best-effort) | `import` statements + same-package implicit (skip implicit in v1) |
| INHERITS | `impl Trait for Type` → `TRAIT_IMPL` | `extends`/`implements` | `extends`/`implements` |
| Async | `async fn` flag | `async` flag | n/a |
| Overloads/generics | monomorphic names only (drop generics from identity) | drop type params from identity | overloads share one symbol_path; store arity list in metadata |

> [!warning] Identity rules that must hold across all languages (ADR-031)
> - `canonical_id = relative_path[#symbol_path]`, dot-separated symbol path, no generics/param types/line numbers.
> - Same input tree ⇒ byte-identical IDs on rebuild (ADR-036) — sort everything before emit.
> - Java nested classes: `Outer.Inner.method`. Rust impl methods: `Type.method` regardless of which impl block. TS default exports: synthesize `default` symbol name.

## 3 · Work packages

### WP-L1 — IR + GraphAssembler refactor (the enabler)
**Goal:** current Python pipeline runs unchanged in behavior but through `SymbolRecord/ImportRecord/CallSite` IR and a language-agnostic `GraphAssembler`.
**Files:** new `ingestion_service/src/core/codebase/ir.py`, `graph_assembler.py`, `module_conventions.py`; rewrite `repo_graph_builder.py` as thin orchestration; adapt `python_extractor.py` to emit IR.
**Directions:** fold in [[02-Graph-Depth-Analysis]] WP-G1…G5 here — implement resolution once, correctly, in the assembler. Registry pattern for extractors: `EXTRACTORS: dict[str, type[BaseExtractor]]` keyed by suffix.
**Acceptance criteria:**
- [ ] Ingesting the project's own repo pre- and post-refactor yields identical `document_nodes`/`document_relationships` rows (modulo intentional WP-G fixes, which land with their own tests)
- [ ] `GraphAssembler` has zero imports from `ast` or any tree-sitter module
- [ ] Adding a new extractor requires touching only the registry + new extractor file

### WP-L2 — tree-sitter runtime + TypeScript/JavaScript extractor (first new language)
**Status:** Shipped (issue #83, `specs/002-typescript-js-extractor/`).
**Goal:** `.ts/.tsx/.js/.jsx/.mjs/.cjs` files produce MODULE/CLASS/INTERFACE/FUNCTION/METHOD nodes, IMPORTS (ESM + `require`), CALL sites, EXTENDS/IMPLEMENTS.
**Why TS first:** biggest enterprise demand; exercises the hardest module-resolution rules (relative paths, `index.ts`, extensionless imports) — if the `ModulePathConvention` abstraction survives TS, Rust and Java are easy.
**Files:** new `extractors/treesitter/base.py` (parser cache, `.scm` query runner), `extractors/treesitter/typescript.py`, query files under `extractors/treesitter/queries/typescript/*.scm`; added `tree-sitter-typescript`/`tree-sitter-javascript` to `ingestion_service/pyproject.toml` (both were already transitive lock entries — promoted to direct dependencies).
**Directions:**
- Use declarative tree-sitter **queries** (`.scm`) per concept, not hand-walked cursors — keeps per-language code small and reviewable.
- Module resolution: relative specifiers only in v1 (`./x`, `../x`, `/index` resolution, drop extensions); bare specifiers (`react`) → `EXTERNAL_MODULE`. **No tsconfig `paths` support in v1** — document as limitation.
- Arrow functions: only named bindings (`const f = () =>`) and class-property arrows become symbols; anonymous callbacks are skipped (metadata counts them).
**Delivery notes (beyond what this plan anticipated):**
- `GraphAssembler`/`RepoGraphBuilder` needed two additive touches, not zero: `INTERFACE` added to `definition_types`/`DOCUMENTABLE_TYPES`/the inheritance-resolution filter, and a new `CompositeModuleConvention` dispatching per-suffix so a repo can mix Python and TS/JS in one ingestion run. See `specs/002-typescript-js-extractor/plan.md`'s Constitution Exceptions table for the full justification.
- `symbol_table.py` also needed `INTERFACE` added to its indexed-type set — discovered only by an end-to-end smoke test, not by inspection: `implements SomeInterface` silently fell through to `EXTERNAL_SYMBOL` without it, since base-class/interface resolution reads through the symbol table, not `graph.entities` directly.
- TS default exports (`export default function f() {}`) needed both `symbol_path` **and** `name` synthesized to the literal string `"default"` (not just identity) — `SymbolTable` indexes by `name`, so a default-imported binding's cross-file lookup only succeeds if the exporting symbol's `name` is literally `"default"` too. The originally-declared name is preserved in `metadata.declared_name`.
**Acceptance criteria:**
- [x] Fixture repo (checked into `tests/fixtures/ts_repo/`) with classes, interfaces, arrow exports, `require`, ESM imports, `extends`/`implements` produces the expected node/edge snapshot (golden-file test)
- [x] `import { helper } from "./util"` → IMPORTS edge to `util.ts` module node; `from "react"` → EXTERNAL_MODULE
- [x] `this.method()` calls resolve within the class
- [ ] Ingesting a real mid-size TS repo (e.g. a clone of `fastify` or similar) completes and logs zero unhandled exceptions — **deferred**: this environment has no guaranteed network access; fixture-based coverage only (see spec.md Non-Goals). Left as a manual follow-up.
- [x] Rebuild determinism test passes

### WP-L3 — Rust extractor
**Goal:** `.rs` files produce MODULE/STRUCT/ENUM/TRAIT/IMPL/FUNCTION/METHOD, `use`-based IMPORTS, CALL sites, TRAIT_IMPL edges.
**Files:** `extractors/treesitter/rust.py` + queries.
**Directions:** module map must encode Rust's file→module rules (`src/lib.rs` = crate root, `foo/mod.rs` ≡ `foo.rs`, path = crate::… within one crate; multi-crate workspaces: treat each `Cargo.toml` dir as a namespace prefix). `impl Type { fn m }` → symbol `Type.m`; `impl Trait for Type` → TRAIT_IMPL edge + methods under `Type.m`. Macros: skip bodies, record `macro_invocation` metadata counts.
**Acceptance criteria:**
- [ ] Fixture crate with `mod` tree, trait + impl, cross-module `use crate::…` produces expected golden snapshot
- [ ] `Type::new()` and method-on-`self` call sites resolve to `Type.new` / enclosing type methods
- [ ] Workspace with two crates: no canonical-ID collisions between same-named modules
- [ ] Determinism test

### WP-L4 — Java extractor
**Goal:** `.java` files produce CLASS/INTERFACE/ENUM/RECORD/METHOD nodes, IMPORTS edges, EXTENDS/IMPLEMENTS, CALL sites.
**Directions:** package decl + class name → module identity (still `canonical_id = relative_path#Outer.Inner.method` — the *path* remains the namespace per ADR-031; store `package.fqcn` in metadata for search). Overloads: single symbol_path, `metadata.overload_signatures=[…]`. Annotations → metadata like decorators.
**Acceptance criteria:**
- [ ] Fixture with packages, nested classes, interface implementation, overloads → golden snapshot
- [ ] `import com.acme.Util` + `Util.calc()` resolves cross-file when `com/acme/Util.java` is in-repo, else EXTERNAL
- [ ] Determinism test

### WP-L5 — Python on tree-sitter (parity migration, last)
**Goal:** retire stdlib-`ast` extractor; one framework everywhere; unlocks parsing Python files with syntax errors.
**Directions:** build alongside; run **A/B parity harness** (ingest N repos with both, diff node/edge sets); cut over when diff = ∅ on the corpus; keep `ast` version one release as fallback flag.
**Acceptance criteria:**
- [ ] Parity harness reports zero diffs on ≥5 varied real repos
- [ ] File with a syntax error yields partial artifacts instead of file skip (improvement over today's `except: continue`)

### WP-L6 — Query/UI awareness of language
**Status:** Retrieval-filter half shipped as WP-L6a (issue #85, PR TBD,
`specs/003-language-aware-retrieval/`), pulled forward ahead of WP-L3/L4
because it doubles as the measurement apparatus for validating WP-L2
against a real mixed-language repo. UI half (Gradio dropdown) remains open.
**Goal:** language surfaces in retrieval + UI.
**Directions:** `metadata.language` on every node (assembler sets it from extractor); optional `language` filter on `/v1/rag` and vector search metadata filter; Gradio dropdown. Embedding note: keep one embedder for all languages (code-capable embedder already in use); benchmark per-language recall later — do **not** fork embedders per language now.
**Delivery note (WP-L6a):** `language` is derived centrally in
`GraphAssembler` from file suffix (`LANGUAGE_BY_SUFFIX`), not set
per-extractor as this directive originally phrased it — see
`specs/003-language-aware-retrieval/plan.md`'s Constitution Exceptions
table for why. Promoted to a typed, indexed `vector_chunks.language`
column — the fourth typed column WP-S4B (`DOCS/audit/04-Scalability-Plan.md`)
had already anticipated but never implemented.
**Acceptance criteria:**
- [x] Vector chunks carry `language` in `source_metadata` (WP-L6a)
- [x] `/v1/rag` accepts optional `language` param and filters seeds accordingly (WP-L6a)
- [ ] Gradio dropdown (remaining WP-L6 scope, not part of WP-L6a)

## 4 · Effort & sequencing

| WP | Depends on | Est. (agent-assisted) |
|---|---|---|
| WP-L1 IR refactor | [[02-Graph-Depth-Analysis]] WP-G1/G3 recommended first | 1–2 weeks |
| WP-L2 TypeScript/JS | WP-L1 | 1–2 weeks |
| WP-L3 Rust | WP-L2 (framework exists) | 1 week |
| WP-L4 Java | WP-L2 | 1 week |
| WP-L5 Python parity | WP-L2 | 3–5 days |
| WP-L6 Language filters | any extractor live | 2–3 days |

> [!tip] Test-fixture discipline
> Each language gets a small **fixture repo under version control** + golden-file snapshot of expected nodes/edges. This is the multi-language equivalent of the project's TGD rule — behavior-observable acceptance, and it doubles as the determinism regression suite (ADR-036).
