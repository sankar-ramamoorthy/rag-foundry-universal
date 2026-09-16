---
title: "Repository architecture audit: ingestion, retrieval, reranking, and operations"
date: 2026-09-16
type: audit
status: complete
source_commit: 308f0ac068fb0a8bdbb30ceba34cc6777abfb304
tags: [audit, architecture, ingestion, retrieval, reranking, production]
related:
  - "[September 7 retrieval audit](./2026-09-07-current-state-retrieval-audit.md)"
  - "[September 7 architecture audit](./2026-09-07-repository-intelligence-architecture-audit.md)"
  - "[Memory design review](./2026-09-16-bounded-ingestion-memory-design-review.md)"
  - "[Audit overview](./00-Audit-Overview.md)"
  - "[Production release record](/DOCS/releases/2026-09-12-prod-release.md)"
---

# Verdict and scope

**The graph-aware architecture remains a reasonable foundation, but this checkout is not ready for reliable large-repository production use.** The highest priority remains bounded ingestion memory. However, the four-item priority chain understates ingestion/deletion consistency, graph-cache freshness, and healthcheck defects. These affect whether production serves a coherent corpus and whether operators can trust its state.

The memory proposal is directionally sound but needs amendments before implementation. Its node-page tests do not establish bounded chunk memory; its retry guarantee requires mechanisms not planned. See the [separate task-level review](./2026-09-16-bounded-ingestion-memory-design-review.md).

Scope: repository and document ingestion, graph persistence/lifecycle, vector retrieval, graph expansion, passage fetching, context assembly/provenance, optional reranking, generation boundary, and production Compose/release evidence. This is an architecture and critical-path audit, not an exhaustive security assessment or a new semantic-parity certification of every language extractor.

Evidence labels used below: **source** means traced through current code; **probe** means reproduced locally with selected actual definitions and controlled inputs; **live HTTP** means read-only production API checks; **recorded** means prior evidence or the owner's brief, not reproduced here. The checkout was clean at start. Only this audit, its design-review companion, and its reproduction script were created. No application code, configuration, issues, PRs, or production data were changed.

Production is the owner's Linux/GTX 1080 Ti machine at the previously documented Tailscale address, with no SSH available. Container/image IDs, memory limits, OOM flags, extension version, and actual runtime SHA could not be inspected through the available HTTP surface. GitHub CLI issue/PR queries returned 401; browser requests could not retrieve #160/#164. Remote issue status is consequently unverified.

## Changes since September 7

There has been substantial useful work; the earlier report should not be repeated as if nothing changed.

| Area | Current evidence | Remaining limit |
| --- | --- | --- |
| Evidence tracing | WP-T1 now distinguishes chunk limits from budget survival and adds a final-context manifest | Incorrect chunk ordinals and pre-budget source lists remain |
| Canonical lookup | POST body replaces oversized GET query strings | Lookup/fetch errors still degrade into missing evidence without a structured degraded-result contract |
| Filtered vector search | Iterative HNSW scans added; prior report records restored result counts | Returned counts do not prove exact-neighbor recall; relaxed ordering conflicts with downstream assumptions |
| Reranker | Optional implementation, request override, six local unit tests passing | Already tested live in a contaminated evaluation; no general quality benefit established |
| Language extraction | Rust, Java, and Python tree-sitter support present with fixtures/fallback work | Language support is not proof of complete repository semantics or TRACE/IMPACT correctness |
| Deployment | Production override, OCI labels, refresh script, and a successful September 12 release record exist | Current revision not observable by HTTP; malformed inherited healthchecks and startup dependency synchronization remain |
| Deletion | API and Gradio path implemented | Retry cleanup, concurrency, historical identity, and event-loop blocking need attention |

The brief's wording that a first clean deployment is still entirely outstanding needs qualification: the [September 12 record](/DOCS/releases/2026-09-12-prod-release.md) documents successful image provenance, health checks, corpus preservation, and an existing-corpus RAG smoke test. It explicitly did not perform fresh ingestion, and predates deletion. A **current-release ingest/query/delete/redeploy validation** remains outstanding; the earlier successful release should still receive credit.

Similarly, [DOCS/status.md](/DOCS/status.md) says reranking has not been evaluated live, but the [September 15 run](/DOCS/test_results/2026-09-15-wp-s8-rerank-evidence-survival-run.md) records 16 on/off calls. Correct description: plumbing exercised live, quality conclusion blocked by contamination and limited clean cases.

## Findings by priority

### A1 — High: ingestion working memory and concurrency remain unbounded

**Source; recorded incident.** [_embed_repo_artifacts](/ingestion_service/src/api/v1/codebase_ingest.py#L79) accumulates whole-repository chunks, [OllamaEmbedder](/shared/embedders/ollama.py#L47) accumulates embeddings, and [HttpVectorStore](/ingestion_service/src/core/http_vectorstore.py#L71) builds records before any persistence. Each ingestion creates a daemon thread without admission control. The supplied DocsGPT incident establishes the production consequence: graph persisted, zero vectors, OOM kill. This audit confirms the code mechanism but does not claim allocation profiling or independently reverify the supplied 44,884-node incident counts.

The proposed node-page loop must also bound chunk counts/bytes, explicitly end graph ownership, preserve chunk ordinals, and bind reads to an ingestion attempt. A single 128,000-character node produced **143 chunks** in the local probe. Memory scales with concurrent active jobs as well as the per-job working set.

**Action:** amend and implement #160 as detailed in the companion review. Add a bounded admission policy for the current deployment. Do not claim this also bounds graph construction or uploaded-document conversion: [file ingestion](/ingestion_service/src/api/v1/ingest.py#L338) reads the entire upload and starts another daemon thread; PDF conversion and `run_with_chunks` retain whole-document state.

### A2 — High: job recovery and corpus publication are incomplete

**Source; orphan incident recorded.** [StatusManager](/ingestion_service/src/core/status_manager.py) transitions only from the worker's execution path; [startup](/ingestion_service/src/api/v1/main.py) performs no reconciliation. Hard death can strand `running`; death between accepting a job and starting its thread can strand `accepted`. Pipeline construction for file ingestion and initial status transitions also happen outside parts of the worker's protected block.

The [graph replacement transaction](/ingestion_service/src/core/codebase/codebase_persistence.py#L79) is atomic only for graph persistence. It deletes old nodes and cascaded vectors before new embedding completes. A failed rebuild can therefore remove a previously usable corpus. Its advisory lock ends at graph commit: it does not serialize the complete graph/embed/status operation with other ingestions or deletion.

**Action:** keep #161 separate from #160, but address both before ordinary large-repo operation. A startup reconciliation policy is reasonable for one exclusive worker process: mark abandoned accepted/running attempts interrupted/failed before accepting new work, retaining the reason and counts. Do not apply blanket reconciliation to a shared database with other live workers; that needs ownership/leases. Add finite embedding timeouts—the current `requests.post` to Ollama has none.

Define serving behavior explicitly: for the MVP, serialize changes and return an explicit unavailable/building state during destructive rebuilds. If production must preserve availability through failed re-ingestion, introduce staging generations and an atomic active-generation switch. That is a distinct consistency feature, not an implicit property of bounded batching.

### A3 — High: deletion can report no work while cleanup remains incomplete

**Source + fault-injection probe.** [list_ingestion_ids_for_repo](/ingestion_service/src/core/db_utils.py#L186) obtains IDs solely from current `document_nodes`. Despite its docstring, that cannot enumerate every historical ingestion: graph replacement deletes previous nodes. It also cannot discover an attempt that failed before creating nodes.

[delete_repo](/ingestion_service/src/api/v1/repos.py#L89) commits node deletion before deleting ingestion requests. If the latter fails or the process dies between these steps, retry has no nodes from which to recover ingestion IDs. The actual route, run with controlled fake persistence, returned `not_found` while the request still existed. This refutes its stated complete retry-cleanup guarantee; it does not imply live vector loss was observed in this audit.

Deletion also has no full-operation guard against a still-running ingestion. A worker can persist after enumeration or attempt completion after its request was deleted.

**Action:** promote deletion correctness above the blue UX item. Persist repository-to-attempt identity independently of replaceable graph rows, and retain it until cleanup commits. Where possible, delete graph and request records in one database transaction after idempotent vector cleanup. Coordinate deletion with active workers. Acceptance tests must include failure after graph commit, repeated ingestions, pre-graph failures, and concurrent mutation. The failed-repo dropdown improvement remains secondary.

### A4 — High: passage retrieval and trace identity still lose or misdescribe evidence

**Source + live HTTP + probe.** The [expanded-document cap](/rag_orchestrator/src/core/service.py#L559) still precedes content fetching. [Traversal ranking](/rag_orchestrator/src/retrieval/traversal_selector.py#L312) resolves equal relation-priority/seed-hit candidates by canonical ID. The earlier same-relation overload finding therefore remains structurally applicable; this audit did not rerun the historical rank-88 query.

[get_chunks_by_document_id](/vector_store_service/src/core/vectorstore/pgvector_store.py) still has `LIMIT` without query relevance or `ORDER BY`. The live check below again showed arbitrary/incomplete excerpts. Sorting by index would make fetching reproducible, but only returns a deterministic prefix; it does not solve evidence late in a long artifact. Seed documents are excluded from supplementary expanded-document fetches too, so one matching seed chunk can prevent retrieval of another required passage in the same function.

The newer trace then replaces real stored chunk indices with response positions in [_add_chunks](/rag_orchestrator/src/core/service.py#L306). A returned chunk at stored index 14 becomes trace index 0. Its reported requested indices `range(k)` also describe something the API did not request: the request contains only a limit. `chunk_id` remains useful, but the ordinal fields are not trustworthy source positions.

**Action:** preserve stored ordinals; distinguish fetch position from document position. Introduce a bounded passage-selection contract that can select relevant passages and adjacent source context within a discovered artifact, with explicit completeness/truncation metadata. Treat seed-document supplementation and pre-fetch cap loss as separate cases. Test long functions with the required implementation at the end and dense same-relation neighborhoods.

### A5 — High for document RAG: expanded documents are fetched and then omitted

**Source + local assembly probe.** [run_simple_rag](/rag_orchestrator/src/core/simple_service.py#L234) supplies only `seed_document_ids` as `document_order` to `prepare_chunks_for_agent`, even after the retrieval plan has gained expanded documents and their chunks have been fetched. Preparation iterates only that supplied order. Expanded documents therefore contribute no context. The probe reproduced a fetched expanded document disappearing from assembly.

**Action:** include the ordered expanded-document set in context preparation with a real candidate bound and the same final-payload observability as repository RAG. Verify at the generation payload boundary that a fact available only through document expansion appears. This is an existing defect, not caused by the recent reranker addition.

### A6 — High: source reporting and context budgeting remain inconsistent

**Source + probe.** WP-T1's manifest is a real improvement: it uses the same selected chunk list as context construction. However, repository [sources](/rag_orchestrator/src/core/service.py#L830) and [simple-RAG sources](/rag_orchestrator/src/core/simple_service.py#L291) still come from pre-budget chunks. The probe produced a helper source label with no helper text in the prompt.

[Budgeting](/rag_orchestrator/src/retrieval/agent_adapter.py#L55) counts whitespace-separated words, excludes labels and prompt overhead, and stops at the first non-fitting chunk. It can discard later small relevant chunks even when they would fit; code token counts need not resemble word counts. The manifest establishes what text the orchestrator supplied to `/generate`, not what an external provider retained or whether it was sufficient to answer. With reranking enabled, `survives_chunk_limits` is computed after reranker removal, conflating another selection stage.

**Action:** derive sources from the final selected list, preserve true chunk IDs/ordinals, and make rerank survival separately observable. Use a documented token budget with prompt/output headroom and an explicit oversized-chunk policy. Capture a payload hash and snapshot identity for evaluation. Validate required passage presence, not merely the presence of any chunk from its canonical document.

### A7 — High for freshness: graph cache and ingestion identity lack versions

**Source.** [get_cached_graph](/rag_orchestrator/src/retrieval/codebase_utils.py#L199) keeps whole graphs indefinitely by repo ID. Production calls do not reload them. Re-ingesting the same repo changes database nodes/vector contents but can leave warm workers traversing old edges. Deleting and re-ingesting the same repo also reuses that cache key. This affects answer correctness, not just benchmarking discipline.

[Clone ingestion](/ingestion_service/src/api/v1/codebase_ingest.py#L166) neither accepts a revision nor records the resolved commit. Runtime labels exist on images but not in health/API provenance. The [walker pilot](/DOCS/test_results/2026-09-15-repoprobe-walker-pilot.md) explicitly ingested current master instead of its benchmark pin, so it cannot serve as a fully pinned benchmark despite useful manual drift checks.

**Action:** key/invalidate graph caches by active ingestion generation, impose an eviction bound, and record the resolved source SHA plus ingestion config/extractor/embedder identity. Accept a pinned source ref or prepared snapshot. Ground truth, ingested snapshot, and runtime revision must be recorded independently. A timestamp or repo URL is not a substitute.

### A8 — High for deployment trust: inherited Compose healthchecks are malformed

**Source; live HTTP health separately passed.** [Base Compose](/docker-compose.yml#L45) supplies `CMD-SHELL` followed by separate Python arguments. Docker's shell form expects a shell command; use `CMD` for an argument vector or one correctly quoted shell command. The ingestion check also targets container-local 8002 though it listens on 8000; the LLM check targets 8003 though it listens on 8000. The production override inherits them. These checks cannot establish the intended service health; Python can be invoked without executing the intended probe under shell argument semantics. [Docker healthcheck reference](https://docs.docker.com/reference/compose-file/services/#healthcheck).

The refresh script's external curl checks are useful independent checks, and the earlier release record explicitly acknowledged malformed healthchecks as deferred. That does not make `depends_on: service_healthy` a reliable readiness gate.

**Action:** correct command form and internal ports, then test healthy and deliberately unavailable endpoints in an isolated stack. Keep current-release image provenance, health, UI, ingest/query/delete, and redeploy checks as a release gate. HTTP-only access cannot verify running image digests; operator-provided release evidence remains needed unless a read-only runtime provenance endpoint is added.

### A9 — Medium/high under load: blocking work stalls service event loops

**Source; production pause recorded.** `delete_repo` is async but invokes synchronous HTTP deletion and synchronous database operations directly. Vector API routes similarly execute synchronous psycopg calls. Both RAG paths synchronously embed queries; cold graph loading uses synchronous HTTP and loads a whole graph. Optional reranking loads/predicts synchronously in the same request path.

This establishes an event-loop blocking mechanism behind service-wide pauses. It does **not** identify whether cascade SQL, vector deletion, serialization, or another component dominated the reported two-minute incident. Large deletes should not be dismissed solely as future optimization when they block health and unrelated API handling.

**Action:** offload synchronous operations to a bounded worker/thread executor or use appropriately synchronous route handlers where applicable; combine this with admission control. Measure database delete time separately. Inspect deployed cascade/index query plans before attributing the cost to missing indexes. Broader queue architecture can follow measured need.

## Retrieval and reranking assessment

The effective repository path remains:

```text
query embedding -> vector seeds -> graph candidates -> document cap
 -> limited passage fetch -> per-document/count caps -> optional reranker
 -> word budget -> labeled prompt -> generation
```

A reranker at its current position cannot recover documents removed before fetching, missing passages, or chunks removed by earlier count caps. It is a reordering/trimming experiment over surviving candidates. Keep it off by default pending clean evidence; there is no reason to remove the experimental plumbing solely because it was built early.

The existing on/off comparison also changes retained count from up to 50 to 10. Reduced generation latency cannot be attributed to better ranking without a no-rerank/top-10 control, equal budgets, and stage timing. The recorded contaminated run even lost one surviving implementation target after reranking. Neither that nor one successful clean target establishes broad benefit or harm.

There is a new score-order contract issue: [vector search](/vector_store_service/src/core/vectorstore/pgvector_store.py) uses `relaxed_order`, while [_apply_doc_type_tie_break](/rag_orchestrator/src/core/service.py#L356) assumes descending scores and exits its scan at the first score outside epsilon. Relaxed scans may return out-of-order distances; pgvector documents reordering through a materialized result. Explicitly sort the returned pool or enforce SQL output order before downstream selection. The probe demonstrates the helper failure with an unsorted pool; this audit did not reproduce an actual live HNSW inversion. [pgvector iterative-scan documentation](https://github.com/pgvector/pgvector#iterative-index-scans).

Embedding fidelity deserves measurement before model shopping: [Ollama truncates](/shared/embedders/ollama.py#L13) each input to 800 characters, including queries. The large-artifact chunker emits 1,000-character windows with 100-character overlap, leaving some characters outside every embedding window even though full chunk text is stored. Sentence/paragraph strategies can emit larger-than-target segments too. Measure searchable evidence loss separately from missing stored text. Changing this behavior belongs in an evaluated re-embedding change, not the memory patch.

Generation now has a useful service boundary, model/fallback reporting, versioned grounding prompts, and transient-error retry handling in [llm_client](/llm_service/src/core/llm_client.py). The recorded clean-context failures mean some work may be generation-side; avoid diagnosing every refusal as retrieval. Compare sufficient implementation-only context against the original noisy context with a pinned model/prompt. Provider fallback chains should fit the orchestrator's request deadline, and evaluation records should retain actual model, prompt version, usage, and fallback.

The GTX 1080 Ti does not imply that the cross-encoder uses that GPU. The checked-in orchestrator Compose service has no GPU device reservation. Determine actual execution device and contention before attributing latency to GPU capacity or recommending new hardware.

## Revised priority order and acceptance gates

1. **Ingestion reliability:** corrected #160, explicit admission limits/timeouts, and #161 orphan recovery. Prove complete normalized vector output within a declared memory envelope.
2. **Corpus lifecycle correctness:** serialize ingestion/deletion, repair delete retries, and bind graph cache/reads to an ingestion generation. Decide whether failed re-ingestion may take the previous corpus offline.
3. **Evidence delivery:** passage fetch semantics, true chunk identity, sources matching final prompt, and the simple-RAG expansion defect. Then address same-relation cap selection using clean measured cases.
4. **Reproducible evaluation and release:** pin the source/runtime/ground-truth triple, keep answer-bearing audit/evaluation documents outside the benchmark corpus, correct healthchecks, and verify a current full lifecycle release on Linux.
5. **Conditional improvements:** evaluate reranking with controlled budgets; pursue lexical search, new embeddings, or retrieval loops only when a measured failure identifies the stage they can improve.

Pipeline-factory drift remains secondary. ORIENT/inventory and TRACE/IMPACT remain useful product directions, but require structural contracts and source evidence; more BFS depth alone does not establish them. OCR modernization and a general autonomous retrieval supervisor remain behind current correctness. Postgres plus pgvector and deterministic graph traversal remain adequate architectural choices absent evidence requiring replacement.

## Verification record and limits

Read-only production checks on 2026-09-16 returned HTTP 200 from all four `/health` endpoints and Gradio. The completed-repo listing contained six entries; the current self-repo ingestion was `d4da8274-f2dc-4b66-89fc-684c467c3539` with 6,311 nodes. This differs from the September 12 release's recorded ingestion, demonstrating why its corpus metadata cannot describe the current corpus. Absence of DocsGPT from a completed-only list does not independently prove deletion of all its data.

Bounded canonical lookup followed by passage reads, for self-repo `f7641840-ba13-5f9d-9ae6-87e1f924709d`:

| Artifact | k=3 returned stored indices | Rows at k=100 | Missing implementation observed |
| --- | --- | --- | --- |
| `rag_orchestrator/src/core/service.py#hybrid_retrieve` | 4, 5, 15 | 19 | Expansion-cap assignment present only in larger fetch |
| `rag_orchestrator/src/core/simple_service.py#run_simple_rag` | 14, 0, 1 | 17 | Seed-only `document_order` assignment present only in larger fetch |

All returned rows carried the current ingestion ID above. These requests used lookup/search POSTs with read-only semantics; no generation, embedding, ingestion, deletion, or deployment was triggered. The audit did not download entire graphs or perform load tests.

Local verification:

- `python DOCS/audit/2026-09-16-audit-probes.py`: seven expected behaviors reproduced from current definitions. Covers node/chunk mismatch, source overstatement, simple-RAG assembly loss, wrong trace ordinal, unsorted tie-break input, delete retry loss, and split-artifact ordinal resets.
- `python -m pytest -q rag_orchestrator/tests/test_reranker.py`: **6 passed**; fake-model unit tests, not model/device/quality validation.
- Combined source/context/manifest test collection failed because local Python lacks `requests` and `httpx`; SQLAlchemy and other service dependencies are also unavailable. No dependency installation or full integration suite was attempted. Local Python is 3.13.2; production targets 3.12.

The [probe script](./2026-09-16-audit-probes.py) compiles selected actual functions with controlled collaborators. It is reproducible audit evidence, not a substitute for PostgreSQL transaction tests, service-level payload tests, production memory benchmarks, or clean RAG evaluation.
