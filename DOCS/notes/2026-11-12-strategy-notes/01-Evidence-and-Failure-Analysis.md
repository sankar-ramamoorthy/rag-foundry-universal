---
title: "November 11 Code-Intelligence Failures — Evidence and Limitations"
date: 2026-11-12
type: diagnostic-synthesis
status: raw
project: RAG-FOUNDRY-UNIVERSAL
tags: [code-intelligence, evidence, retrieval, failure-analysis, regression]
aliases: ["Retrieval Failure Evidence Summary"]
authority: "Synthesis of pasted live responses and reported Claude investigation; some measurements not independently reproduced"
related: ["[[00-Strategy-Discussion-Index]]", "[[04-Metadata-and-Evidence-Authority]]", "[[08-Experiments-Gates-and-Open-Decisions]]"]
---
# Evidence and Failure Analysis

## Provenance discipline

- **Directly supplied live response:** November 11 `/v1/rag` smoke and implementation-trace JSON pasted from the Linux deployment.
- **Reported analysis:** Claude's Windows-side LightRAG controls, SQL/rank probes, and note summary; raw rank scripts and captures were reported in a git-ignored folder, not independently executed for this document.
- **External comparison:** User-provided DeepWiki answers with implementation excerpts. Useful *reference candidates*, not independently established ground truth for all call edges.
- **Discussion hypothesis:** Architectural explanations below are not automatically proven by a failed answer.

## Production context

- Reported deployed image SHA: `8bc0ed224b92b4f1b11a0542956b71a3ae22bb04`.
- Six project stack containers eventually became healthy after `prod-refresh.sh --deploy` initially exited because ingestion was unhealthy; migrations already at `20261030_vc_idempotent_key (head)`.
- The production repository database persisted despite `docker compose down -v`; this is consistent with a surviving bind mount. This does not by itself certify vector/graph consistency.
- Self-repo ID: `f7641840-ba13-5f9d-9ae6-87e1f924709d`; ingested October 29, generation/ingestion ID `e423d1bb-e1d3-4d71-8200-3826c5987c95`.
- LightRAG repo ID: `4f76a36f-caf8-5532-9ee2-977ec412ed6c`; ingested October 13, generation ID `128c494e-0aae-4e1d-81d0-b7e52f2006b1`.
- Production release script did not finish a successful `--deploy` verification pass; a later healthy state and query success are evidence of operational recovery, **not proof that its generated release record says complete**.

## Three diagnostic scenarios (four LightRAG executions counted separately)

### Case A — Self-repo smoke question (basic PASS)

Prompt: `What service handles RAG queries, and what downstream services does it call?`

- Answer correctly identified the orchestrator, vector store and LLM services.
- Seed documents: 5. Graph expansion candidates: 7. Final context: 8 chunks; approximately 4,067/4,096 estimated tokens.
- Seven of the eight final-context chunks came from old reports/release documentation; only one implementation chunk. Graph expansion executed but added no final-context chunks.
- Conclusion: the service path works, but a correct answer with historical evidence is not proof of implementation-tracing capability.

### Case B — Self-repo endpoint trace (FAIL)

Prompt: `Trace the execution path from the POST /v1/rag endpoint through the orchestrator service layer to vector retrieval. Identify the actual Python functions and files involved, explain the call sequence, and distinguish direct function calls from HTTP service calls. Base the answer on implementation code rather than documentation or historical test reports.`

- Answer abstained for insufficient evidence.
- Seeds: four documentation sections and one service-topology test file, not the requested production endpoint.
- Graph expansion: 12 candidates; two expanded document IDs derived by `CALL` from the test-file seed.
- Final context: 4 chunks, all historical documentation; token estimate reduced from 10,752 to 3,982 against a 4,096-token budget.
- The model's abstention was appropriate given that context; the retrieval/evidence-delivery path failed the task.
- User-supplied DeepWiki reference identified: `rag_endpoint` → `run_rag` → `hybrid_retrieve` → HTTP vector search, but partially inferred internals from evaluation notes rather than direct full source.

### Case C — Self-repo ingestion lifecycle question (FAIL)

Question seen in Gradio screenshot: what happens when a small repository is ingested; identify the major steps/events. The screenshot reportedly showed a non-answer using audit/test material; **a full corresponding JSON retrieval plan was not supplied**. Do not assign it a verified failure stage or invented numerical metrics. This question is key because it is a broad workflow question **without an exact symbol anchor**.

### Case D — LightRAG control (two variants; both FAIL per Claude)

Long prompt: `Trace how LightRAG processes a query from its API entry point through the core query-processing functions to vector retrieval. Identify the actual functions, classes, and source files involved. Explain the execution sequence and distinguish direct Python calls from external service calls. Base the answer primarily on implementation code, not documentation or test reports.`

A shorter wording was also tested; exact shorter prompt should be recovered from Claude's raw capture before using it in formal evaluation.

Reported findings:

- Full corpus contained **77,625 vector chunks** in a single reported generation.
- Query-related implementation symbols were indexed, including `LightRAG.aquery`, `naive_query`, `kg_query`, `create_query_routes`, and `query_text`.
- Claude later reported that functions in the DeepWiki reference answer ranked **329–7,861** among all chunks. Earlier intermediate figures included `create_query_routes` 668, `naive_query` 1,299, `kg_query` 2,606, `LightRAG.aquery` 5,375. These are reported rank-probe results, not numbers independently reproduced here; rankings depend on the precise query and method.
- Many of the leading candidates were example scripts, tests and Markdown.
- In short query expansion, 43/61 expanded canonical IDs were external-symbol placeholders; Claude reported a similar high share for the longer query. **Do not conflate this request-specific proportion with the separately reported 69% repo-wide unresolved call links without checking denominators.**
- In the longer run, useful code reportedly appeared during expansion but did not survive the final ~4,096-token context budget (about 37k before allocation).
- Long-answer model abstained; short-answer model reportedly misidentified an example script as API entry point.
- DeepWiki offered a useful trace through `query_text`, `aquery_llm`, keyword extraction, `_perform_kg_search`, `_get_vector_context`, and `chunks_vdb.query`, but explicitly noted missing bodies for some intermediate dispatch steps.

## Failure taxonomy

| Boundary | What is observed | What is not yet proven |
| --- | --- | --- |
| Index presence | LightRAG target code reportedly indexed | Completeness/freshness of every canonical relation |
| Seed discovery | Correct code ranks far below top-k | Whether lexical/structural discovery fully solves issue |
| Source classification | Source-type filter admits markdown from codebase ingestion | Correctness of every repo/language metadata field |
| Graph expansion | Some paths terminate at unresolved placeholders | How many important bug paths are practically affected |
| Evidence survival | Useful expanded code reportedly lost to budgeting | Best allocation policy and safe budget increase |
| Generation | Different deployment and corpus dates | Whether new re-ingestion changes any given outcome |
| Generation quality | Qwen3:4b abstains or makes errors under bad context | Performance with verified full evidence supplied directly |

## Crucial cautions

A graph engine replacement does not resolve extraction gaps, poor seed ranking, or evidence truncation. A better generation model cannot consume code absent from final context. A reranker cannot find an implementation outside its candidate pool. A metadata-only change cannot automatically resolve example-vs-library competition.

See [[04-Metadata-and-Evidence-Authority]] for the `source_type` issue and [[08-Experiments-Gates-and-Open-Decisions]] for the reproducible baseline requirements.
