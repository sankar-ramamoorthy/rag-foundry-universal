---
title: "Scalability Plan — Massive Codebases"
date: 2026-07-09
type: audit-plan
status: proposed
target: "monorepos of 1M+ LOC / 100k+ artifacts, concurrent ingestion & query"
tags:
  - audit
  - scalability
  - performance
  - rag-foundry
related:
  - "[[01-Codebase-Audit-Findings]]"
  - "[[05-Enterprise-Platform-Plan]]"
---

# 🚀 Scalability Plan — Massive Codebases

> [!tip] Status (2026-08-27) — Phase A (WP-S1–S4) is done
> `WP-S1`–`WP-S4` below shipped in Phase 1 (see `DOCS/test_results/Phase-1-Exit-Report.md` and `DOCS/audit/00-Audit-Overview.md`'s current-status overlay). The rest of this document (Phase B/C: `WP-S5`–`WP-S8`) is unstarted except where noted. `WP-S8`'s reranker sub-task specifically has a recorded **NO-GO** verdict as of the WP-Q0 RAG-quality baseline (issue #49, 2026-08-27) — see the annotation on that work package below before picking it up.

> [!abstract] Thesis
> Nothing about the architecture *prevents* scale — but four implementation layers currently cap it at toy-repo size: **(1)** O(N²) graph build, **(2)** per-artifact serial persistence/embedding, **(3)** un-indexed vector search, **(4)** in-process fire-and-forget ingestion with whole-graph-in-RAM query. Fix in that order; measure between steps.

## 0 · Where it breaks today, quantified

| Bottleneck | Location | Cost at 100k artifacts |
|---|---|---|
| `_canonical_from_id` linear scans | `repo_graph_builder.py:256` | ~10¹⁰ dict scans (build never finishes) |
| Per-artifact full-file re-parse | `repo_graph_builder.py:281` | file parsed once **per symbol** in it |
| Per-node SQL lookup + HTTP embed + HTTP persist, serial | `codebase_ingest.py:135-162` | ≥300k round-trips |
| 3 queries per relationship | `codebase_persistence.py:162` | ~1M queries |
| No ANN index | `migrations/` (absent) | every query scans every chunk row |
| Whole repo graph in orchestrator RAM, no eviction | `codebase_utils.py:15,56` | multi-GB resident per large repo; unbounded dict across repos |
| `threading.Thread` ingestion | `codebase_ingest.py:200` | dies on deploy; no concurrency control |
| Full-graph API unpaginated | `api/v1/graph.py:96` | 100k-node JSON body per cache load |

## 1 · Phase A — Algorithmic fixes (no new infrastructure)

### WP-S1 — Make graph build O(N) ✅ Done (Phase 1)
**Goal:** ingestion CPU time linear in repo size.
**Files:** `repo_graph.py`, `repo_graph_builder.py`, `python_extractor.py`.
**Directions:**
- Add `RepoGraph.by_extractor_id: dict[str, dict]` maintained in `add_entity`; replace both `_canonical_from_id` linear scans (`:256`) and the `_resolve_in_scope` entity scan (`:239`) with dict lookups.
- Extract artifact text **during extraction** using `lineno/end_lineno` line slicing of the already-loaded source (coordinate with [[02-Graph-Depth-Analysis#WP-G1|WP-G1]]); delete `_extract_artifact_text`'s re-parse.
- `_walk_repo`: respect `.gitignore` (use `pathspec` lib) and a default deny-list (`node_modules`, `venv`, `.venv`, `target`, `build`, `dist`, `vendor`); count+log skipped/failed files instead of bare `except: continue` (fixes [[01-Codebase-Audit-Findings#F-16|F-16]], [[01-Codebase-Audit-Findings#F-21|F-21]]).
**Acceptance criteria:**
- [ ] Synthetic benchmark repo (generate 2k files / 50k symbols in a test fixture script): graph build completes < 60 s on laptop hardware
- [ ] Profiling shows zero calls to a full-entity scan helper (helpers deleted)
- [ ] `node_modules` contents produce zero artifacts
- [ ] Ingestion summary logs: files parsed / skipped / failed counts

### WP-S2 — Batch embedding + persistence ✅ Done (Phase 1)
**Goal:** ingestion I/O round-trips proportional to *batches*, not artifacts.
**Files:** `codebase_ingest.py`, `pipeline.py`, `http_vectorstore.py`, `shared/embedders/ollama.py`, `vector_store_service/src/api/v1/vectors.py`.
**Directions:**
- One query to fetch all `(canonical_id → document_id)` for the repo after `upsert_nodes` (kill the per-node `get_node_by_canonical_id`).
- Chunk all nodes first; embed via the embedder's existing batch parameter (`OLLAMA_BATCH_SIZE` config already exists — it's plumbed but the loop defeats it); persist via `/v1/vectors/batch` in batches of ~500 records.
- Stop the dual-write to `vectors` ([[01-Codebase-Audit-Findings#F-15|F-15]]): write `vector_chunks` only; migration to drop `vectors` after a deprecation window.
- Add connection pooling in `pgvector_store.py` (`psycopg_pool.ConnectionPool`) — one pool per process, not one connection per call ([[01-Codebase-Audit-Findings#F-22|F-22]]).
**Acceptance criteria:**
- [ ] Ingesting the benchmark repo issues ≤ (N/500 + constant) vector-store HTTP calls (assert via request counter in a test double)
- [ ] Zero rows written to `ingestion_service.vectors` on new ingests
- [ ] End-to-end ingest of benchmark repo ≥10× faster than baseline (record both numbers in the PR description)

### WP-S3 — Transactional, bulk graph persistence ✅ Done (Phase 1)
**Goal:** rebuild is atomic (all-or-nothing) and fast.
**Files:** `codebase_persistence.py`.
**Directions:**
- Single transaction wrapping delete + `bulk_insert_mappings` (or `INSERT … VALUES` batches of ~1k) for nodes **and** relationships; commit once (fixes [[01-Codebase-Audit-Findings#F-06|F-06]]).
- Relationships: build `canonical_id → document_id` map in memory (you just inserted the nodes — you have the IDs); drop the 3-queries-per-edge pattern; `ON CONFLICT DO NOTHING` on the relationship unique key.
- Take a Postgres advisory lock on `repo_id` for the duration (prevents concurrent-ingest corruption, [[01-Codebase-Audit-Findings#F-11|F-11]]).
**Acceptance criteria:**
- [ ] Kill -9 the service mid-ingest → previous graph rows still intact (test with docker-compose test stack)
- [ ] Second concurrent ingest of same repo blocks or fails fast with clear status, never interleaves
- [ ] 50k nodes + 100k edges persist < 30 s

### WP-S4 — ANN index + query-path hygiene ✅ Done (Phase 1; typed filter columns landed later as WP-S4B)
**Goal:** vector search latency independent of corpus size.
**Files:** new Alembic migration; `pgvector_store.py`.
**Directions:**
- Migration: `CREATE INDEX CONCURRENTLY ix_vector_chunks_hnsw ON ingestion_service.vector_chunks USING hnsw (vector vector_cosine_ops)` (+ analyze). Note: filtered queries (`source_metadata->>…`) partially bypass HNSW — add btree expression indexes on `(source_metadata->>'doc_type')` and `(source_metadata->>'repo_id')`, and put `repo_id`/`doc_type`/`language` into **real columns** on `vector_chunks` in a follow-up migration (JSONB-only filtering won't scale).
- `similarity_search`: set `SET LOCAL hnsw.ef_search = 100` per query; expose `k` and filter as today.
**Acceptance criteria:**
- [x] `EXPLAIN ANALYZE` on a filtered search shows index scan, not seq scan
- [ ] p95 search latency < 100 ms at 1M chunk rows — **not yet measured at this scale**. The HNSW index and typed filter columns are live and p95 ≈ 62 ms was measured at Phase 1 benchmark scale (56k artifacts, `DOCS/test_results/Phase-1-Exit-Report.md`); the 1M-row target itself remains an unverified projection, not a measured result (see README.md's softened wording).

## 2 · Phase B — Ingestion as real jobs

### WP-S5 — Job queue for ingestion
**Goal:** ingestion survives restarts, retries transient failures, scales horizontally.
**Directions:**
- Introduce a worker: **arq or Celery over Redis** (arq recommended — async, small, fits FastAPI). New container `ingestion_worker` sharing the `ingestion_service` image (`command: arq src.worker.WorkerSettings`).
- `POST /v1/ingest-repo` enqueues and returns `202` (API contract unchanged). Worker executes today's `_background_ingest_repo` body, refactored into `src/core/ingest_job.py`.
- Progress: extend `StatusManager` with stage + counts (`cloning / parsing / persisting / embedding`, `n_of_m`); expose in the existing status endpoint.
- Startup recovery: mark orphaned `running` rows as `failed:orphaned` on worker boot.
**Acceptance criteria:**
- [ ] `docker compose restart ingestion_worker` mid-ingest → job retries and completes; no `running` orphans
- [ ] Two repos ingest concurrently on two workers; same-repo concurrency serialized via WP-S3 lock
- [ ] Status endpoint reports stage + progress counts

### WP-S6 — Incremental ingestion (the massive-repo unlock)
**Goal:** nightly re-ingest of a 1M-LOC monorepo touches only changed files.
**Directions:**
- Store per-file content hash (`file_hashes` table or `metadata` on MODULE nodes) + last ingested commit SHA per repo.
- On re-ingest: `git diff --name-status <last_sha> HEAD` → changed/deleted file set. Unchanged files: skip parse entirely. Changed: delete that file's nodes/edges/chunks (`relative_path`-scoped delete) and re-extract. Deleted: remove.
- **Cross-file edges** (calls/imports into changed files): keep a reverse index (`document_relationships` already is one — query edges whose target is in changed set) and re-run *resolution only* for affected source files. Re-embed only changed artifacts.
- Preserve ADR-036 semantics: an incremental result must equal a from-scratch rebuild — enforce with a periodic (weekly) full rebuild + diff assertion job, and a test comparing incremental vs full on a fixture repo after a scripted edit.
- Snapshot lineage: record `(repo_id, commit_sha, ingested_at)` history — this is also the foundation for the vision doc's "what changed since last week" queries.
**Acceptance criteria:**
- [ ] Editing 1 file in a 2k-file fixture repo re-parses exactly 1 file (+ affected resolvers) and re-embeds only its artifacts
- [ ] Incremental-vs-full graph diff is empty on the fixture after edits
- [ ] Re-ingest time for 1-file change < 30 s regardless of repo size

## 3 · Phase C — Query path at scale

### WP-S7 — Bounded graph service instead of whole-graph-in-RAM
**Problem:** `get_cached_graph` (`codebase_utils.py:56`) loads **every node and edge** of a repo into orchestrator memory via an unpaginated API ([[01-Codebase-Audit-Findings#F-25|F-25]]), cached forever, per process.
**Directions (two steps):**
1. **Near-term:** replace full-graph load with **neighborhood queries** — new `ingestion_service` endpoint `POST /v1/graph/repos/{repo_id}/traverse {start_ids[], relation_types[], direction, max_depth, limit}` executing a recursive CTE over `document_relationships`. Orchestrator's `execute_traversals` calls it instead of local BFS. Delete the in-memory cache (or keep an LRU of *small* repos only, capped by node count).
2. **Later, if measurements demand:** dedicated graph store (Neo4j/Memgraph) or Postgres `pg_graph`-style adjacency with covering indexes. **Do not adopt a graph DB before CTE performance is measured** — depth ≤3 typed traversal on indexed edges is fast in Postgres at this scale.
**Acceptance criteria:**
- [ ] Orchestrator RSS stays < 500 MB while querying a 100k-node repo
- [ ] Traverse endpoint p95 < 200 ms for depth-2 on benchmark graph (indexes on `(from_document_id, relation_type)` / `(to_document_id, relation_type)`)
- [ ] `/v1/graph/repos/{id}` full-graph endpoint paginates (`limit/offset`) — breaking change coordinated with UI

### WP-S8 — Retrieval quality/perf at scale
> [!warning] Reranker sub-task: NO-GO, deferred (2026-08-27)
> The WP-Q0 RAG-quality baseline (issue #49, `DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`) ran the reranker decision gate below against a 10-question corpus and returned an explicit **NO-GO**: 0/10 failures classified `rank-8-to-20` (the only pattern a reranker addresses); the one failure was already top-3 and was independently confirmed via a clean-context test to be a prompting/context-assembly problem. **Do not pick up the reranker bullet below without a new evaluation showing rank-8–20 failures.**

> [!tip] Dedup bullet: done (2026-08-29)
> [Issue #65](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/65) (near-duplicate chunk crowding from module/sole-child artifact embedding, measured at a mean of 4 duplicate candidate slots per ~17–20-item window in WP-Q0) is fixed in [#73](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/73) — a retrieval-time dedup pass in `hybrid_retrieve()`, not an ingestion-time change (see [[00-Audit-Overview]]'s 2026-08-29 status for why). See [[09-Retrieval-Technique-Decision-Gates]]'s "Context deduplication" row.

**Directions:**
- Parallelize the per-doc `search-by-doc` loop (`service.py:183-200`) with `asyncio.gather` + semaphore(10).
- Real tokenizer for the context budget (tiktoken or provider count) instead of `len(text.split())` (`service.py:271`).
- Add a reranker stage (flag-gated): cross-encoder over top-50 → top-10 (runs in `rag_orchestrator`; model via [[06-LLM-Provider-LiteLLM-Plan|LiteLLM]] or local `bge-reranker`). **Gate:** only build this after [[08-RAG-Quality-Evaluation-Methodology]] shows correct chunks landing at rank 8–20, not absent or already top-3. **As of 2026-08-27 this gate has been checked once and failed (NO-GO) — see callout above.**
- ~~Cap and dedupe expanded context (today `max_total_chunks=9999`, `service.py:262`).~~ Dedup done (see callout above); the cap itself was already resolved separately (issue #30 Part 3 — `MAX_TOTAL_CHUNKS` default is 50, not 9999, per `rag_orchestrator/src/core/config.py`).
**Acceptance criteria:**
- [ ] Expanded-doc fetch is concurrent (test: 20 docs fetched in ~1 RTT, not 20)
- [ ] Context never exceeds configured token budget measured by the real tokenizer
- [ ] Reranker flag on/off compared on a small eval set; results recorded in `DOCS/test_results/` — **superseded for now**: the eval already ran and the recorded result is NO-GO (`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`); re-open only alongside new evidence
- [x] Dedup pass resolves issue #65: fixed in [#73](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/73) — `dedupe_near_identical_chunks()` in `codebase_utils.py`, wired into `hybrid_retrieve()`; verified live that near-identical module/sole-child chunk pairs collapse to a single seed candidate before reaching the top-k context

## 4 · Capacity targets after all phases

| Metric | Today (measured shape) | Target |
|---|---|---|
| Ingest 1M LOC monorepo (cold) | fails / hours | < 30 min (parallel workers) |
| Re-ingest after small PR | full rebuild | < 30 s |
| Vector search p95 @ 1M chunks | seconds (seq scan) | < 100 ms |
| Graph traversal p95 depth-2 | whole-graph load first | < 200 ms |
| Orchestrator memory | O(repo) unbounded | O(1) bounded |
| Ingestion survival across deploys | ❌ | ✅ queued + resumable |

> [!tip] Measure-first discipline
> Land WP-S1 with the synthetic benchmark repo **in the same PR**, and record before/after numbers in `DOCS/test_results/` for every WP in this plan. Scaling claims without the benchmark harness are guesses.
