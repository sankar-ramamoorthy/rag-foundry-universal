---
title: "Graph Depth Analysis — Is the graph too shallow?"
date: 2026-07-09
type: audit-analysis
status: complete
verdict: "Yes — too shallow, and partially broken"
tags:
  - audit
  - graph
  - code-intelligence
  - rag-foundry
related:
  - "[[01-Codebase-Audit-Findings]]"
  - "[[03-Multi-Language-Graph-Plan]]"
  - "[[../adr/ADR-032-symbol-resolution-call-graph|ADR-032]]"
---

# 🕸️ Graph Depth Analysis

> [!question] The question asked
> **"Is the graph too shallow?"**

> [!success] Verdict
> **Yes.** Today the graph is a *containment tree with a partial call overlay* — not a code-intelligence graph. Three edge types actually materialize (`DEFINES`, `CALL`, `DOCUMENTS`); of those, `CALL` is unreliable (see [[01-Codebase-Audit-Findings#F-03 · CALL canonical IDs collide and overwrite each other|F-03]]/[[01-Codebase-Audit-Findings#F-04 · Method calls essentially never resolve|F-04]]) and `IMPORT` edges advertised by the query layer **do not exist** ([[01-Codebase-Audit-Findings#F-02 · `IMPORT` relationships are never created|F-02]]). The good news: the storage model (two tables, typed edges, canonical IDs) needs **no schema change** to go much deeper — this is extractor/builder work, not migration work.

## 1 · What the graph captures today

**Node types** (from `python_extractor.py` + `markdown_extractor.py`):
`MODULE`, `CLASS`, `FUNCTION`, `METHOD`, `IMPORT` (as nodes, not edges), `CALL` (as nodes — problematic), `MARKDOWN_SECTION`.

**Edge types actually created** (`repo_graph_builder.py`):

| Edge | Created by | Quality |
|---|---|---|
| `DEFINES` | `_attach_defines` | ✅ Solid (containment) |
| `CALL` | `_resolve_calls` | ⚠️ Bare-name matches only; method calls miss; call sites collide |
| `DOCUMENTS` | `_link_docs_to_code` | ✅ Works as designed (exact-name, ADR-048) |

**Metadata captured:** `lineno`, `col_offset`, function args, class bases (as strings), import module/asname. **Not captured:** `end_lineno`, decorators, docstrings-as-fields, return types, type hints, visibility, async-ness.

## 2 · Depth gaps ranked by query value

The point of the graph is answering maintenance questions ([[../../README_VISION|vision doc]]: PR-review assistant). Rank gaps by the questions they unlock:

| Gap | Questions it blocks | Effort |
|---|---|---|
| **G-A. Reliable CALL resolution** (fix F-03/F-04, use imports per ADR-032) | "what calls X" / impact analysis — the flagship query | M |
| **G-B. `IMPORTS` module edges** (F-02) | "what breaks if I change this module's interface" | S |
| **G-C. `INHERITS` / `OVERRIDES` edges** (bases already in metadata!) | "who subclasses X", "is this method overridden", MRO-aware call resolution | S–M |
| **G-D. Docstrings + signatures as first-class fields** | Better embeddings (embed signature+docstring separately from body), better LLM context | S |
| **G-E. `READS`/`WRITES` attribute & global usage edges** | "where is this config/attribute mutated" | M–L |
| **G-F. Type-hint edges (`PARAM_TYPE`, `RETURNS`)** | "what functions accept/return a `Foo`" | M |
| **G-G. Package hierarchy (`PACKAGE` nodes, MODULE→PACKAGE)** | scoped queries, namespace browsing | S |
| **G-H. `TESTS` edges (test file ↔ tested symbol heuristics)** | "which tests cover this function" — PR-assistant gold | M |
| **G-I. Snapshot diffing (graph-over-time)** | "what changed structurally since last week" — vision doc promise | L (see [[04-Scalability-Plan#Incremental ingestion]]) |

> [!important] Depth ceiling without type inference
> Steps G-A…G-D get you a graph roughly at "ctags + reliable same-repo call graph" level — enough for the PR-assistant use case. Going beyond (precise cross-module attribute calls, duck-typed dispatch) requires real type inference (pyright/pytype integration or tree-sitter + stack-graphs). **Do not hand-roll type inference**; integrate a tool if/when queries demand it.

## 3 · Where the current resolution violates its own ADR

[[../adr/ADR-032-symbol-resolution-call-graph|ADR-032]] specifies resolution order: *local scope → file imports → global index → EXTERNAL*. The implementation (`repo_graph_builder.py:117-151`):

1. `_resolve_in_scope` — only matches recursion (ancestor whose *name equals* the call name)
2. Global flat `symbol_table.lookup(name)` — last-write-wins across the whole repo ([[01-Codebase-Audit-Findings#F-04|F-04]])
3. **Imports: never consulted.** EXTERNAL marking: never happens (unresolved calls are silently dropped, `repo_graph_builder.py:137`)

So two of ADR-032's four layers are unimplemented. The work packages below implement the ADR as written.

## 4 · Work packages (agent-ready)

> [!note] Sequencing
> If [[03-Multi-Language-Graph-Plan]] is starting within a quarter, implement WP-G2…G6 **against the IR** defined there, not against `PythonASTExtractor` directly. WP-G1 and WP-G3 are worth doing immediately regardless.

### WP-G1 — Async functions + richer metadata
**Goal:** `async def` functions/methods appear in the graph identically to sync ones; artifacts carry `end_lineno`, `decorators`, `docstring`, `is_async`.
**Files:** `ingestion_service/src/core/extractors/python_extractor.py`; text extraction in `repo_graph_builder.py::_extract_artifact_text`.
**Directions:**
- Add `visit_AsyncFunctionDef = visit_FunctionDef` (identical body; set `metadata["is_async"]=True`).
- In both class and function visitors add `metadata`: `end_lineno=node.end_lineno`, `decorators=[ast.unparse(d) for d in node.decorator_list]`, `docstring=ast.get_docstring(node)`.
- Store `end_lineno` so `_extract_artifact_text` can slice `source` lines directly instead of re-parsing (fixes [[01-Codebase-Audit-Findings#F-07|F-07]] third bullet — coordinate with [[04-Scalability-Plan#WP-S1]]).
- Fix `module_name` suffix bug ([[01-Codebase-Audit-Findings#F-05|F-05]]) while in file.
**Acceptance criteria:**
- [ ] A file with `async def handler()` inside and outside a class yields FUNCTION/METHOD artifacts with `is_async: true`
- [ ] Artifact metadata includes `end_lineno`, `decorators`, `docstring` for CLASS/FUNCTION/METHOD
- [ ] `utils/copy.py` module artifact is named `utils.copy` (regression test for rstrip bug)
- [ ] Full-file AST is parsed exactly once per file during ingestion (assert via counter in test)

### WP-G2 — Materialize `IMPORTS` edges
**Goal:** `MODULE --IMPORTS--> MODULE` edges exist for intra-repo imports; external imports become `EXTERNAL_MODULE` nodes (doc_type `external`), so "what imports X" works.
**Files:** `repo_graph_builder.py` (new `_resolve_imports(graph)` called before `_resolve_calls`); no schema change.
**Directions:**
- Build a map `dotted_module_path → module canonical_id` from all MODULE artifacts (`pkg/util.py` → `pkg.util`; handle `__init__.py` → package name).
- For each IMPORT artifact: resolve `metadata.module` (ImportFrom) or `name` (Import) against the map; handle relative imports using the importing file's package.
- Hit → edge `{from: importing module cid, to: target module cid, relation_type: "IMPORTS", metadata: {imported_name, asname}}`. Miss → create/reuse one `EXTERNAL_MODULE` node per external root (`numpy`, not `numpy.linalg`) and edge to it.
- Deterministic ordering (sort before insert) to preserve ADR-036 rebuild identity.
**Acceptance criteria:**
- [ ] `from pkg.util import helper` in `app.py` yields `app.py --IMPORTS--> pkg/util.py`
- [ ] Relative import `from . import x` resolves correctly
- [ ] `import numpy` yields an `EXTERNAL_MODULE` node named `numpy`, exactly one per repo
- [ ] `traverse_incoming_imports` in rag_orchestrator returns non-empty for an imported module (integration test)
- [ ] Two consecutive ingestions produce identical edge sets

### WP-G3 — Remove CALL nodes from identity space; keep call sites as evidence
**Goal:** call sites no longer collide or pollute `document_nodes`; CALL edges carry call-site evidence in metadata.
**Files:** `python_extractor.py`, `repo_graph_builder.py`, `codebase_ingest.py` (stop persisting CALL artifacts as nodes).
**Directions:**
- Extractor: emit call records into a separate list (`self.call_sites`) — not `self.artifacts` — with `{name, receiver, parent_id, lineno}` where `receiver` is `self`/`cls`/expr-string/None (split `node.func` instead of the current fused string).
- Builder: `_resolve_calls` consumes `call_sites`; aggregate multiple sites of the same caller→callee pair into **one** CALL edge with `metadata.call_sites=[linenos]` and `metadata.count`.
- Do **not** insert CALL rows into `document_nodes` anymore; skip embedding them (they were never embedded per ADR-039, but they are persisted today — stop that).
**Acceptance criteria:**
- [ ] Calling `foo()` twice from `bar()` produces one CALL edge with `count: 2`, both linenos in metadata
- [ ] `document_nodes` contains zero rows with `artifact_type`/`doc_type` of CALL after ingestion
- [ ] Distinct callers of `foo` each get their own edge (no last-write-wins)

### WP-G4 — Scope- and import-aware call resolution (implement ADR-032 fully)
**Goal:** `self.x()`/`cls.x()` resolve within the enclosing class; imported names resolve via IMPORTS; unresolved calls become `EXTERNAL` edges instead of disappearing.
**Files:** `repo_graph_builder.py`, `symbol_table.py`.
**Directions:**
- Replace flat `SymbolTable` with two layers: `per_file[relative_path][name] → cid` and `global_index[name] → list[cid]` (list — surface ambiguity instead of last-write-wins).
- Resolution order per ADR-032: (1) receiver `self`/`cls` → enclosing CLASS's methods; (2) bare name → same-file symbols; (3) name imported in this file (via WP-G2's import map, incl. `asname`) → target module's symbol; (4) global index **only if unambiguous** (len==1); (5) else CALL edge to `EXTERNAL_SYMBOL` node with `confidence: 0.0` — never silently drop.
- Set `confidence`: 1.0 (scoped/import-resolved), 0.5 (unique-global), 0.0 (external/unknown). Confidence lives in metadata, never in identity (ADR-031).
**Acceptance criteria:**
- [ ] `self.helper()` inside `class A` resolves to `file.py#A.helper`
- [ ] `from utils import calc; calc()` resolves cross-file to `utils.py#calc`
- [ ] Two same-named functions in different files: bare-name call from a third file yields EXTERNAL/ambiguous edge, **not** an arbitrary winner
- [ ] Unresolved call to `requests.get` produces an edge to `EXTERNAL_SYMBOL:requests.get` (queryable)
- [ ] Rebuild determinism preserved

### WP-G5 — `INHERITS` and `OVERRIDES` edges
**Goal:** class hierarchy is queryable; method overrides are explicit.
**Files:** `repo_graph_builder.py` (new `_resolve_inheritance`, after imports, before calls).
**Directions:** resolve each CLASS's `metadata.bases` strings using the same name-resolution machinery as WP-G4 (same-file → imports → global-unique → external). Emit `CLASS --INHERITS--> CLASS`. Then for each METHOD whose name exists in a resolved base class, emit `METHOD --OVERRIDES--> base METHOD`. Use inheritance in WP-G4's step (1): `self.x()` falls back to base-class methods.
**Acceptance criteria:**
- [ ] `class B(A)` cross-file yields INHERITS edge when `A` is imported
- [ ] `B.run` overriding `A.run` yields OVERRIDES edge
- [ ] `self.x()` defined only on the base resolves via inheritance
- [ ] External bases (e.g. `BaseModel`) link to `EXTERNAL_SYMBOL`

### WP-G6 — Traversal layer catches up with the deeper graph
**Goal:** query layer exploits new edges; multi-seed traversal.
**Files:** `rag_orchestrator/src/retrieval/traversal_selector.py`, `codebase_queries.py`, `src/core/service.py`.
**Directions:**
- Fix single-seed bug ([[01-Codebase-Audit-Findings#F-12|F-12]]): traverse from **all** seed canonical_ids, cap total expanded nodes (e.g. 50).
- Add strategies: `traverse_inherits` (both directions), `traverse_overrides`, `traverse_imports` (now functional), each keyed to intent keywords ("subclass", "override", "extends", "imports").
- Replace the keyword `if/elif` chain with an ordered rule table (data, not code) so adding a strategy is one line; keep it deterministic (no LLM router — deferred per ADR-045).
**Acceptance criteria:**
- [ ] Query "what subclasses Calculator" returns subclass nodes
- [ ] All seeds are expanded (test with 2 seeds mapping to disjoint subgraphs)
- [ ] Rule table unit test: each intent keyword maps to expected strategy list

## 5 · What *not* to do

- **Don't add per-language or per-edge tables.** ADR-030's two-table model handles all of the above (`relation_type` is a string).
- **Don't put resolution results into canonical IDs** (ADR-031).
- **Don't reach for a graph DB (Neo4j) yet.** At current scale the in-memory adjacency graph is fine; revisit only after [[04-Scalability-Plan]] measurements say otherwise.
- **Don't hand-roll type inference** — integrate pyright/stack-graphs later if queries demand it.
