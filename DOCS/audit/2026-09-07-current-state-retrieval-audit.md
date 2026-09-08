---
title: "Current-state retrieval audit: three next investigations"
date: 2026-09-07
type: audit
status: complete
tags: [audit, retrieval, graph, context-selection, scalability]
source_commit: 9044d68a5c1821854aaac9089d186f177ab5f937
related:
  - "[[00-Audit-Overview]]"
  - "[[08-RAG-Quality-Evaluation-Methodology]]"
  - "[[../test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline]]"
---

# Current-state retrieval audit

Scope: current code at the commit above, historical evaluations, and limited read-only production API checks authorized during this audit. Only this report was written. No services, data, dependencies, configuration, or existing documentation were changed.

Validation: dependency-free, in-memory execution of current function definitions reproduced same-relation ranking loss and context/source disagreement. Existing `test_evidence_survival.py` and `test_expansion_caps.py` could not collect because local Python lacks `httpx`; local Docker had no running containers. No full-suite, new generation evaluation, or live performance result is claimed.

**Production spot-check, 2026-09-07:** APIs at `100.105.24.12` were reachable; `/v1/models` reported default `ollama/Qwen3:4b`. For repo `f7641840-ba13-5f9d-9ae6-87e1f924709d`, canonical lookup followed by `/v1/vectors/search-by-doc` at k=3 and k=100 produced:

| Stored function | Rows at k=100 | Indices returned at k=3 | Implementation present only in larger fetch |
|---|---:|---|---|
| `hybrid_retrieve` | 13 | 0, 1, 2 | Seed-filter assignment, expanded-document cap, expanded-chunk fetch call |
| `run_simple_rag` | 17 | 14, 0, 1 | `expand_retrieval_plan`, `/search-by-doc`, `build_labeled_context` |
| `build_labeled_context` | 3 | 0, 1, 2 | None; complete small-artifact control |

All rows belonged to ingestion `c171cc00-3be7-42c4-bb21-328412d40a7f`. The latter two functions' chunk texts matched local chunker output. Stored `hybrid_retrieve` lacked `trace_canonical_ids` and `compute_partial_evidence_survival`, which exist in the checkout: **corpus snapshot drift is confirmed; production runtime revision is not established**. These bounded retrieval reads did not invoke generation or ingestion.

## 1. Current-state verdict

- **Seed retrieval is scoped, but “code” does not mean implementation-only.** `hybrid_retrieve()` searches cosine-ranked chunks with `repo_id`, `source_type="code"`, and optional language; fallback preserves repo/language. It deduplicates near-identical seeds after top-k, without refilling. Repository Markdown also receives `source_type="code"`, allowing docs/tests to compete with implementation. HTTP default top-k is **5**, versus **20** for direct Python calls. Sources: [hybrid_retrieve](../../rag_orchestrator/src/core/service.py#L231), [_embed_repo_artifacts](../../ingestion_service/src/api/v1/codebase_ingest.py#L79), [RAGQuery](../../rag_orchestrator/src/api/v1/models.py#L6).

- **Graph expansion is real, with limited measured benefit.** Every seed is expanded; current ranking uses `(best_strategy_index, -seed_hits, canonical_id)`. Under default strategies, DEFINES precedes CALL, but neither vector score nor actual path distance distinguishes same-priority candidates. The recorded live comparison improved one target from rank **24 to 12**, while another improved **137 to 88** and remained outside the default **20-document** cap. This supports useful discovery/selection, not a general answer-quality improvement. Sources: [execute_traversals_from_seeds](../../rag_orchestrator/src/retrieval/traversal_selector.py#L209), [historical comparison, section 16](../test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md).

- **Finding an artifact does not ensure fetching its relevant passage.** Repository ingestion sub-chunks artifact text; `/search-by-doc` defaults to **3 rows**, with neither query scoring nor `ORDER BY`. The production spot-check above confirmed three fetched rows omitted relevant implementation present in the same stored document; `run_simple_rag` returned indices **14, 0, 1**, not source order. Already-seeded documents receive no supplementary fetch. Local chunking produced 15 chunks for current `hybrid_retrieve`, versus the older corpus's 13. Ollama additionally embeds only the first **800 characters** of each input, potentially omitting searchable content. Sources: [_embed_repo_artifacts](../../ingestion_service/src/api/v1/codebase_ingest.py#L79), [ChunkerFactory.choose_strategy](../../shared/chunkers/selector.py#L25), [get_chunks_by_document_id](../../vector_store_service/src/core/vectorstore/pgvector_store.py#L239), [_truncate](../../shared/embedders/ollama.py#L13).

- **Context selection introduces further loss and overstates provenance.** After fetching, `execute_retrieval_plan()` slices to five chunks/document without ranking; preparation keeps seed documents first and defaults to 50 total chunks. `build_labeled_context()` then stops entirely at the first chunk exceeding the remaining 4,096-word approximation, excluding labels from its count. Both `sources` and `reaches_final_context` use the earlier chunk list/document IDs. An in-memory probe reported a helper source while its text was absent from the assembled context. Sources: [execute_retrieval_plan](../../rag_orchestrator/src/retrieval/execute_plan.py#L13), [run_rag](../../rag_orchestrator/src/core/service.py#L378), [build_labeled_context](../../rag_orchestrator/src/retrieval/agent_adapter.py#L55).

- **Traversal is narrower than the stored graph.** The first regex rule wins; each selected traversal runs one hop from the seed plus its depth-two DEFINES descendants. This broadens candidate fan-out without retaining path distance. Generic “imports” selects incoming imports, even for wording asking what a module imports. `GraphAssembler` creates DOCUMENTS edges, but the production selector never traverses them. These are traversal/coverage risks, distinct from dropping an already-discovered target. Sources: [select_traversal_strategies and execute_traversals](../../rag_orchestrator/src/retrieval/traversal_selector.py#L121), [traverse_incoming_imports](../../rag_orchestrator/src/retrieval/codebase_queries.py#L132), [GraphAssembler._link_docs_to_code](../../ingestion_service/src/core/codebase/graph_assembler.py#L754).

- **Generation has a clear service boundary; its failures need controlled attribution.** Labeled context goes to `/generate`, then LiteLLM with a versioned grounding prompt, model resolution, retries, and fallback. There is no answer-verification stage. Historical Q4/Q6/Q10 suggest generation failures, but source names and document-level traces cannot establish that the required passage reached the prompt. Sources: [generate_completion / _complete](../../llm_service/src/core/llm_client.py#L44), [grounding prompt](../../llm_service/src/core/prompts/rag_answer.v1.txt), [source evaluation](../test_results/2026-09-03-rag-quality-source-eval.md).

- **A successful TypeScript control argues against a blanket extractor failure.** User-supplied observation during this audit, not independently rerun: with Qwen3:4b, a broad query at top-k 10 reportedly included the right TS code but answered “implementation unavailable”; top-k 5 was mostly correct but omitted `upsertAdvisoryContext`. A narrow symbol query at top-k 5 correctly traced default-record creation, uppercase normalization, patch merging, forced symbol, ISO timestamp, and `saveContext()`. The prompt called it `upsertAdvisoryRecord`; the actual reported name was `upsertAdvisoryContext`. This supports a working TS retrieval path for that example and non-monotonic answer quality as top-k grows; context competition versus incomplete coverage versus synthesis remains to be isolated.

- **Several old scalability findings are fixed; material ingestion costs remain.** Graph persistence now uses bulk inserts, one transaction/advisory lock, and an in-memory endpoint map; embedding and vector HTTP requests are batched, and an HNSW migration exists. However, every ingestion still rebuilds/re-embeds the repository, materializes all chunks/embeddings/records in memory, and starts an unrestricted daemon thread; vector persistence still executes one INSERT per row. These costs are visible, but their production dominance is unmeasured. Sources: [persist_graph](../../ingestion_service/src/core/codebase/codebase_persistence.py#L79), [_background_ingest_repo / ingest_repo](../../ingestion_service/src/api/v1/codebase_ingest.py#L141), [embed_and_persist_batch](../../ingestion_service/src/core/pipeline.py#L187), [persist_batch](../../ingestion_service/src/core/http_vectorstore.py#L71), [PgVectorStore.add](../../vector_store_service/src/core/vectorstore/pgvector_store.py#L43), [index migration](../../migrations/versions/20260718_add_vector_chunk_indexes.py).

- **Query scalability and freshness remain coupled to whole-graph loading.** A cold query synchronously downloads the full graph into an unbounded process-local cache; no production caller requests reload, and no TTL/version invalidation exists. Query embedding and vector-service database operations also block inside async request paths. The repo path's document fetches are already bounded-concurrent (default eight), but the simple-document path still fetches serially. Sources: [get_cached_graph](../../rag_orchestrator/src/retrieval/codebase_utils.py#L167), [get_full_graph_from_api](../../rag_orchestrator/src/retrieval/codebase_queries.py#L226), [run_rag / _fetch_expanded_doc_chunks](../../rag_orchestrator/src/core/service.py), [vector routes](../../vector_store_service/src/api/v1/vectors.py), [run_simple_rag](../../rag_orchestrator/src/core/simple_service.py#L49).

- **Important documentation mismatches concern behavior, not OKF organization.** [CLAUDE.md](../../CLAUDE.md) says artifact embeddings are not sub-chunks and calls simple RAG flat; the ingestion and simple-query functions above contradict both. [ADR-048's query-time section](../adr/ADR-048-Cross-Artifact-Linking.md) describes automatic DOCUMENTS traversal absent from the selector. The [query diagram](../architecture/Repo-query-ascii-flow-diagram.md) still shows `k=10` expanded fetches and a ranking stage in `execute_retrieval_plan()`, which explicitly has none. The [roadmap's WP-S8 row](07-Roadmap.md) bundles concurrent fetch as future work although repo retrieval already has it. Proposed ADR-045 and explicitly superseded audit snapshots remain historical records; wikilinks, front matter, and MOCs are intentional organization, not defects.

## 2. Most important confirmed problem

**Useful graph-discovered evidence is discarded before its content can influence selection.**

The decisive loss occurs in [hybrid_retrieve](../../rag_orchestrator/src/core/service.py#L326): mapped, deduplicated expanded documents are sliced to `MAX_EXPANDED_DOCS` before `/search-by-doc`. Within equal strategy/seed-hit groups, [execute_traversals_from_seeds](../../rag_orchestrator/src/retrieval/traversal_selector.py#L249) orders alphabetically. Query wording selects a strategy, but target relevance does not break these ties. Thus broad modules and overlapping seed neighborhoods can crowd out exact helpers. Improving the generator cannot recover passages never supplied.

This is a **context-selection failure after successful graph discovery**, not evidence that vector search or edge resolution failed. The existing [same-relation fixture](../../rag_orchestrator/tests/test_evidence_survival.py#L142) intentionally preserves this failure. Running the current ranking definitions in memory again placed three helpers at zero-based ranks 25–27, outside 20. The user's confirmed example and the historical rank-88 live target support a broader structural risk; its frequency is still unknown.

The relation-priority fix is meaningful but incomplete. The historical live report also records evaluation-document contamination. Its ranking/fetch observations remain useful; its “final context” flags require qualification because current tracing precedes text-budget truncation. Neither those flags nor the answer grades establish clean passage-level recall. Investigation 1 therefore measures the actual LLM payload.

The supplied TypeScript broad/narrow comparison is a separate failure shape: apparently available code can still be poorly used. It strengthens the need for a generation control, not the claim that every failure comes from the expansion cap.

The production spot-check independently confirms that surviving the document cap is insufficient: the three-row fetch can omit the required passage. It does not measure how often either loss occurs in complete production queries.

## 3. Three next investigations

### 1. Where does discovered evidence actually disappear?

**Hypothesis:** Same-priority cap competition recurs, but broader questions can also fail through passage loss or distractor-sensitive synthesis after successful retrieval.

**Experiment:** Use eight fresh known-answer questions across two repositories, including long functions and successful controls; withhold answer-bearing evaluation/audit material from the corpus. Pin runtime revision and ingested source snapshot separately. Include paired broad/narrow TS questions at top-k 5 and 10, using actual symbol names and fixed Qwen3:4b. Capture `/generate` context and target chunk IDs at each stage. For cap losses, compare cap 20 versus 40 with seeds/context budget fixed. For apparent synthesis failures, replay sufficient implementation passages alone and with original distractors, holding query/model fixed and repeating to check variability.

**Measurement:** Raw/post-dedup seed rank, graph rank/path, mapping failures, mapped-document rank, fetched chunk indices, each truncation stage, exact passage presence, required-symbol coverage, distractor share, answer correctness/refusal, actual model/fallback, latency, and context size.

**Decision gate:** Repeated loss at one stage on at least two independent questions supports a focused selection/fetch change when supplying the missing passage recovers answers. Repeated clean-context success but noisy-context failure supports context-selection/prompt work; failure with sufficient clean context supports generation/model investigation. Neither higher top-k nor a higher cap is automatically an improvement.

### 2. When does graph traversal add evidence beyond vector seeds?

**Hypothesis:** Expansion helps structural questions but misses some through seed coverage, direction/intent selection, or unused DOCUMENTS edges; these mechanisms differ from cap loss.

**Experiment:** Reuse the uncontaminated questions with identical seeds and budgets: compare vector-only versus current graph expansion. For misses, inspect persisted artifacts/edges and replay only the expected traversal with caps removed from the diagnostic. Use a forced correct seed to isolate seed retrieval from traversal; for remaining seed misses, compare stored passage text with the actual 800-character embedding input.

**Measurement:** Incremental exact-passage recall and answer correctness, distractor/context cost, expected versus resolved edges (including EXTERNAL_SYMBOL endpoints), chosen direction/anchors, reachability before selection, and omitted embedding text. Check artifact existence first: unsupported files such as YAML/config have no extractor in [EXTRACTORS](../../ingestion_service/src/core/codebase/repo_graph_builder.py#L34).

**Decision gate:** An existing correct edge that repeatedly recovers targets only under the forced traversal supports a narrow routing/traversal change. Missing artifacts/edges support ingestion/resolution work; correct artifacts missed only at seeding support a retrieval experiment. Expansion volume alone justifies none of these.

### 3. Which remaining scaling cost matters at the actual workload?

**Hypothesis:** Full re-ingestion and full-graph cache loading dominate growth or freshness problems before another storage architecture becomes necessary.

**Experiment:** On an isolated copy, compare one representative repository and a roughly twice-sized sample: initial versus unchanged re-ingestion, cold versus warm queries, and one versus four concurrent queries. Then change one known edge and re-ingest under the same repo ID; compare the existing worker with a fresh worker. Record deployed index presence/query plans instead of assuming migrations ran.

**Measurement:** Extraction, graph persistence, embedding, vector INSERT, graph export/load, and fetch timings; peak memory, chunk/vector counts, SQL statement counts, query latency, and whether the changed edge appears. Distinguish graph-cache staleness from the interval between graph replacement and completed embedding.

**Decision gate:** Prioritize the measured dominant stage if it breaches a predeclared latency/memory target or produces repeatable stale evidence. Unchanged full re-embedding dominating cost supports incremental-ingestion work; graph loading or stale cache results support bounded loading/invalidation; row INSERT cost dominating supports batching there. No measured breach means defer infrastructure changes.

## 4. Explicitly defer

- **A reranker:** First establish which candidate stage loses evidence; a reranker after fetching cannot recover documents discarded before fetching.
- **Hybrid lexical search or a new embedding model:** Separate missing artifacts, truncated embedding input, and genuine seed-ranking misses before replacing retrieval components.
- **A graph database:** Existing edges are already discovered in the primary failure; graph storage is not yet the demonstrated cause.
- **An LLM retrieval router or LangGraph-style supervisor:** Test the specific deterministic traversal gaps before adding orchestration complexity.
- **A larger context window or blanket cap increase:** Use them only as diagnostic controls until passage survival, distractor cost, and answer quality are measured together.
