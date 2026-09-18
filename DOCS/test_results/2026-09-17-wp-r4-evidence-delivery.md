---
title: "WP-R4 evidence-delivery implementation verification"
date: 2026-09-18
type: test-result
status: complete
tags: [retrieval, evidence, verification]
related:
  - "[WP-R4 specification](/specs/005-production-correctness/issues/evidence.md)"
  - "[ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)"
  - "[Quality methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)"
  - "[Quality evaluation results](/DOCS/test_results/2026-09-18-wp-r4-quality-evaluation.md)"
---

# WP-R4 verification checkpoint

Branch: `fix/wp-r4-evidence-delivery`, commit `cbb84d7`.
Base: `3ba6a2f4cec4d3e0724859d70aeff98bb7f7880f`.
Results below (mechanics section) were re-run fresh on 2026-09-18 against
`cbb84d7` itself (not the uncommitted working tree the prior checkpoint
described) and reproduce identically. **This doc covers mechanics only.**
The quality-evaluation gate (frozen 8-question set vs. legacy runtime,
partial clean-context control) initially could not be executed this
session against local CPU Ollama — see "Quality evaluation attempt"
below for that record — but **completed successfully after switching to
the Tailscale production Ollama**; see the
[quality evaluation doc](/DOCS/test_results/2026-09-18-wp-r4-quality-evaluation.md)
for the actual results (net positive, no blocking findings).

## Code-level review against ADR-052 (2026-09-18) — no defects found

Read the full diff (`git diff 3ba6a2f...cbb84d7`) against every clause of
[ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md) and
the [WP-R4 spec](/specs/005-production-correctness/issues/evidence.md)'s
acceptance/verification section. Each contract clause traced to the
specific code that implements it; no gaps or contradictions found:

- **Passage API contract**: `PgVectorStore.get_chunks_by_document_id`
  accepts `query_vector`/`repo_id`/`ingestion_id`, orders by exact cosine
  similarity → stored `chunk_index` → `chunk_id` with a query vector, by
  `chunk_index, chunk_id` without one. `VectorSearchByDocRequest.k` is
  bounded `ge=1, le=100`. Matches ADR-052's "Decision under verification"
  paragraph exactly.
- **Relaxed ANN sort**: `similarity_search` now explicitly
  `.sort(key=lambda r: (-score, chunk_id))` after the DB round-trip —
  covers the "relaxed_order HNSW does not guarantee distance order"
  comment and the ADR's "Sort relaxed ANN results explicitly" clause.
  Confirmed by `test_relaxed_ann_candidates_are_explicitly_sorted`.
- **Generation-scoped retrieval**: `hybrid_retrieve` resolves
  `generation_id` via `_query_generation` before seed search, scopes both
  the primary and source-type-relaxed fallback seed filters to it, and
  calls `_verify_generation` again after passage fetch, raising 409 on
  change / 503 when not ready — matches "resolves a ready generation
  before seed search... verifies it again after retrieval."
- **Stored ordinal vs. fetch position**: `RetrievedChunk` now carries
  both `chunk_index` (from stored metadata, nullable) and
  `fetch_position` (list position) as distinct fields; `_add_chunks` sets
  them independently. `chunks_requested_by_document` reports a count
  (`EXPANDED_DOC_CHUNKS`) via `dict.fromkeys`, not an invented
  `range()` — matches "Fetch requests report counts, not invented
  ordinal ranges" (this was the prior code's actual bug: `range(k)`
  presented as if it were the requested ordinals).
- **Seed supplementation**: `passage_doc_ids = list(retrieved_chunks_by_document) + expanded_doc_ids`
  in `hybrid_retrieve`, and `seed_document_ids + selected_expanded` in
  `simple_service.run_simple_rag` — both now fetch supplementary
  query-relevant passages for seeds, not just graph-expanded docs.
- **Query-term lexical preference**: `_rank_expanded_canonical_ids` sorts
  candidates by `(strategy_index, -overlap_with_query_terms)` — preserves
  relation-priority ordering, breaks ties toward query-matching symbols,
  exactly as specified ("does not claim semantic recall").
- **Single context-assembly pass**: `assemble_context` replaces the old
  separate `select_chunks_within_token_budget` + `build_labeled_context`
  pair; returns `AssembledContext(text, chunks, token_count)` from one
  loop. `sources`/`build_final_context_manifest` in both `run_rag` and
  `run_simple_rag` are now derived from `assembled.chunks` (the
  post-budget selection), not pre-budget `agent_chunks` — matches
  "Derive sources and manifest from that same selection." Manifest rows
  add `text_sha256`, `chunk_index`, `fetch_position` as specified.
  Oversized passages are skipped via `continue` (not the old `break`),
  so later passages are still considered — matches "Skip oversized whole
  passages and continue considering later passages."
- **Reranker loss separated**: `finalize_evidence_survival` gained
  `reranked_document_ids`; its `drop_reason` `elif` chain now attributes
  `dropped_by_reranker` distinctly from `DROP_CHUNK_LIMITS`/
  `DROP_TOKEN_BUDGET`, and a new `survives_rerank` field is exposed.
  Confirmed by `test_reranker_loss_is_distinct_from_chunk_and_budget_loss`.
- **Budget contract**: `config.py` adds `CONTEXT_WINDOW_TOKENS=8192`,
  `PROMPT_RESERVE_TOKENS=1024`, `OUTPUT_RESERVE_TOKENS=2048` — matching
  ADR-052's stated defaults exactly. `context_budget = min(max_total_tokens,
  max(0, CONTEXT_WINDOW_TOKENS - PROMPT_RESERVE_TOKENS - OUTPUT_RESERVE_TOKENS
  - conservative_token_count(query)))` in both `run_rag` and
  `run_simple_rag`, floored at zero, matches the ADR's formula verbatim.
  `token_count_method: "utf8_bytes_upper_estimate"` is recorded in the
  retrieval plan, not silently assumed.
- **Simple-document expansion**: `run_simple_rag` now fetches chunks for
  seeds and expanded docs together via the same `_fetch_expanded_doc_chunks`
  helper `run_rag` uses, and exposes `final_context_manifest` on
  `SimpleRAGResult` — the old code fetched expansions but then dropped
  them at `prepare_chunks_for_agent(document_order=seed_document_ids)`;
  that omission is fixed (`document_order=passage_doc_ids`).
- **No new embedding/reranker default changed**: confirmed — no
  `RERANK_ENABLED`, `EMBEDDING_PROVIDER`, or model default touched
  anywhere in the diff.

One incidental, in-scope correctness fix noticed during review (not a
regression, not flagged as a problem): `execute_retrieval_plan` already
accepted a `top_k_per_document` parameter (default 5) that neither
`run_rag` nor `run_simple_rag` was passing before this branch — so a
caller-supplied `max_chunks_per_doc` was previously enforced only later,
at `prepare_chunks_for_agent`. Both call sites now pass
`top_k_per_document=max_chunks_per_doc` explicitly. Behavior-neutral for
every existing default-parameter caller (5 either way).

All eight frozen questions' code premises (`DOCS/evaluations/wp-r4-questions.json`)
were independently re-checked against current `cbb84d7` source (not just
trusted from when the set was frozen): `cache`, `drop`, `chain`,
`ambiguous`, `link`, `limits`, `ties`, `truncate` all still match the
named functions/constants/control-flow exactly as their
`required_substrings`/`rubric` describe. The frozen set's premises have
not drifted.

## Executed checks

From `rag_orchestrator`, `../.venv/Scripts/python.exe -m pytest -q --tb=short`:
173 passed, 1 skipped (live model A/B environment not configured).

From `vector_store_service`, `../.venv/Scripts/python.exe -m pytest -m unit
-q --tb=short`: 28 passed, 13 deselected.

Root `.venv/Scripts/python.exe -m ruff check .`: passed.

Isolated `docker-compose.test.yml` PostgreSQL on localhost:5433, database
`ingestion_test`, migrated with root `python -m alembic upgrade head`:
`pytest tests/core/vectorstore/test_wp_r4_passages.py -q --tb=short` passed
(1 test). It writes and cleans up unique test identities, proves tail ordinal
97 ranks first among 100 passages, stable ordinal ties, generation/repository
filtering, ordinal-only fallback and sorted seed scores. Initial fixture
failures (missing artifact FK, UUID repository type and UUID/string comparison)
were corrected before this passing run; they were not product-query failures.
The new integration test is explicitly included in CI.

Focused pyright with `--pythonpath .venv/Scripts/python.exe` found two existing
environment/baseline issues: missing `sentence_transformers` and the vector
settings constructor's required `DATABASE_URL`. Full type-check success is
not claimed.

Re-run 2026-09-18 via `uv run pyright <touched files>` from the repo root
(root `pyrightconfig.json`, a different invocation than the above): 0
errors/warnings/informations on all seven touched files (`service.py`,
`simple_service.py`, `agent_adapter.py`, `evidence_trace.py`, `types.py`,
`pgvector_store.py`, `vectors.py`). Narrower scope than the prior run
(explicit file list vs. whatever `--pythonpath` covered), so this doesn't
contradict the earlier baseline-noise finding — just confirms no new
type errors on the files this branch actually changed.

## Payload coverage

`test_wp_r4_payload.py` captures outgoing `/generate` JSON and checks seed tail
supplementation, same-relation overload, simple-document expansion, source /
manifest agreement, generation-change refusal and separate reranker loss.
`test_wp_r4_context.py` checks oversized-passage continuation and UTF-8/label/
separator accounting. These are deterministic mechanics tests using controlled
responses, not embedding or answer-quality evaluations.

## Quality evaluation attempt (2026-09-18) — could not complete

Reviewed the budget/evidence-trace behavior against every ADR-052 clause
(above — complete, no defects found) and attempted the frozen 8-question
quality run per [the protocol](/DOCS/evaluations/2026-09-17-wp-r4-protocol.md)
(baseline/WP-R4/matched-budget-control arms, clean/noisy-context
generation comparison). **The evaluation corpus never finished
ingesting**, across four attempts, each hitting a different failure on
this local machine:

1. **Real-PostgreSQL crash under I/O pressure**: the isolated test
   Postgres container (`ingestion-db-test`) crashed mid-embedding
   ("database system was not properly shut down; automatic recovery in
   progress") at 286/396 nodes. Recovered cleanly (WAL replay,
   no data loss), but the in-flight ingestion attempt was left
   inconsistent and had to be restarted.
2. **Local misconfiguration on restart**: relaunching `ingestion_service`
   after the crash omitted `VECTOR_STORE_SERVICE_URL`, so it silently
   fell back to the Docker-only hostname `vector_store_service:8002`
   (unresolvable outside Docker) — every embedding-batch write failed,
   and the job appeared to "stall" at a fixed node count with
   `chunks_persisted: 0` until enough retries exhausted and it failed
   outright. This was a session/harness setup error, not a WP-R4 code
   defect.
3. **Ollama embedding throughput**: with the URL corrected, ingestion
   progressed but very slowly — a single-string `mxbai-embed-large`
   embed call on this machine's Ollama (CPU-only, `size_vram: 0`) took
   20-48s in isolation; a real batch of ~50 chunks exceeded the
   embedder's 120s read timeout and the job failed again at 202/396
   nodes. Retried with `OLLAMA_BATCH_SIZE=8` to fit under the timeout.
4. **Session memory pressure**: before the smaller-batch retry could
   finish, Claude Code's own background-process memory-pressure guard
   killed both locally-launched `ingestion_service` and
   `vector_store_service` processes ("system is running low on memory")
   at 26/396 nodes into that attempt. Per that guard's explicit
   instruction, these were not relaunched again this session.

None of these four failures originate in the code under review on
`fix/wp-r4-evidence-delivery` — all four are this session's local
infrastructure (a resource-constrained Windows machine already running
Docker, multiple Python service processes, and a CPU-only Ollama
instance, concurrently). No question in the frozen set was answered by
any arm (WP-R4, legacy, or matched-budget-control); no clean/noisy
generation comparison was run; no baseline was captured.

**This local-Ollama attempt did not satisfy the quality-acceptance gate.**
That gate was subsequently satisfied in the same session by retrying
against the Tailscale production Ollama instead — see
[the quality evaluation doc](/DOCS/test_results/2026-09-18-wp-r4-quality-evaluation.md)
for the actual results. This section is retained as-is (not rewritten)
because the four failure modes it documents are real, reproducible
findings about this local machine's suitability for CPU-bound Ollama
workloads under memory pressure, independent of whether the eval
eventually succeeded another way.

## What actually unblocked it

Per the "Recommended next attempt" note this section originally ended
with: pointing the eval harness's `OLLAMA_BASE_URL` at the
Tailscale-reachable production Ollama (100.105.24.12:11434, GPU) instead
of this session's local CPU-only Ollama resolved the throughput problem
completely — no code changes were needed, only which endpoint the
harness's `ingestion_service`/`vector_store_service`/`llm_service`
pointed at. Fresh ingestion of the same pinned corpus completed in
minutes with zero failures. The isolated eval harness scripts
(`run_eval.py`, `run_clean_context.py`) and the legacy-revision worktree
(`../rag-foundry-legacy-r4-base`) used for this are still scratchpad,
not committed; see `.wp-r4.tmp/` in the repo working tree.

## Owner-requested handoff

Original checkpoint requested near a usage limit; that live process/job
state (ports, PIDs, database names) recorded in
[HANDOFF](/specs/005-production-correctness/HANDOFF.md) is now stale —
all of those specific processes/jobs no longer exist (superseded by the
four attempts above, all of which also failed). Do not reuse those PIDs
or job IDs. The [quality protocol](/DOCS/evaluations/2026-09-17-wp-r4-protocol.md)
and questions are still frozen and still valid; still no quality query
or generation control has successfully run end to end.
