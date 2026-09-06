---
type: test-result
title: "RAG Quality Source-Code Evaluation - Remote Repo f7641840"
date: 2026-09-03
status: complete
tags: [rag-quality, retrieval, source-evaluation]
related:
  - "[RAG Quality Evaluation Methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)"
  - "[WP-Q0 RAG Quality Baseline](/DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md)"
---

# RAG Quality Source-Code Evaluation - Remote Repo f7641840

## Scope

This experiment evaluated the retrieval and answer quality of the running
RAG-FOUNDRY-UNIVERSAL instance against this repository's current source code.
The evaluator derived ground truth directly from local source files, then asked
the remote graph-aware RAG endpoint the same questions.

No files, code, configuration, tests, database contents, issues, commits, or git
state were intentionally modified as part of the evaluation. This file records
the experiment after the fact so the results are available as RAG quality test
data.

No further RAG/API testing was performed after the user requested that testing
stop.

## Environment

- Date: 2026-09-03
- Remote orchestrator health check: `GET http://100.105.24.12:8004/health`
  returned `200 {"status":"ok"}`.
- Remote graph-aware endpoint used:
  `POST http://100.105.24.12:8004/v1/rag`
- Remote UI was not used.
- Repository ID:
  `f7641840-ba13-5f9d-9ae6-87e1f924709d`
- Request shape:

```json
{
  "query": "<question>",
  "repo_id": "f7641840-ba13-5f9d-9ae6-87e1f924709d",
  "top_k": 5
}
```

- Model reported by all captured responses:
  `model_used=ollama/Qwen3:4b`, `model_alias=default`,
  `fallback_from=null`.

## Ground-Truth Source Files Read

- `rag_orchestrator/src/core/service.py`
- `rag_orchestrator/src/api/v1/routes.py`
- `rag_orchestrator/src/api/v1/models.py`
- `rag_orchestrator/src/core/simple_service.py`
- `rag_orchestrator/src/core/config.py`
- `rag_orchestrator/src/retrieval/agent_adapter.py`
- `rag_orchestrator/src/retrieval/codebase_queries.py`
- `rag_orchestrator/src/retrieval/codebase_utils.py`
- `rag_orchestrator/src/retrieval/execute_plan.py`
- `rag_orchestrator/src/retrieval/traversal_selector.py`
- `shared/config/service_urls.py`
- `docker-compose.yml`

## Results

| # | Question focus | Ground truth | RAG result summary | Classification |
|---|---|---|---|---|
| 1 | `hybrid_retrieve` direct calls | `hybrid_retrieve` directly calls `get_settings`, `_add_chunks`, `dedupe_near_identical_chunks`, `extract_canonical_ids_from_chunks`, `_rank_expanded_canonical_ids`, `canonical_to_document_map_http`, and `_fetch_expanded_doc_chunks`, excluding constructors, logging, builtins, and generic object methods. Source: `rag_orchestrator/src/core/service.py#hybrid_retrieve`. | RAG refused, saying implementation context was absent. Sources were specs, tests, and a flow diagram; no `service.py#hybrid_retrieve` implementation reached the answer context. | FAIL; incorrect; evidence missing; source quality tests/current docs; grounded refusal; graph expansion should help; likely failure class graph traversal/expansion miss. |
| 2 | `hybrid_retrieve` seed/fallback metadata filters | Initial vector filter is `{"source_type": "code", "repo_id": repo_id}`, with `language` added if provided. Fallback removes only `source_type`, keeping `repo_id` and `language` if provided. Source: `rag_orchestrator/src/core/service.py#hybrid_retrieve`. | Correct answer, but sources were docs/specs rather than the implementation. | WEAK PASS; correct; evidence incomplete; source quality current docs; reasonable inference; vector retrieval likely sufficient; likely failure class vector seed miss. |
| 3 | `run_rag` cross-service sequence | `run_rag` resolves repo via `resolve_repo_id_http` and `GET /v1/repos`, builds an embedder, calls `embed_query`, calls `hybrid_retrieve`, executes a retrieval plan, prepares chunks, builds labeled context, calls LLM service `POST /generate`, then builds sources. During hybrid retrieval it also calls vector search `/v1/vectors/search`, graph node lookup `/v1/graph/repos/{repo_id}/nodes`, and expanded-doc lookup `/v1/vectors/search-by-doc`. Source: `rag_orchestrator/src/core/service.py`. | RAG gave a mostly stale/design answer with invented helpers and files such as `resolve_repo_id`, `vector_search`, `doc_type`, and `rag_orchestrator/src/core/retrieval/vector_search.py`. Sources included ADR/current docs plus archived docs and route code. | FAIL; incorrect; evidence incomplete; source quality archived/current docs; fabricated; graph expansion should help; likely failure class source competition/distractor context. |
| 4 | `/v1/rag` endpoint call-through | `rag_endpoint` in `routes.py` calls `run_rag` with `query`, `repo_id`, `top_k`, `provider`, `model`, and `language`. It re-raises `HTTPException` unchanged. Source: `rag_orchestrator/src/api/v1/routes.py#rag_endpoint`. | RAG said the function was `rag_endpoint`, listed only `query`, `repo_id`, and `language`, and claimed the exception type was not in context. Sources included `routes.py`. | FAIL; partially correct; evidence complete; source quality implementation; grounded but incomplete; vector retrieval likely sufficient; likely failure class generation/reasoning error despite adequate evidence. |
| 5 | `_rank_expanded_canonical_ids` graph expansion | Imports/uses `get_cached_graph`, calls `select_traversal_strategies`, calls `execute_traversals_from_seeds`, and returns expanded node canonical IDs excluding seed IDs. Source: `rag_orchestrator/src/core/service.py#_rank_expanded_canonical_ids`. | Correct answer. Sources included `service.py#_rank_expanded_canonical_ids`, `codebase_utils#get_cached_graph`, and traversal selector functions. | PASS; correct; evidence complete; source quality implementation; grounded; explicitly graph-dependent. |
| 6 | Caller vs callee traversal selection | In `_RULE_TABLE`, intent `"callers"` selects `traverse_incoming_calls`; intent `"callees"` selects `traverse_calls`; both are wrapped by `_s(... depth=1)`. Source: `rag_orchestrator/src/retrieval/traversal_selector.py#select_traversal_strategies`. | Mostly correct, but intent labels were paraphrased as `"callers/called by"` and `"calls/call"` instead of exact table names. Sources included implementation and tests. | WEAK PASS; partially correct; evidence complete; source quality implementation/tests; grounded; graph expansion should help; likely failure class generation/reasoning error despite adequate evidence. |
| 7 | Traversal relation types and directions | `traverse_calls`: `CALL` forward. `traverse_incoming_calls`: `CALL` reverse. `traverse_defines`: `DEFINES` forward. `traverse_incoming_imports`: `IMPORTS` reverse. Source: `rag_orchestrator/src/retrieval/codebase_queries.py`. | RAG incorrectly said `traverse_incoming_imports` uses `IMPORT`, and hedged on the rest. Sources included a stale audit finding and related implementation-adjacent files, but not the exact function implementation evidence. | FAIL; partially correct; evidence incomplete; source quality stale docs plus implementation-adjacent sources; reasonable inference beyond evidence; explicitly graph-dependent; likely failure class stale documentation. |
| 8 | `canonical_to_document_map_http` behavior | If no canonical IDs, returns `{}`. Otherwise GETs `{INGESTION_SERVICE_URL}/v1/graph/repos/{repo_id}/nodes` with query parameter `canonical_ids` as comma-joined sorted IDs. It returns `{node["canonical_id"]: node["document_id"]}` for nodes containing both fields. On exception, logs a warning and returns `{}`. Source: `rag_orchestrator/src/core/service.py#canonical_to_document_map_http`. | Correct answer. Sources included `service.py#canonical_to_document_map_http` and related utility code. | PASS; correct; evidence complete; source quality implementation; grounded; vector retrieval likely sufficient. |
| 9 | `build_sources` source label precedence | `_source_label` prefers top-level `metadata.canonical_id`, nested `metadata.source_metadata.canonical_id`, top-level `metadata.relative_path`, nested `metadata.source_metadata.relative_path`, then `document_id`. `build_sources` keeps first-seen unique labels using a `seen` set. Source: `rag_orchestrator/src/retrieval/agent_adapter.py`. | Correct core answer, with extra unrelated rationale. Sources included `agent_adapter.py#build_sources`, `_source_label`, and tests. | PASS; correct; evidence complete; source quality implementation/tests; grounded; vector retrieval likely sufficient. |
| 10 | `run_simple_rag` vs `run_rag` retrieval | `run_simple_rag` uses vector filter `{"source_type": {"ne": "code"}}`; expands document graph with `expand_retrieval_plan` and `TraversalConstraints(max_depth=1, allowed_relation_types={"DEFINES"})`; fetches missing expanded docs from `/v1/vectors/search-by-doc` with `k=3`. Unlike `run_rag`, it does not perform repo-scoped code hybrid canonical traversal. Source: `rag_orchestrator/src/core/simple_service.py`. | RAG refused, claiming implementation details were absent, despite sources including `simple_service.py` and expansion to `simple_service.py#run_simple_rag`. | FAIL; incorrect; evidence complete; source quality implementation; fabricated absence claim; graph expansion should help; likely failure class generation/reasoning error despite adequate evidence. |

## Captured RAG Sources

The RAG answers reported these source sets:

1. `specs/003-language-aware-retrieval/research.md#phase_0_research_wp_l6a_language_aware_retrieval`; `rag_orchestrator/tests/test_repo_scoping.py`; `specs/003-language-aware-retrieval/research.md#phase_0_research_wp_l6a_language_aware_retrieval.test_precedent`; `DOCS/architecture/Repo-query-ascii-flow-diagram.md`; `rag_orchestrator/tests/test_repo_scoping.py#_run_hybrid_with_empty_store`
2. `DOCS/architecture/Repo-query-ascii-flow-diagram.md`; `DOCS/audit/00-Audit-Overview.md#audit_overview_rag_foundry_universal.current_status_2026_08_29_supersedes_the_2026_08_27_status_below`; `specs/003-language-aware-retrieval/research.md#phase_0_research_wp_l6a_language_aware_retrieval.v1_rag_request_response_and_service_layer`
3. `DOCS/architecture/Repo-query-ascii-flow-diagram.md`; `docs-archive/DOCS-docgraph/DESIGN/onepagerendofproject.md#ms5_rag_system_developer_cheat_sheet.1_quick_overview`; `docs-archive/DOCS-docgraph/DESIGN/onepagerendofproject.md#ms5_rag_system_developer_cheat_sheet.2_core_components`; `rag_orchestrator/src/api/v1/routes.py#rag_endpoint`; many sections of `DOCS/adr/ADR-045-hybrid-vector-graph-rag.md`
4. `ingestion_service/src/ui/gradio_app.py`; `rag_orchestrator/src/api/v1/routes.py`; `DOCS/architecture/Repo-query-ascii-flow-diagram.md`; `specs/003-language-aware-retrieval/tasks.md#tasks_wp_l6a_language_aware_retrieval_filter.phase_3_user_story_1_distinguish_extraction_failures_from_retrieval_leakage_priority_p1_mvp.implementation_for_user_story_1`; `rag_orchestrator/tests/test_language_scoping.py`
5. `DOCS/architecture/platform-graph-architecture-expanded.md#docs_adr_adr_044_graph_models_in_shared_md.graph_schema_lifecycle`; `rag_orchestrator/src/core/service.py#_rank_expanded_canonical_ids`; `rag_orchestrator/src/core/service.py`; `rag_orchestrator/src/retrieval/codebase_utils.py#get_cached_graph`; `rag_orchestrator/src/retrieval/traversal_selector.py#execute_traversals_from_seeds`; `rag_orchestrator/src/retrieval/traversal_selector.py#select_traversal_strategies`
6. `rag_orchestrator/src/retrieval/traversal_selector.py`; `DOCS/architecture/Repo-query-ascii-flow-diagram.md`; `rag_orchestrator/tests/test_traversal_selector_routing.py`; `rag_orchestrator/src/retrieval/traversal_selector.py#select_traversal_strategies`; `rag_orchestrator/src/retrieval/traversal_selector.py#_matches_any`
7. `rag_orchestrator/src/retrieval/traversal_selector.py`; `rag_orchestrator/src/retrieval/__init__.py`; `DOCS/audit/01-Codebase-Audit-Findings.md#codebase_audit_findings.p0_graph_correctness.f_02_import_relationships_are_never_created`; `rag_orchestrator/src/core/service.py`; `DOCS/architecture/Repo-query-ascii-flow-diagram.md`; `rag_orchestrator/src/retrieval/traversal_selector.py#execute_traversals_from_seeds`; `rag_orchestrator/src/retrieval/traversal_selector.py#select_traversal_strategies`
8. `rag_orchestrator/src/core/service.py#canonical_to_document_map_http`; `DOCS/architecture/Repo-query-ascii-flow-diagram.md`; `rag_orchestrator/src/retrieval/codebase_utils.py#canonical_ids_to_document_ids`; `rag_orchestrator/src/retrieval/codebase_utils.py`
9. `DOCS/audit/00-Audit-Overview.md#audit_overview_rag_foundry_universal.current_status_2026_08_30_supersedes_the_2026_08_29_status_below`; `DOCS/audit/00-Audit-Overview.md`; `rag_orchestrator/tests/test_build_sources.py`; `rag_orchestrator/src/retrieval/agent_adapter.py#build_sources`; `rag_orchestrator/src/retrieval/agent_adapter.py#_source_label`; several `test_build_sources.py` test functions
10. `rag_orchestrator/src/core/simple_service.py`; `CLAUDE.md#claude_md.architecture_independent_services_over_http`; `DOCS/architecture/platform-graph-architecture-expanded.md#docs_adr_adr_044_graph_models_in_shared_md.graph_schema_lifecycle.1_documentnode`; `DOCS/architecture/platform-graph-architecture-expanded.md#docs_adr_adr_044_graph_models_in_shared_md.logical_architecture`; `DOCS/architecture/platform-graph-architecture-expanded.md#docs_adr_adr_044_graph_models_in_shared_md.logical_architecture.diagram_platform_graph_architecture`

## Aggregate Counts

Overall result:

- PASS: 3
- WEAK PASS: 2
- FAIL: 5

Correctness:

- correct: 4
- partially correct: 3
- incorrect: 3

Evidence completeness:

- complete: 6
- incomplete: 3
- missing: 1

Likely failure class for imperfect rows:

- vector seed miss: 1
- graph traversal/expansion miss: 1
- source competition/distractor context: 1
- stale documentation: 1
- generation/reasoning error despite adequate evidence: 3

## Retrieval/Context vs Generation

Retrieval or context failures:

- Q1: exact `hybrid_retrieve` implementation evidence did not reach context.
- Q2: answer correct, but evidence came from docs/specs rather than source.
- Q3: stale/design and archived context displaced current implementation.
- Q7: stale audit/documentation context competed with exact current function
  evidence.

Generation failures despite adequate or near-adequate evidence:

- Q4: `routes.py` was present, but the answer missed passed fields and
  `HTTPException`.
- Q6: implementation was present, but exact intent labels were paraphrased.
- Q10: `simple_service.py` and `run_simple_rag` expansion were present, but the
  answer claimed implementation details were absent.

## Candidate Failure Retest

Candidate question:

> According to the actual implementation of `hybrid_retrieve` in
> `rag_orchestrator/src/core/service.py`, list every non-builtin helper/service
> function it directly calls. Exclude constructors, logger calls, and generic
> object methods such as `dict.get`, `resp.json`, and `raise_for_status`. Use
> only implementation evidence, not docs or tests.

Finding:

The required `hybrid_retrieve` implementation evidence did not reach the RAG
answer context. The retrieval plan included
`EXTERNAL_SYMBOL:src.core.service.hybrid_retrieve`, but the answer sources were
tests, specs, and documentation rather than
`rag_orchestrator/src/core/service.py#hybrid_retrieve`.

## Recurring Quality Problems

1. Implementation questions often seed or expand into docs, tests, or specs
   instead of exact function chunks.
2. Stale or design-stage documentation competes strongly with current source
   and can produce outdated answers.
3. When implementation evidence is present, the model can still claim it is
   absent or miss fields visible in the cited source.

## What Worked Well

Graph-aware expansion worked well for precise function-local questions when the
exact function chunk was retrieved, especially `_rank_expanded_canonical_ids`
and `canonical_to_document_map_http`.

Source labeling retrieval also performed well for `agent_adapter.py` and its
related tests.

## Follow-Up Measurement Hypotheses

No implementation changes are recommended from this experiment alone. Follow-up
measurement should focus on:

- Exact function-target recall for implementation-only questions at `top_k=5`,
  `top_k=10`, and `top_k=20`.
- Whether graph expansion from `EXTERNAL_SYMBOL:*` nodes can recover owning
  implementation chunks.
- Stale-documentation competition rate when questions explicitly name current
  source files and functions.
