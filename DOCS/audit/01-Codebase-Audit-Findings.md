---
title: "Codebase Audit Findings"
date: 2026-07-09
type: audit-findings
status: complete
severity-scale: P0 (corrupts data / blocks scale) → P3 (hygiene)
tags:
  - audit
  - bugs
  - tech-debt
  - rag-foundry
related:
  - "[[00-Audit-Overview]]"
  - "[[02-Graph-Depth-Analysis]]"
  - "[[04-Scalability-Plan]]"
---

# 🐛 Codebase Audit Findings

> [!abstract] Scope
> Concrete defects and structural debt found by reading the source. Each finding has a location, an impact statement, and a fix direction. Work-package IDs (`WP-xx`) cross-reference the plan documents where the fix is specified in full.

## P0 — Graph correctness

### F-01 · Async functions are invisible to the graph
**Where:** `ingestion_service/src/core/extractors/python_extractor.py:94`
The extractor implements `visit_FunctionDef` but **not `visit_AsyncFunctionDef`**. Every `async def` — which includes most FastAPI handlers in any modern repo, including this project's own — produces **no FUNCTION/METHOD artifact at all**. Calls inside async bodies still emit CALL artifacts, but their `parent_id` points at the enclosing class/module, mis-attributing the call.
**Fix:** add `visit_AsyncFunctionDef = visit_FunctionDef` (plus an `is_async` metadata flag). → [[02-Graph-Depth-Analysis#WP-G1]]

### F-02 · `IMPORT` relationships are never created
**Where:** `repo_graph_builder.py` — `_attach_defines` (line 86) handles only `DEFINES`; `_resolve_calls` (line 117) only `CALL`; `_link_docs_to_code` (line 158) only `DOCUMENTS`. IMPORT artifacts exist as *nodes* (`python_extractor.py:123-153`) but no builder step converts them into `MODULE→MODULE` edges.
**Impact:** `rag_orchestrator/src/retrieval/codebase_queries.py:112` (`traverse_incoming_imports`) traverses `relation_type="IMPORT"` edges that cannot exist. Any "what imports X" query **silently returns nothing** — the worst failure mode: plausible, wrong.
**Fix:** add `_resolve_imports()` builder step creating `IMPORTS` edges from importing MODULE to imported MODULE (resolve `module` metadata against known repo paths; mark unresolvable as external). → [[02-Graph-Depth-Analysis#WP-G2]]

### F-03 · CALL canonical IDs collide and overwrite each other
**Where:** `python_extractor.py:166` — `"id": f"{relative_path}#call:{func_name}"` — and `repo_graph.py:44` — `self.entities[canonical_id] = entity`.
Two calls to `foo()` in the same file produce the **same canonical ID**; the second overwrites the first in `RepoGraph.entities`. Call *sites* are lost; only "this file calls foo at least once" survives, with the surviving `parent_id` being whichever call was visited last — so caller attribution is arbitrary.
**Fix:** CALL is not an identity-bearing artifact (per ADR-031 spirit); either key call sites by `path#call:name@lineno` **internally only** (never persisted as canonical identity) or stop storing CALLs as entities and keep them in a side list consumed by `_resolve_calls`. Recommended: the side-list approach — CALL nodes also pollute `document_nodes` today. → [[02-Graph-Depth-Analysis#WP-G3]]

### F-04 · Method calls essentially never resolve
**Where:** `python_extractor.py:157-158` records attribute calls as `"self.add"` / `"obj.method"`; `symbol_table.py:48` keys symbols by **bare name** (`add`). `repo_graph_builder.py:135` does `symbol_table.lookup(name)` with the dotted string → **miss**. `_resolve_in_scope` (line 239) only matches when an *ancestor scope's name equals the call name* — i.e. recursion.
**Impact:** the CALL graph contains only direct-name, same-file-or-global-unique calls. For idiomatic OO Python the call graph is close to empty. Combined with F-03, "what calls X" answers are unreliable.
**Fix:** strip the receiver for `self.x`/`cls.x` and resolve within the enclosing class first (then MRO once INHERITS lands); consult the file's IMPORT artifacts (per ADR-032's stated order — imports are currently **skipped entirely**). → [[02-Graph-Depth-Analysis#WP-G4]]

### F-05 · `rstrip(".py")` corrupts module names
**Where:** `python_extractor.py:33` — `relative_path.replace("/", ".").rstrip(".py")`.
`str.rstrip` strips a *character set*, not a suffix: `"utils/copy.py"` → `"utils.co"`, `"happy.py"` → `"ha"`. Module display names are silently wrong for any path ending in `p`, `y`, or `.`.
**Fix:** `relative_path[:-3].replace("/", ".")` guarded by `endswith(".py")`, or `PurePosixPath(...).with_suffix("")`.

### F-06 · Non-atomic delete-then-insert "upsert" can destroy a repo's graph
**Where:** `codebase_persistence.py:87-97` — the delete runs in its own transaction (`with self._session.begin()` commits on exit), inserts commit later (line 139), and relationship writes commit later still (line 221).
**Impact:** any failure after the delete (embedding error, crash, OOM) leaves the repo with **no graph** and marks the ingestion failed — the previous good graph is already gone. Violates the rebuild-safety intent of ADR-030/036.
**Fix:** single transaction for delete + node insert + relationship insert; or build into a staging `ingestion_id`-scoped set and swap. → [[04-Scalability-Plan#WP-S3]]

## P0 — Scalability (algorithmic)

### F-07 · O(N²) and worse in the graph build hot path
**Where:** `repo_graph_builder.py`
- `_canonical_from_id` (line 256): **linear scan of all entities**, called per DEFINES/CALL candidate → O(N²).
- `_resolve_in_scope` (line 239): linear scan **per ancestor hop, per call** → O(calls × entities × depth).
- `_extract_artifact_text` (line 281): **re-parses the whole file's AST for every artifact** in it → O(artifacts × file size); a 500-symbol file is parsed 500 times.
**Impact:** ingestion time grows quadratically; a mid-size repo (50k artifacts) is effectively un-ingestable.
**Fix:** maintain an `id → entity` dict in `RepoGraph` (it already keys by `canonical_id`; add a second index by extractor `id`); parse each file **once** and slice text by `lineno/end_lineno` during extraction. → [[04-Scalability-Plan#WP-S1]]

### F-08 · Per-artifact embedding loop: 1 DB query + ≥2 HTTP calls per node, sequential
**Where:** `codebase_ingest.py:135-162` — for each node: `get_node_by_canonical_id` (SQL), `pipeline._embed` (HTTP to Ollama), `pipeline._persist` (HTTP to vector_store).
**Impact:** 10k artifacts ≈ 10k SQL round-trips + 20k HTTP round-trips, serial. Hours of wall-clock.
**Fix:** batch — one query to map canonical_id→document_id for all nodes; embed in Ollama batches; bulk persist. → [[04-Scalability-Plan#WP-S2]]

### F-09 · Relationship persistence: 3 queries per edge
**Where:** `codebase_persistence.py:162-219` — per relationship: two node lookups + one existence check, then per-row insert.
**Fix:** preload `canonical_id→document_id` map once; bulk `INSERT ... ON CONFLICT`. The existence check is pointless right now anyway — nodes were just deleted and recreated, so no relationship can pre-exist. → [[04-Scalability-Plan#WP-S3]]

### F-10 · No ANN index on vector columns
**Where:** `migrations/versions/20251229_add_vectors_table.py`, `20260201_add_vector_chunks_table.py` — no `USING hnsw`/`ivfflat` index exists anywhere in `migrations/`.
**Impact:** every `similarity_search` (`pgvector_store.py:132-163`) is a **sequential scan** with distance computed for every row.
**Fix:** HNSW index migration + tune `hnsw.ef_search`. → [[04-Scalability-Plan#WP-S4]]

### F-11 · Fire-and-forget `threading.Thread` ingestion
**Where:** `codebase_ingest.py:200-209`.
**Impact:** ingestion dies silently on container restart/deploy; no retry, no backpressure, no concurrency control (two simultaneous ingests of the same repo will interleave delete/insert and corrupt each other — no lock exists). Status rows are left `running` forever.
**Fix:** job queue (see [[04-Scalability-Plan#WP-S5]]); short-term, at least a per-repo advisory lock and startup recovery for orphaned `running` rows.

## P1 — Design / correctness

### F-12 · Graph traversal starts from ONE arbitrary seed
**Where:** `rag_orchestrator/src/core/service.py:172` — `start_cid = max(seed_canonical_ids, key=len)` — the *longest string* among seeds is picked as the sole traversal root; all other seeds are never expanded.
**Fix:** traverse from **all** seeds (bounded), merge results. Trivial loop; large quality win.

### F-13 · ADR-038 factory does not exist
`docs claim `pipeline_factory.py::build_pipeline()` owns construction; reality: `codebase_ingest.py:40` has an inline `_build_pipeline` marked "TECH DEBT", and `NoOpValidator` (line 35) silently disables validation for repo ingestion. Create the factory or amend the ADR.

### F-14 · Embedding-dimension inconsistency
`shared/models/document_node.py:100` declares `Vector(768)` for `summary_embedding` while the system-wide embedder is 1024-d (`mxbai-embed-large`, migration `20260301_update_vector_dimensions_1024.py`). Any future write to `summary_embedding` with the current embedder fails. Also `shared/embedders/` and `ingestion_service/src/core/embedders/` are **duplicated implementations** that can drift (as are `shared/chunkers/` vs `src/core/chunkers/`).

### F-15 · Dual-write to `vectors` + `vector_chunks`
`pgvector_store.py:32-67` writes every embedding twice ("MS6 dual-write test" was never retired). Doubles storage and write latency; `vectors` is read nowhere in the query path. Retire it.

### F-16 · `_walk_repo` has no ignore semantics beyond dot-dirs
`repo_graph_builder.py:264-271` skips only dot-directories. `node_modules/`, `venv/`, `build/`, `dist/`, vendored code — all ingested. On real repos this multiplies graph size by 10–100× with junk. Also `except Exception: continue` (line 43) silently drops files that fail to parse — no count, no report.

### F-17 · Broken CI
`.github/workflows/ci/yml` — the path makes it a file named `yml` inside directory `ci`; GitHub Actions will never run it. Its content also references a nonexistent `requirements.txt` and Python 3.9 (project requires ≥3.12). Rewrite as `.github/workflows/ci.yml` running ruff + pyright + unit tests per service.

### F-18 · No authn/authz on any endpoint, secrets in compose
Every service port is bound to the host with no auth; `docker-compose.yml` hard-codes `ingestion_pass`. Acceptable on a laptop; disqualifying for enterprise. → [[05-Enterprise-Platform-Plan#Security baseline]]

## P2/P3 — Hygiene (abbreviated)

| # | Finding | Where |
|---|---|---|
| F-19 | `logger.setLevel(DEBUG)` + `logging.basicConfig` at import time in libraries | `repo_graph_builder.py:15`, `pgvector_store.py:12`, `service.py:28` |
| F-20 | `doc_type` defaults to `"python source"` for **all** artifacts incl. Markdown | `repo_graph_builder.py:51` |
| F-21 | Bare `except Exception: continue` swallows parse failures with no metric | `repo_graph_builder.py:33,43` |
| F-22 | New psycopg connection per operation (no pool) | `pgvector_store.py:48,166,194,212` |
| F-23 | `httpx.AsyncClient` created per request; 200s timeouts hide latency bugs | `service.py:96,138,183,288` |
| F-24 | Dead/commented code, stray `hello.py`, duplicated status docs | repo root |
| F-25 | `graph.py` full-graph endpoint returns entire node+edge set unpaginated | `ingestion_service/src/api/v1/graph.py:96` |

## Suggested fix order

1. **F-05, F-01, F-12** — one-line to few-line fixes, immediate quality gains.
2. **F-07 + F-08 + F-09** as one refactor pass over build/persist ([[04-Scalability-Plan#WP-S1]]–[[04-Scalability-Plan#WP-S3]]).
3. **F-03, F-04, F-02** — call/import resolution rework ([[02-Graph-Depth-Analysis]] WP-G2–G4) — do this **inside the IR refactor** of [[03-Multi-Language-Graph-Plan]] if multi-language is imminent.
4. **F-10, F-11** — infrastructure ([[04-Scalability-Plan]]).
5. **F-17, F-18** — platform ([[05-Enterprise-Platform-Plan]]).
