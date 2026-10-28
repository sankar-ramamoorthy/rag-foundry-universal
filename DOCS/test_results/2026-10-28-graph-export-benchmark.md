---
title: "Graph export benchmark: latency, memory and responsiveness under concurrent exports"
date: 2026-10-28
type: evaluation-report
status: complete-local-synthetic
tags: [benchmark, ingestion-service, graph-export, concurrency, memory]
related:
  - "[Issue #270: E1 control-replay timeout diagnosis](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/270)"
  - "[Issue #271 / PR #272: run the export off the event loop](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/272)"
  - "[Issue #273: this benchmark](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/273)"
  - "[E1 baseline results](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)"
  - "[Project status](/DOCS/status.md)"
---

# Graph export benchmark

Measurement infrastructure and first results for
`GET /v1/graph/repos/{repo_id}` (the full-graph export the orchestrator loads on
a cold cache). It exists to answer one capacity question raised by PR #272:
that PR moves the export off the event loop, so exports that the blocked loop
used to serialize now overlap. How much memory and latency does that cost?

**Scope.** Local, synthetic, one machine. It says nothing about the 120 s+
E1 control-replay timeout, which remains unresolved in #270.

## How to run

Opt-in; not collected by pytest, not run in CI. Needs a migrated **test**
database and the root virtualenv.

```bash
docker compose -f docker-compose.test.yml up -d postgres
DATABASE_URL=postgresql://USER:PASS@localhost:5433/ingestion_test alembic upgrade head

export BENCH_DATABASE_URL=postgresql://USER:PASS@localhost:5433/ingestion_test
python scripts/graph_export_benchmark.py --nodes 15000 --output report.json

# another checkout (e.g. a git worktree of a branch), same fixture, same flags:
python scripts/graph_export_benchmark.py --nodes 15000 --skip-load \
    --repo-root ../other-checkout --expect-hash <hash from the first run>
```

For each concurrency level (default 1, 2, 4) it starts the real
`ingestion_service` app in one uvicorn process, fires that many simultaneous
exports, probes `/version` every 50 ms, and records per-request latency, wall
time, the slowest probe, peak memory of the server process tree, and a
canonical hash of every response. A level is **skipped** when projected memory
(idle + level x measured single-export growth x 1.25) exceeds available RAM.
The database name must contain `test` or `bench` (or pass `--force-db`); the
script writes and deletes rows only for one synthetic repo id. No dataset is
committed. The response hash depends on `--nodes` and `--edges-per-node`, not
on text size.

## Setup of the recorded runs

- Windows 11, 7.8 GB RAM with roughly 0.4-0.9 GB free during the runs, local
  Docker Postgres 15 (pgvector), single uvicorn process, Python 3.12.
- Synthetic graphs: 5,000 nodes (10.1 MB text, 15,000 relationships) and 15,000
  nodes (29.9 MB text, 45,000 relationships); 3 edges per node, ~2 KB mean node
  text (random hex, which compresses differently from source code).
- **Before:** `main` at `a476b39` (handler is `async def`). **After:** branch
  `fix/271-graph-export-off-event-loop` at `07b586e` (PR #272, not merged),
  run from a git worktree with identical flags. One run per cell.
- Raw reports: [`graph-export-benchmark/`](/DOCS/test_results/graph-export-benchmark/).

## Results

Response hashes were identical before and after at both sizes (`4a8a3c934a508e2d`
at 5,000 nodes, `59a364e1cb0d6f02` at 15,000) and across every concurrent request.

### 5,000 nodes

| Concurrent exports | Handler | Per-request latency (min / median / max) | Wall | Slowest `/version` | Peak memory (idle 156 MB) |
| --- | --- | --- | --- | --- | --- |
| 1 | before | 1.78 s | 1.94 s | 1.25 s | 214 MB |
| 1 | after | 1.78 s | 1.90 s | 0.31 s | 214 MB |
| 2 | before | 2.04 / 2.75 / 3.46 s | 3.61 s | 2.69 s | 216 MB |
| 2 | after | 3.13 / 3.22 / 3.32 s | 3.47 s | 0.64 s | 275 MB |
| 4 | before | 2.20 / 4.15 / 6.14 s | 6.28 s | 5.24 s | 218 MB |
| 4 | after | 4.24 / 4.38 / 4.54 s | 4.63 s | 1.02 s | 393 MB |

### 15,000 nodes

| Concurrent exports | Handler | Per-request latency (min / median / max) | Wall | Slowest `/version` | Peak memory (idle 156 MB) |
| --- | --- | --- | --- | --- | --- |
| 1 | before | 5.56 s | 5.88 s | 4.67 s | 323 MB |
| 1 | after | 5.05 s | 5.52 s | 0.44 s | 325 MB |
| 2 | before | 5.07 / 6.79 / 8.51 s | 8.85 s | 7.62 s | 329 MB |
| 2 | after | 8.71 / 8.98 / 9.25 s | 9.65 s | 1.41 s | 498 MB |
| 4 | both | skipped by the memory guard (projected ~1,000 MB, ~600 MB available) | | | |

## Findings

Measured:

1. **Responsiveness.** Before the fix the slowest `/version` probe tracks the
   total serialized export time and grows with concurrency (5,000 nodes: 1.25,
   2.69, 5.24 s for 1, 2, 4 exports). After it, the probe waits 0.31, 0.64,
   1.02 s: about five times lower at four exports, but it still grows with
   concurrency (CPU contention between worker threads), so it is not flat.
2. **Memory.** Before the fix, peak memory is flat in concurrency because
   exports are serialized. After it, memory grows with every in-flight export:
   about 58-60 MB per export at 5,000 nodes (214, 275, 393 MB for 1, 2, 4) and
   about 170 MB at 15,000 (325 MB, 498 MB for 1, 2). That is roughly 11-12 KB
   per node per in-flight export, linear in both node count and concurrency over
   what was measured.
3. **Latency and throughput are mixed.** Overlapping exports each take longer
   than a lone export (5,000 nodes, four at once: 4.2-4.5 s each versus 1.78 s),
   and all finish together. Wall time was lower at four exports (4.63 s versus
   6.28 s) and slightly higher at two exports on the 15,000-node graph (9.65 s
   versus 8.85 s). The change is a responsiveness fix, not a throughput fix.
4. **Equivalence.** The response is unchanged by the handler change.

Inferred, not measured here:

- At the E1 LightRAG scale (41,635 nodes) the same per-node rate suggests
  roughly 450-500 MB per in-flight export, so four simultaneous cold exports
  would approach 2 GB. PR #272's earlier single measurement (983 MB peak for two
  exports at 41,635 nodes) is consistent with this order but this benchmark did
  not run that size or four-way at that size.
- Whether a concurrency limit is needed depends on how often several cold-cache
  exports can occur together in a real deployment and on that host's memory
  limit; neither is known from this data. The compose files set no memory limits.

## Limitations

One run per cell (no repeat variance). Windows working-set memory of the
server's process tree, not a Linux cgroup measurement. Local database, no
network hop. Synthetic data. The machine was under memory pressure while it
ran, which may have affected timings. The four-way level was only possible at
5,000 nodes. "After" ran the unmerged branch. Nothing here is a production
measurement or a deployment recommendation.
