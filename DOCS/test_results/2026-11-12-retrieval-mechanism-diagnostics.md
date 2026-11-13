---
title: "Retrieval mechanisms: matched failure diagnostics and implementation study"
date: 2026-11-12
type: test-result
status: complete
summary: "Initial read-only ranking and navigation diagnostics completed; evidence-selection and end-to-end alternatives remain untested"
tags: [code-intelligence, retrieval, diagnostics, lexical-search, graph-navigation]
authority: "Observed diagnostic results on known development cases; no architecture adoption or implementation authorization"
related:
  - "[Strategy discussion index](/DOCS/notes/2026-11-12-strategy-notes/00-Strategy-Discussion-Index.md)"
  - "[November 11 failure evidence](/DOCS/notes/20261111-code-intelligence-retrieval-failure-evidence.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
  - "[Earlier architectural discussion](/DOCS/notes/2026-11-12-strategy-notes/2026-11-12-repository-intelligence-architecture-challenge.md)"
---

# Retrieval mechanisms: matched failure diagnostics and implementation study

## Corrected investigation objective

The owner clarified that the immediate task is to explain and improve this system's retrieval, navigation and delivery of implementation evidence. Product positioning, external-agent superiority and generalized patch benchmarks are separate questions. The earlier architectural recommendation was premature for this purpose.

This investigation therefore used the known LightRAG and self-repository failures, queried their existing corpus generations without changing them, and inspected specific external implementations. It does not select a replacement architecture. Its immediate findings are:

1. Raw-query LightRAG vector ranks reproduce the recorded failure. Adding the embedding model's prescribed retrieval prefix does not rescue it.
2. Source-only filtering improves ranks but still fails to find the relevant functions near the top. Lexical retrieval alone also fails at a small cutoff.
3. A diagnostic path-role filter plus lexical/vector fusion retrieves useful self-repository implementation candidates. LightRAG remains incomplete.
4. Exact endpoint navigation already reaches `rag_endpoint` through an existing `HANDLED_BY` edge, independently of vector seed ranking.
5. The LightRAG receiver is untyped, and method-name lookup produces two candidates. Parameter-annotation resolution or a globally unique-name assumption cannot by themselves bridge this call.
6. The final-context cap is accounted in UTF-8 bytes, and existing provenance labels do not drive general implementation-query selection. These are concrete downstream mechanisms to test next.

## Execution and evidence provenance

Read-only service metadata reported orchestrator and ingestion runtime `8bc0ed224b92b4f1b11a0542956b71a3ae22bb04`, release `prod-2026-11-11-0300pm`. Local source inspection used checkout `b24d093d3679cc964dbf61695a646a9cadebfe0e`; local behavior is not automatically deployed behavior.

| Corpus | Repository ID | Generation | Vector chunks |
| --- | --- | --- | ---: |
| LightRAG | `4f76a36f-caf8-5532-9ee2-977ec412ed6c` | `128c494e-0aae-4e1d-81d0-b7e52f2006b1` | 77,625 |
| Self repository | `f7641840-ba13-5f9d-9ae6-87e1f924709d` | `e423d1bb-e1d3-4d71-8200-3826c5987c95` | 24,081 |

The embedding service reported `mxbai-embed-large:latest`, digest `468836162de7f81e041c43663fedbbba921dcea9b9fefea135685a39b2d83dd8`. The original corpus source commit and ingest-time model digest were not independently established here. All ranking queries explicitly constrained repository and generation; counts checked afterward still showed the same single generation per repository. No re-ingestion, deployment, persisted vector changes, runtime edits or generated-answer calls occurred.

The November 11 short/long JSON, rank output and probe-script hashes were verified against the existing index. New results are recorded as `20261112-retrieval-mechanisms/rank-comparison.json` in the [raw index](/DOCS/test_results/raw-index.json). This contains query text, target suffixes, channel results, model identity, filter expressions, fusion settings and navigation evidence. The queries are diagnostic development cases, not independent evaluation fixtures.

## Comparison method

Three prompts were used: the recorded short LightRAG trace, the self-repository endpoint trace, and the recorded wording of the ingestion-workflow question. The last is a new diagnostic ranking run using the note's wording; no original Gradio JSON was available to reproduce its complete request configuration.

The comparisons were:

- **Raw vector:** exact cosine ordering over the generation's existing stored vectors; the current model embeds the raw query.
- **Prefixed vector:** identical stored vectors, with the publisher-prescribed retrieval prefix applied only to the query. The model card specifies this usage; its benefit here was tested rather than assumed. [Mixedbread model card](https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1).
- **Lexical:** PostgreSQL English `ts_rank_cd`, identifier/path text at weight A and body text at weight B. Underscores in canonical IDs were split into spaces. OR terms were manually chosen from each question's subject: `query | api | vector | retrieval`, `rag | orchestrator | vector | retrieval`, and `repo | ingest | ingestion`. This is a diagnostic full-text baseline, **not BM25 or an implemented query planner**.
- **Source-only:** `doc_type` ending in ` source`, applied before ranking.
- **Path-role scope:** source-only plus exclusion of directory components matching test(s), example(s), reproduce, benchmark(s), evaluation and fixtures. This is a deliberately coarse diagnostic scope, not a proposed universal production filter. Scripts and migrations can still win.
- **Fusion:** first 100 chunks per channel, ordered by score rank then canonical ID/chunk index; deduplicate to canonical artifacts within each channel; sum `1 / (60 + best_chunk_rank)` across vector and lexical channels. Sort ties by canonical ID. Target rows fetched separately for evaluation never enter fusion unless they are in the first 100 candidates.

Vector and lexical ranks below are best **chunk ranks** for each named symbol, with equal scores sharing ranks. Fusion ranks are **artifact ranks** after deduplication. Their numbers are not directly interchangeable: improvements combine discovery, filtering and changed result unit. No claim of a multiplicative rank improvement or answer-quality gain is made.

## Results: discovery

### LightRAG trace

| Expected symbol | Raw vector | Prefixed vector | Source-only vector | Path-role vector | Path-role lexical | Path-role fusion artifact rank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `_perform_kg_search` | 329 | 1,062 | 144 | 60 | 69 | 16 |
| `create_query_routes` | 668 | 644 | 317 | 136 | 27 | 45 |
| `_get_vector_context` | 1,165 | 1,997 | 605 | 256 | 82 | 114 |
| `naive_query` | 1,299 | 2,134 | 688 | 283 | 27 | 49 |
| `LightRAG.aquery_llm` | 2,356 | 3,063 | 1,376 | 551 | 220 | Outside fusion pool |
| `kg_query` | 2,606 | 4,177 | 1,541 | 626 | 27 | 48 |
| `query_text` | 2,924 | 4,017 | 1,770 | 714 | 203 | Outside fusion pool |
| `extract_keywords_only` | 7,861 | 7,929 | 5,619 | 2,509 | 2,552 | Outside fusion pool |

The raw ranks reproduce the recorded probe for these targets. Prefix-only correction fails as a remedy on this case. Source and path-role filtering remove competitors, but do not make the relevant functions top-five results. Lexical search adds useful candidates without completing the trace. Unfiltered fusion places `create_query_routes`, `kg_query` and `naive_query` at artifact positions 98, 101 and 102: fusion alone is not the answer.

Path-role fusion's first three artifacts are `lightrag/kg/postgres_impl.py`, `lightrag/operate.py` and `lightrag/lightrag.py`; the route module appears at 9. This suggests a concrete next test: use retrieved modules to discover relevant contained definitions. It does not prove their currently retrieved module passages contain the needed function bodies. The broad term “vector” also attracts storage implementation rather than the API-to-retrieval transition.

### Self-repository endpoint trace

| Symbol | Raw vector | Prefixed vector | Source-only vector | Path-role vector | Path-role lexical | Path-role fusion artifact rank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `rag_endpoint` | 401 | 280 | 69 | 30 | 10 | 4 |
| `hybrid_retrieve` | 849 | 1,131 | 174 | 75 | 7 | 6 |
| `run_rag` | 1,045 | 1,114 | 230 | 98 | 10 | 7 |

Path-role fusion puts all three expected definitions in the first seven artifacts. Unfiltered fusion still favors historical reports; only `hybrid_retrieve` enters that fusion pool, at artifact rank 101. The demonstrated lesson is the interaction between candidate scope and retrieval channel, not a blanket endorsement of RRF.

### Broad ingestion workflow

Raw and prefixed vectors both start with audit/source-snapshot reports. Source-only vector search starts with `_delete_repo_sync`, a test fixture helper and a test module. Path-role vector search starts with `_delete_repo_sync`, `ingest_repo` and `db_utils.py`.

Path-role fusion puts `ingest_repo` first, `codebase_ingest.py` third, `submit_ingestion` eighth and `_background_ingest_repo` ninth. Unfiltered fusion also puts `ingest_repo` first, followed by tests. Thus a useful entry point can be discovered without a supplied exact function name. This is evidence of improved localization only: the full acquisition/extraction/assembly/embedding/completion sequence was not scored or delivered in an answer.

## Results: navigation

### A successful existing mechanism for the self-repository failure

The pinned graph contains exactly this relationship:

```text
route:rag_orchestrator:POST:/v1/rag
    --HANDLED_BY-->
rag_orchestrator/src/api/v1/routes.py#rag_endpoint
```

The route itself has no source text; the handler supplies the implementation identity. The endpoint path and verb come from the user's question, not from an evaluator-supplied function name. The normal vector-first request can miss this already-indexed structural answer. An endpoint anchor should therefore be compared directly with semantic discovery for this class of query; adding a new graph database is unnecessary to test that mechanism.

### Why the LightRAG receiver is a real gap

Stored source begins with `def create_query_routes(rag, api_key: Optional[str] = None, top_k: int = 60):`. Its nested handler calls `rag.aquery_llm(...)`; `rag` is unannotated. The stored edge still targets `EXTERNAL_SYMBOL:rag.aquery_llm`.

Searching definitions for the observed method name returns both `LightRAG.aquery_llm` and `HangingRag.aquery_llm` in a test file. Name lookup can expose a plausible implementation that vector search misses, but selecting it solely because it is the only non-test candidate would still be an inference about receiver identity. Caller argument binding or another source witness is needed to establish the actual receiver.

Once `LightRAG.aquery_llm` is reached, stored edges to `kg_query` and `naive_query` exist. The edge from `_perform_kg_search` to `_get_vector_context` also exists. This localizes the problem more precisely than “the graph is broken”: a task-critical receiver boundary is missing while useful downstream relationships are already available. A bounded method-name search at that unresolved boundary is worth testing, with candidate ambiguity retained.

## Results: delivery and metadata

Recalculation from the saved final manifests gives:

| Captured request | Final source characters | Accounted bytes including labels/separators | Seed passage costs, excluding separators | Final content |
| --- | ---: | ---: | ---: | --- |
| Short | 3,650 | 3,950 / 4,096 | 3,942 | Five passages, all from seed artifacts |
| Long | 3,729 | 4,027 / 4,096 | 3,564 | Three seed passages, a test helper, and `QueryContextResult` |

`reproduce/Step_3.py` costs 1,936 bytes in each final context, about 47% of the cap. Its provenance role is `implementation`; example passages are correctly marked `example_fixture`. This is not a case where every classification field is absent.

The captured `token_count_method` is `utf8_bytes_upper_estimate`. Local [context assembly](/rag_orchestrator/src/retrieval/agent_adapter.py) implements this as UTF-8 byte length, not tokenizer measurement. Calling this a “4k-token context” obscures the actual amount of source delivered. A tokenizer-aware cap might permit more text, but simply changing units without respecting the real model window would be unsafe; first measure actual prompt and evidence token counts.

Local [service selection](/rag_orchestrator/src/core/service.py) places ordinary seeds before expanded documents, with narrow explicit-mention/overview exceptions. Chunk-count caps precede optional reranking, so a later reranker cannot recover candidates already removed. The [provenance diagnostics](/rag_orchestrator/src/retrieval/provenance_diagnostics.py) explicitly run after selection as shadow diagnostics and intentionally do not filter or score. This explains why adding metadata alone did not change retrieval. It reflects a staged policy boundary, not proof of a classification transport bug.

These source mechanisms are consistent with the captures. The full pre-budget source pool was not replayed in this session, so no improved allocation result is claimed. In particular, removing the reproduction passage frees capacity but does not by itself prove the required call witnesses will fill it.

## What the inspected external implementations actually contribute

Read on November 12; immutable commit references below. Neither project was executed against our corpora, and their performance claims were not independently reproduced.

### Code-Graph-RAG: `475e4e18aa0e1c6eb4e10355b26d366a2bb97c30`

- [Source retrieval](https://github.com/vitali87/code-graph-rag/blob/475e4e18aa0e1c6eb4e10355b26d366a2bb97c30/codebase_rag/tools/code_retrieval.py) resolves a qualified name through the graph and reads source, separating definition identity from semantic relevance.
- [Python type inference](https://github.com/vitali87/code-graph-rag/blob/475e4e18aa0e1c6eb4e10355b26d366a2bb97c30/codebase_rag/parsers/py/type_inference.py) builds local variable type information from parameters and assignments, with instance-attribute and property-return handling. It also treats name-based parameter inference as heuristic. This is a substantive mechanism to inspect for receiver resolution, but our unannotated closure receiver still requires a specific demonstration.
- [Structural search](https://github.com/vitali87/code-graph-rag/blob/475e4e18aa0e1c6eb4e10355b26d366a2bb97c30/codebase_rag/tools/structural_search.py) wraps AST-pattern matching and exposes capped results as truncated. It provides a search route independent of embedding similarity; it does not establish execution semantics.

Transferable tests: qualified-name source retrieval, receiver resolution on the exact stored LightRAG boundary, and AST-based route discovery. None requires adopting the project's whole stack.

### paulxiep/code-rag: `b42c1deae74fa92681f3fd4c197768ca2aaa5e84`

- [Intent policy](https://github.com/paulxiep/code-rag/blob/b42c1deae74fa92681f3fd4c197768ca2aaa5e84/crates/code-rag-engine/src/intent.rs) uses prototype embeddings and defaults to implementation intent; it includes optional ambiguity controls. Its policy enables BM25 for overview/relationship queries but disables it for implementation and comparison. Source comments report that identifier matching hurt implementation retrieval by promoting tests/callers; these are the author's findings, not ours.
- [Retrieval orchestration](https://github.com/paulxiep/code-rag/blob/b42c1deae74fa92681f3fd4c197768ca2aaa5e84/crates/code-rag-core/src/retriever.rs) supports body/lexical retrieval, optional signature fusion, and graph augmentation. Graph project selection depends on the leading candidate, so this design retains a possible seed error dependency.
- [Graph augmentation](https://github.com/paulxiep/code-rag/blob/b42c1deae74fa92681f3fd4c197768ca2aaa5e84/crates/code-rag-engine/src/graph.rs) can fall back from candidate identifier matching to a graph identifier index. It also reserves result slots for graph-derived chunks after reranking. This addresses both discovery outside vector candidates and later displacement, but reserved slots are not a guarantee of final byte-budget survival.
- [Searchable representation](https://github.com/paulxiep/code-rag/blob/b42c1deae74fa92681f3fd4c197768ca2aaa5e84/crates/code-rag-engine/src/text/searchable.rs) combines repeated identifier text, split identifier words, signature and docstring. This is a concrete representation alternative to undifferentiated body matching.

Transferable tests: route-specific channel selection, identifier-index fallback, and protection of verified evidence through the final allocation boundary. Copying classifier thresholds or enabling every retrieval channel is not supported by this study.

## What “state of the art” means for this problem

The sources reviewed do not establish one best repository retriever. There are distinct tasks: locating a named definition, finding a file from behavior, resolving references, and delivering sufficient source excerpts. A winner on one does not settle the others.

Two current research references are particularly relevant to these mechanisms:

- [Agent Retrieval Bench, July 2026](https://arxiv.org/abs/2607.24882) evaluates file retrieval rather than only final patches. It reports different winners for ranking, recall and budgeted context yield across lexical, embedding and repository-map methods. It supports measuring discovery and delivery separately, not declaring a universal hybrid winner.
- [RepoET, TOSEM 2026](https://xutangzhi.github.io/assets/pdf/repoet-tosem26.pdf) studies a staged file-search, file-filter, snippet-search and snippet-filter workflow, with tools for broad search and model assistance for selection. Its reported improvements on SWE-bench Lite and RepoQA make file-to-snippet retrieval a relevant challenger. They do not establish success on our trace questions. [Author implementation](https://github.com/SoftWiser-group/RepoET).

This is a focused, dated mechanism study, not an exhaustive leaderboard review. The useful frontier to investigate here includes hybrid candidate discovery, structural definition lookup, receiver-aware navigation and file-to-passage selection. More powerful models are one experimental variable, not an explanation for every failure.

## Engineering recommendations supported by this session

1. **Test exact route resolution in the normal query path.** The current corpus already provides the handler edge for the failed self-repository question. Compare retrieval and final delivery against the vector baseline before designing broader intent routing.
2. **Continue the multi-channel experiment with explicit source-role controls.** The diagnostic filtered fusion finds useful self-repository candidates, while unfiltered fusion and prefix-only changes fail. Replace the ad hoc lexical terms with a declared reproducible extraction policy before evaluating a deployable candidate. Test role preferences as well as hard exclusions so needed tests/examples are not lost.
3. **Test file-to-definition discovery on LightRAG.** Module artifacts are found much earlier than the functions. Determine whether bounded containment lookup plus source reading recovers the handler/core sequence. Do not claim that a large module chunk is already adequate evidence.
4. **Test the exact unresolved receiver boundary.** Compare candidate method-name lookup, call-site argument binding and the external resolver on the stored source. Require correct disambiguation between `LightRAG` and the test double; retain unknown when evidence is insufficient.
5. **Replay allocation independently of discovery.** Freeze the same fetched passages, ordering and actual source bytes. Compare seed-first selection with query-relevant passage selection and protected verified call witnesses. Keep the 4,096-byte cap for the initial comparison; separately measure a true tokenizer-based budget. Record every mandatory passage surviving into the final prompt.

The earliest demonstrated failure in the normal trace path is seed discovery. Exact route navigation bypasses it for the self-repository case; filtered fusion improves candidate discovery for both self-repository questions. LightRAG additionally requires better definition discovery and receiver navigation. Delivery remains a separate demonstrated loss point. These are narrower, evidence-grounded conclusions than selecting an adaptive or agent-oriented architecture.

Implementation decisions remain open. This session used ad hoc read-only diagnostics and documentation only; no reusable retrieval subsystem, prototype harness, GitHub issue or milestone was created. Further implementation follows explicit decisions and issue/milestone assignment. The next useful evidence is a matched navigation-and-delivery comparison on these same failures, not a product-positioning benchmark.
