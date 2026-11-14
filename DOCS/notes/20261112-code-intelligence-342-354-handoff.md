---
title: "Retrieval-side handoff: #342 discovery diagnostics and #354 import resolution"
date: 2026-11-12
type: working-note
status: current
tags: [handoff, code-intelligence, retrieval, graph, import-resolution, issue-342, issue-354]
related:
  - "[Issue #342](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/342)"
  - "[Issue #354](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/354)"
  - "[#342 A/B/C discovery diagnostic](/DOCS/test_results/2026-11-12-342-abc-discovery-diagnostic.md)"
  - "[#354 import-resolution validation](/DOCS/test_results/2026-11-12-354-import-resolution-validation.md)"
  - "[ADR-032 amendment 2026-11-12](/DOCS/adr/ADR-032-symbol-resolution-call-graph.md)"
  - "[Inference-side handoff](/DOCS/notes/20261112-inference-baseline-and-provider-capture-handoff.md)"
  - "[Agent Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
---

# Retrieval-side handoff (2026-11-12)

This note is written so that anyone resuming the work (a person, Claude Code or
Codex) can do so from the repository alone. Roadmap: Phase 6. It complements the
[inference-side handoff](/DOCS/notes/20261112-inference-baseline-and-provider-capture-handoff.md).
#194 (budget) and #345 (inference) stay separate from this track.

## Where things stand

**The question.** The #342 failure question is the Step 0 question:

> Trace the execution path from POST /v1/rag through the orchestrator to vector
> retrieval.

It is asked against self-repo generation `e423d1bb` (commit `8e06335`).

| Step | Outcome | Record |
|---|---|---|
| #351 | The Step 0 candidate pool is all Markdown. Implementation ranks 676 to beyond 2,000: a ranking failure, not a budget failure. | [round 3](/DOCS/test_results/2026-11-12-345-round3-repro-and-retrieval.md) |
| #352 | Mechanism diagnostics, with hand-picked lexical terms, plus strategy notes | [diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md) |
| #353 | A/B/C discovery: vector and identifier search find 0 of 11 functions. The route anchor (`POST /v1/rag` → `HANDLED_BY` → `rag_endpoint`) works, but the trace stops at hop 2. | [A/B/C report](/DOCS/test_results/2026-11-12-342-abc-discovery-diagnostic.md) |
| #355 | Source full-text search with terms derived from the question: the best text result is 2 of 11 in the top 20 (path-role filter plus fusion). This applies only to the broad OR formulation tested. | same report, "B2" section |
| #356 (part of #354) | **Merged 2026-11-12 (`c0feae2`).** Service-local `src.` imports are now resolved at ingestion (ADR-032 amendment). Validated in memory only; **no database re-ingested**. Criterion 4 was verified on 2026-11-13 after the owner's re-ingestion. | [validation](/DOCS/test_results/2026-11-12-354-import-resolution-validation.md) |
| Rerun (2026-11-13) | Generation `8cbedbb9` (commit `9f039c4`): H2 is exact, and the trace reaches 7 of 13 chain nodes (1 before). The live graph matches the in-memory fix-on build exactly. | [trace rerun](/DOCS/test_results/2026-11-13-342-post-354-trace-rerun.md) |

**Root cause fixed by #354.** Services import from their own root
(`from src.core.service import run_rag`), but module names were dotted from the
repository root. At `8e06335` this left 1,245 CALL edges as
`EXTERNAL_SYMBOL:src.…` placeholders. With the fix, 18 remain, and all 18 are
correct to leave unresolved.

**Still not graph-connected, even with #354:**
- functions passed to `asyncio.to_thread` (`run_rag → embed_query`,
  `similarity_search → PgVectorStore.similarity_search`);
- calls through an abstract-typed parameter (`embedder.embed`);
- which vector-store route an HTTP call hits (`CALLS_SERVICE` is service-level
  only);
- the Ollama `/api/embed` and pgvector SQL hops.

All of these are visible in the stored source text.

## Agreed next steps (owner decisions, 2026-11-12)

1. **Done.** #356 was merged, deployed, and the self-repo re-ingested by the
   owner (generation `8cbedbb9`).
2. **Done (2026-11-13).** The graph-trace rerun met the expected result. Pass
   `--expected-generation` to target any generation other than Step 0's.
   Remaining graph gaps: `to_thread` arguments, abstract dispatch, route-level
   HTTP, and the 300-node `/trace` cap. The `/api/embed` request now lives in
   `OllamaEmbedder._post`; the script's H9 ground truth still names `embed`.
3. **Then return to #342** with *route-grounded graph discovery plus source
   evidence fetching*. This is now issue #359. Its
   [protocol](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)
   (controls C1–C12) was **frozen on merge at `45f34e1`** (PR #360). Codex
   writes the sealed C7 and `mealie` ground truth by following the
   [Codex handoff](/DOCS/notes/20261113-359-codex-independent-evaluation-handoff.md),
   which also lists the prerequisites before any ingestion or run. The
   diagnostic has not started. Use the existing graph, route mapping and indexed source.
   Do **not** introduce another retrieval framework.
4. **Separate, diagnostic-first: #361** covers exact-file source retrieval
   and completeness-aware summarization, for example "read
   `ingestion_service/src/api/v1/repos.py` and summarize". By code reading,
   `/v1/rag` never fetches a named file. `prioritize_exact_sources` only
   reorders already-retrieved chunks, and only for repository-overview claims.
   A 10.4 KB file cannot fit the 4 KB budget, and nothing signals partial
   coverage. The issue keeps file discovery, document fetching and budget
   limitations separate.
5. **Out of scope until separately approved:** retrieval ranking, query
   planning, context budgets, generation settings and generation experiments.

## Environment and boundaries

- **The "production" Linux host is a development machine.** Repository docs and
  scripts call it production or deployed (`scripts/prod-refresh.sh`,
  `DOCS/deployment/*`). The owner develops mostly on a Windows laptop and treats
  the Linux box as a second development machine. Renaming that terminology is a
  separate cleanup, not part of this work. The operator-owned boundary in
  [agent-execution-and-verification.md](/DOCS/deployment/agent-execution-and-verification.md)
  still applies: no deploys and no checkouts there. Re-ingestion needs explicit
  owner approval.
- **The host address** comes from `REMOTE_OLLAMA_BASE_URL` in the git-ignored
  `.env`. Never print or commit it (`scripts/check_private_addresses.py`
  enforces this). Services are on ports 8001, 8002, 8003 and 8004; Postgres is
  on 5434.
- **SQL access is granted per task.** For #342 the owner authorized read-only
  SQL on 5434: `SELECT` and `EXPLAIN` without `ANALYZE` only, with no changes to
  data, schema, indexes, configuration or ingestion state. An agent's permission
  classifier may refuse SQL to a host it reads as production. If it does, ask
  the owner to authorize explicitly; do not work around it.

## Practical gotchas for the scripts

- **Use the root `.venv`.** Do not run `uv sync` inside `ingestion_service`.
- **Settings read `.env` from the working directory.** Importing orchestrator or
  ingestion code from the repository root reads the root `.env`, whose extra
  keys Settings rejects. The scripts `chdir` into the service directory for
  imports. Graph building also needs a placeholder `DATABASE_URL`; it is never
  connected to.
- **Raw captures go in the main checkout's `DOCS/test_results/_raw/`,** never
  in a worktree, which `git worktree remove --force` can delete. Index them with
  `scripts/raw_index.py update`, then fill `produced_by`, `cited_by` and
  `notes`. Drop any `__pycache__` entries that `update` picks up.
- **Use `2026-11-12-345-retrieval-candidates-run3.json` as the query-vector
  source** (it holds `query_vector`). The first run's file does not.
- **`/v1/vectors/search-by-doc` caps `k` at 100.** A larger `k` returns 422;
  the scripts raise on that so it cannot read as "no evidence".
- **CI note:** `vector_store_service`'s `test_ann_index_usage.py` (ANN
  result counts) failed once on 2026-11-12 and passed on re-run, with no
  related code change. Treat a single failure there as possibly intermittent;
  re-run once before investigating.
- **For a disposable corpus,** `git archive <sha> | tar -x -C <scratch dir>`
  gives exactly the tracked files an ingestion clone sees.

## Scripts

| Script | Purpose | Contacts |
|---|---|---|
| `scripts/discovery_diagnostic_342.py` | A/B/C discovery and hop representation | read-only HTTP (graph export, `/trace`, `search-by-doc`) |
| `scripts/fulltext_diagnostic_342.py` | full-text vs vector vs fusion ranking | read-only SQL (`SELECT` and `EXPLAIN`) |
| `scripts/validate_354_import_resolution.py` | graph before/after diff and source-verification sample | nothing (in-memory builds) |
