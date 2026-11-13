---
title: "#342 A/B/C discovery diagnostic: can existing mechanisms find the POST /v1/rag implementation path?"
date: 2026-11-12
type: test-result
status: complete
summary: "Vector and identifier discovery find none of the chain; the route anchor works but graph traversal stops at hop 2 on an unresolved service-local import. One ingestion-side import-resolution rule would connect 8 of 13 chain nodes."
tags: [code-intelligence, retrieval, diagnostics, graph-navigation, import-resolution]
authority: "Observed read-only diagnostic on one known development question; no implementation authorization"
related:
  - "[#351 round 3 retrieval candidates](/DOCS/test_results/2026-11-12-345-round3-repro-and-retrieval.md)"
  - "[Retrieval-mechanism diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md)"
  - "[November 11 failure evidence](/DOCS/notes/20261111-code-intelligence-retrieval-failure-evidence.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #342 A/B/C discovery diagnostic

## Question and rules

The Step 0 question, unchanged:

> Trace the execution path from POST /v1/rag through the orchestrator to vector
> retrieval. Identify the actual Python functions and files involved, explain the
> call sequence, and distinguish direct function calls from HTTP service calls.
> Base the answer on implementation code rather than documentation or historical
> reports.

The question was asked of the self-repository generation `e423d1bb` (commit
`8e06335`), which was unchanged before and after the run. The services queried
were at `82b70cd`, on the Linux development host. Everything was read-only HTTP:
the graph export, the deployed `GET /v1/repos/{id}/trace`, and vector-store
`search-by-doc` to read stored text. Arm A reused the #351 capture, so there was
no model call at all. There was no generation, no SQL, no writes and no
re-ingestion. The script is `scripts/discovery_diagnostic_342.py` and the raw
record is `2026-11-12-342-abc-discovery.json` in the
[raw index](/DOCS/test_results/raw-index.json).

**No mechanism was given the expected functions.** The ground truth below (13
nodes, 16 hops) was checked against the source at `8e06335` and is used only to
score each mechanism after it has run. Three outcomes are scored separately:

- **Discovered:** the mechanism surfaced the node within its normal bound (the
  seed k = 20 for A and B; the server trace caps for C).
- **Connected:** the graph holds a relationship from the previous node to it.
- **Answerable:** the evidence suffices to explain the whole path.

## Ground truth: how each hop is represented

| Hop | From → to | Kind | In the graph | Witnessed in stored source text |
|---|---|---|---|---|
| H1 | `POST /v1/rag` route → `rag_endpoint` | route | exact (`HANDLED_BY`) | n/a |
| H2 | `rag_endpoint` → `run_rag` | direct | **placeholder** `EXTERNAL_SYMBOL:src.core.service.run_rag` | yes |
| H3 | `run_rag` → `resolve_repo_id_http` | direct | exact | yes |
| H4 | `resolve_repo_id_http` → ingestion `GET /v1/repos` | HTTP | service-level (`CALLS_SERVICE`) | yes |
| H5 | `run_rag` → `get_embedder` | direct | exact | yes |
| H6 | `get_embedder` → `OllamaEmbedder` | direct | exact | yes |
| H7 | `run_rag` → `embed_query` | function passed to `asyncio.to_thread` | **absent** | yes |
| H8 | `embed_query` → `OllamaEmbedder.embed` | call through a `BaseEmbedder` parameter | **placeholder** `embedder.embed` | yes |
| H9 | `OllamaEmbedder.embed` → Ollama `/api/embed` | HTTP, outside the repository | **absent** | yes |
| H10 | `run_rag` → `hybrid_retrieve` | direct | exact | yes |
| H11 | `hybrid_retrieve` → `_query_generation` | direct | exact | yes |
| H12 | `_query_generation` → ingestion `GET …/generation` | HTTP | service-level | yes |
| H13 | `hybrid_retrieve` → `POST /v1/vectors/search` | HTTP, cross-service | service-level only: the service exposes 7 routes, and the graph does not say which one is called | yes |
| H14 | vector route → `similarity_search` | route | exact (`HANDLED_BY`) | n/a |
| H15 | `similarity_search` → `PgVectorStore.similarity_search` | function passed to `asyncio.to_thread` | **absent** | yes |
| H16 | `PgVectorStore.similarity_search` → pgvector `<=>` | SQL | **absent** | yes |

Seven hops are exact edges, three are service-level only, two end at
placeholders and four are absent. **Every non-route hop is visible in the
indexed source text.** The text holds the whole chain; the graph structure does
not.

## A: vector seed search (current behaviour)

- The 20 seeds are all Markdown (12 sections, 8 modules), and so is the
  pre-budget pool.
- **Discovered 0 of 13.** Ranks among chunks: `hybrid_retrieve` 676, `run_rag`
  819, `rag_endpoint` 1,777. The other functions rank beyond 2,000. Routes have
  no text, so they are never vector candidates.
- Answerable: no. This confirms #351.

## B: lexical and symbol discovery from the question

**Existing query-mention extractors**, applied to the unchanged question:

| Mechanism | Result |
|---|---|
| `traversal_selector._extract_mentioned_methods` | nothing |
| `exact_source_preservation._targets` | nothing |
| `named_symbol_first._is_named` over every graph symbol name | false positives only: `Base`, `functions`, `implementation`, `sequence`, `service`, `vector` |
| `select_traversal_strategies` | `CALL` (the word "calls" in the question) |

The question names no symbols, so none of these can help.

**Identifier-token discovery.** Question tokens were matched against
canonical-ID tokens, weighted by IDF, with no hand-chosen terms.

| Scope | Nodes | Discovered in the top 20 | Best target ranks |
|---|---:|---|---|
| All nodes | 10,973 | 0 | vector route 102, `/v1/rag` route 166, `resolve_repo_id_http` 531 |
| Source symbols | 5,046 | 0 | `resolve_repo_id_http` 437, `similarity_search` 698 |
| Source symbols, path-role filtered | 2,552 | 0 | `resolve_repo_id_http` 126, `similarity_search` 347, `rag_endpoint` 414 |

The question's instruction words ("explain", "rather", "distinguish",
"historical") rarely appear in identifiers, so IDF ranks them highest. The top
results are tests, documentation sections and import nodes. The embedding chain
(`embed_query`, `get_embedder`, `OllamaEmbedder`) shares no token with the
question at all. Answerable: no.

**Not run: body-text full-text search with automatic terms.** It needs read-only
SQL against the development host's Postgres, and the session's permission
classifier refused it. The earlier
[mechanism diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md)
ran FTS with hand-picked terms. Re-running it with terms taken automatically from
the question is still open.

## C: graph-first from the route named in the question

**Route anchor.** The regex `METHOD /path` over the question text gives exactly
one graph node, `route:rag_orchestrator:POST:/v1/rag`, which has a `HANDLED_BY`
edge to `rag_endpoint`. **Discovery of the entry point works without any
supplied function name.**

| Traversal | Discovered | Result |
|---|---|---|
| Deployed `/trace`: `HANDLED_BY,CALL`, depth 6 | 2 of 13 | `route → rag_endpoint`, then **stops**. The next hop is `EXTERNAL_SYMBOL:src.core.service.run_rag`: 7 hops, 6 gaps. |
| Deployed `/trace`, adding `CALLS_SERVICE,EXPOSES_ENDPOINT` | 2 of 13 | Identical: the trace never gets past `rag_endpoint`. |
| Existing `hybrid_retrieve` expansion, seeded with the handler | 0 new | 6 expansions, all `EXTERNAL_SYMBOL` placeholders, so 0 fetchable documents. |
| **Counterfactual:** one rule resolving `src.`-prefixed placeholders inside the caller's service (`HANDLED_BY,CALL`) | **8 of 13** by depth 4 | 88 nodes reachable. Adds `run_rag`, `resolve_repo_id_http`, `get_embedder`, `OllamaEmbedder`, `hybrid_retrieve`, `_query_generation`. |
| The same rule, also following `CALLS_SERVICE → EXPOSES_ENDPOINT` | 10 of 13 by depth 6 | 155 nodes. The vector route and `similarity_search` are reached only by fanning out to all 7 vector-store routes. |

Graph traversal never reaches `embed_query`, `OllamaEmbedder.embed` or
`PgVectorStore.similarity_search` (H7, H8, H15), even under the counterfactual
rule.

## Root cause of the hop-2 break

`PythonModuleConvention.dotted_path`
([module_conventions.py](/ingestion_service/src/core/codebase/module_conventions.py))
names modules from the repository root, for example
`rag_orchestrator.src.core.service`. Each service imports from its own root
(`from src.core.service import run_rag`), so the import never matches, and every
call through such an import becomes an `EXTERNAL_SYMBOL`.
[service_topology.py](/ingestion_service/src/core/codebase/service_topology.py)
(`_module_to_relpaths`) already resolves imports relative to the service
directory, but only for route discovery.

Across the whole graph there are 10,251 CALL edges, 8,221 ending at
placeholders. **1,245 of the placeholders are `src.`-prefixed.** A service-root
rule (try `<service>/<module path>.py#symbol`) resolves 1,205 of them: 267 from
non-test code and 938 from tests. `run_rag → get_embedder` resolves today only
because `shared.*` is importable from the repository root.

## Conclusions

1. **No arm, as it stands, makes this question answerable.** A and B do not
   discover the implementation. C discovers the entry point but cannot connect
   past it.
2. **The graph holds the needed structure, cut by one resolution gap.** That gap
   is a graph-construction defect, not missing extraction. The chain's direct
   calls (H3, H5, H6, H10, H11) are already exact edges.
3. **Some hops are source-only by nature.** These are the external HTTP to
   Ollama (H9), SQL (H16), and which vector-store route is called (H13). In this
   generation the `CALLS_SERVICE` metadata is empty and does not identify the
   URL path. Answering them needs the callers' source text delivered, not
   traversal.
4. **Three in-repository hops need resolution beyond imports.** Two pass a
   function to `asyncio.to_thread` (H7, H15); 10 functions in the repository call
   `asyncio.to_thread`. One calls through an abstract-typed parameter (H8). The
   graph holds `OllamaEmbedder.embed OVERRIDES BaseEmbedder.embed`, but
   `MockEmbedder` is also a candidate, so any resolution must keep that
   ambiguity.

## Smallest defensible next change

1. **Ingestion: resolve service-root Python imports.** In the Python module
   convention or `GraphAssembler`, mirror `service_topology`'s existing
   convention. This change must follow ADR-031 and ADR-032. It requires a
   re-ingestion, and the result should be judged by re-running this diagnostic:
   the expected outcome is the counterfactual row, measured for real.
2. **Then query time: anchor `METHOD /path` in `/v1/rag`** as a code seed via
   `HANDLED_BY`. On its own it stops at hop 2, so it depends on change 1.

This diagnostic does not justify adding a graph engine, changing ranking policy,
adding a reranker or changing the budget. Delivery within the 4 KB budget (#194)
was not assessed. The 88 to 155 reachable nodes would still need selection.

## Limits

- One question on one repository. LightRAG was not re-run; its failure has a
  different cause (an untyped receiver; see the mechanism diagnostics).
- The identifier-token arm is a declared diagnostic baseline, not BM25 or a
  proposed retriever.
- The counterfactual rule was applied at query time over the exported graph. It
  estimates, and does not demonstrate, what re-ingestion with the fix would
  produce.
- The repo-wide counts in "Root cause" (1,245 `src.`-prefixed placeholders, 1,205
  resolvable) came from a separate ad hoc pass over the same graph export, not
  from the script. That pass used a broader rule than the script's
  counterfactual: the caller's first path component is taken as the service
  root, and tests are included. Neither the counts nor that rule are in the raw
  record. The ingestion issue must re-derive them.
- The raw record's `git_head` is the `main` commit the script ran from. The
  script was committed afterwards; only formatting changed.
