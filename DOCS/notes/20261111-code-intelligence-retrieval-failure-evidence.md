---
title: "Code intelligence retrieval failure: evidence from 2026-11-11"
date: 2026-11-11
created: 2026-11-11
type: working-note
status: raw
scope: rag-foundry-universal
source: "Issue #342. Owner live tests (Gradio and /v1/rag), owner-supplied DeepWiki answers, Codex read-only inspection and ChatGPT analysis, plus Claude Code live queries, read-only SQL and exact similarity ranking on 2026-11-11"
authority: "Raw capture of evidence and open questions; not a decision, ADR or roadmap change"
verification_status: "Findings marked Confirmed were measured on the Linux stack on 2026-11-11; items marked Hypothesis or Reported were not"
tags:
  - code-intelligence
  - retrieval
  - evidence-survival
  - lightrag
  - investigation
related:
  - "[Code intelligence outlook](/DOCS/notes/20261110-code-intelligence-outlook-and-portability-goals.md)"
  - "[November 10 code intelligence audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[ADR-045 hybrid vector + graph RAG](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md)"
  - "[ADR-056 embedding-input contract](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
  - "[Current project status](/DOCS/status.md)"
---

# Code intelligence retrieval failure: evidence from 2026-11-11

Tracked by issue #342.

> [!warning] Raw note
> This note records what was tested and learned on 2026-11-11, before any
> decision. The owner's conclusion at the end of the day was that a run of
> fixes, each followed by another failure, means the code intelligence
> strategy needs rethinking, not one more patch.

## 1. Summary

- `/v1/rag` failed three implementation questions in one day, on two
  different repos: our own repo twice, and HKUDS/LightRAG.
- **Test 3 rules out dogfooding as the main cause.** LightRAG has none of our
  self-describing docs, and it still failed.
- **The index is not the problem.** The implementation symbols exist, with
  vectors.
- **All three later stages fail:**
  1. Seed search: implementation chunks rank in the hundreds to thousands.
  2. Graph expansion: the call that crosses from the API layer into the core is
     not resolved.
  3. Context budget: about 4k tokens, so code that expansion reached is cut.
- **External tools did better.** DeepWiki answered both questions with cited
  implementation code. It was imperfect but far better. Codex (read-only)
  confirmed that the `/v1/rag` path has no step that routes by code anchor or
  question type.

## 2. Tests run

### Test 1: self-repo endpoint trace (owner, deployed stack; Reported)

- **Question:** trace `POST /v1/rag` through the orchestrator service layer to
  vector retrieval. It asked for implementation code.
- **Corpus:** repo `f7641840`, ingested 2026-10-29. The release was built
  2026-11-11.
- **Result:** 5 seeds (4 markdown sections and 1 service-topology test file).
  The final context held 4 documentation chunks and 0 implementation chunks.
  The model correctly said it had too little evidence.
- **Expected path** (DeepWiki, cited):
  `routes.py#rag_endpoint` → `service.py#run_rag` → `service.py#hybrid_retrieve`
  → HTTP POST `vector_store_service /v1/vectors/search`.

### Test 2: self-repo ingestion question (owner, Gradio; Reported, screenshot)

- **Settings:** repo `f7641840`, Normal RAG, top-k 5, `ollama/Qwen3:4b`.
- **Question:** "what happens when a small repo is ingested. what are the major
  steps or events".
- **Result:** the model said it had too little evidence.
- **Sources:**
  - `DOCS/audit/01-Codebase-Audit-Findings.md` (a section on scalability)
  - two sections of `DOCS/test_results/2026-10-10-issue-240-source-snapshot-verification.md`
  - `ingestion_service/src/api/v1/repos.py#_delete_repo_sync`
  - `ingestion_service/tests/core/test_repo_lifecycle.py#_make_ingestion`
- **Gap:** none of the ingestion pipeline code (for example the `/v1/ingest-repo`
  handler or `codebase_ingest.py`) reached the context.

### Test 3: LightRAG control (Claude Code, Linux stack; Confirmed)

- **Repo:** `4f76a36f-caf8-5532-9ee2-977ec412ed6c`, generation `128c494e`,
  77,625 chunks, ingested 2026-10-13. This predates ADR-056.
- **Purpose:** proposed by ChatGPT, to test whether the self-repo failure is
  caused by doc crowding.

| Run | Query | Seeds | Final context | Answer |
|---|---|---|---|---|
| Long | ChatGPT's wording, including "base the answer on implementation code, not documentation or test reports" | `examples/lightrag_ag2_multiagent_demo.py` (2), `reproduce/Step_3.py`, two test files | 3 seeds, 1 test helper, `lightrag/base.py#QueryContextResult` | Said it lacked evidence |
| Short | "Trace how LightRAG processes a query from its API entry point to vector retrieval. Identify the functions and source files involved." | 3 chunks from the example demo, `reproduce/Step_3.py`, `reproduce/Step_3_openai_compatible.py` | Seeds only | **Confidently wrong:** named the example script's `lightrag_query` as the API entry point |

**Expected path,** from DeepWiki with citations (verified against
LightRAG source):

1. `query_routes.py#query_text`, inside `create_query_routes`.
2. → `rag.aquery_llm(...)`.
3. → `operate.py#extract_keywords_only`. This is an LLM call.
4. → `operate.py#_perform_kg_search`. This is a batch embedding call.
5. → `operate.py#_get_vector_context`.
6. → `chunks_vdb.query(...)`, defined on `BaseVectorStorage`. Backends are
   local (Nano, Faiss) or remote (PG, Milvus, Qdrant).

DeepWiki also said it lacked the bodies of `aquery_llm`, `kg_query` and
`naive_query`.

Before this answer arrived, Claude's own expected list had `query_text →
LightRAG.aquery → kg_query/naive_query`. That was partly wrong: the route calls
`aquery_llm`, and the list missed the three helpers in steps 3–5.

## 3. Confirmed findings (LightRAG)

### F1. Indexing is fine

The implementation symbols all exist as `python source` nodes with vectors:
`query_text`, `create_query_routes`, `LightRAG.aquery`, `aquery_llm`,
`kg_query`, `naive_query`, `_perform_kg_search`, `_get_vector_context` and
`extract_keywords_only`.

### F2. The seed search cannot reach the implementation

**Method:** exact cosine ranking over all 77,625 chunks for the short query,
using `mxbai-embed-large`, the raw query and no prefix. This matches
`embed_query`.

Best-ranked chunk per expected symbol:

| Symbol | Best rank | Similarity |
|---|---|---|
| `_perform_kg_search` | 329 | 0.687 |
| `create_query_routes` | 668 | 0.671 |
| `_get_vector_context` | 1,165 | 0.657 |
| `naive_query` | 1,299 | 0.654 |
| `aquery_llm` | 2,356 | 0.634 |
| `kg_query` | 2,606 | 0.630 |
| `query_text` | 2,924 | 0.626 |
| `LightRAG.aquery` | 5,375 | 0.605 |
| `extract_keywords_only` | 7,861 | 0.590 |

The top 25 (similarity 0.734–0.769) are:

- example scripts (`examples/...`)
- reproduction scripts (`reproduce/Step_3*.py`)
- test files
- 9 markdown sections, including `docs/Reproduce.md`, READMEs and
  evaluation sample docs
- a few library files such as `lightrag/operate.py`, the module-level chunk, at
  rank 8

The 25th result has similarity 0.734. The best implementation chunk has 0.687.
That is a gap of about 0.05 between example, test and doc code and the library
code.

**What this rules out:**
- `top_k` is 5. `DOC_TYPE_TIE_BREAK_ENABLED`, which is off by default, would
  look at only 100 candidates within a 0.03 band. No filter or tie-break tweak
  reaches rank 329 or worse.
- A perfect code-only filter would still return the example and reproduction
  scripts, because they are `python source` too.

### F3. The #64 fix closed the bug, not the intent

- #64 was fixed in PR #72 (`8fdbd20`). `hybrid_retrieve` now filters on
  `source_type="code"`.
- But codebase ingestion chunks every node with
  `pipeline._chunk(node.text, "code", ...)`:
  `ingestion_service/src/api/v1/codebase_ingest.py:104` and
  `ingestion_service/src/core/pipeline.py:293`.
- So every chunk in a code repo, markdown included, has `source_type=code`.
  In LightRAG: 64,276 python, 7,636 markdown_section, 3,891 typescript and
  1,816 markdown_module chunks, all `code`.
- The "code-only seed search" in ADR-045 is therefore a search over every
  artifact in the repo.
- This is real, but it is not the main cause (see F2).

### F4. Graph expansion breaks at the boundary that matters

- **API layer to core:** `query_text` CALL → `EXTERNAL_SYMBOL:rag.aquery_llm`.
  `rag` is a function parameter, so the callee is not resolved to
  `lightrag/lightrag.py#LightRAG.aquery_llm`.
- **Example scripts to core:** `examples/...#lightrag_query` CALL →
  `EXTERNAL_SYMBOL:_rag_instance.aquery`. Starting from the seeds that did win,
  expansion cannot reach the library.
- **Inside a module, edges do resolve,** for example:
  - `LightRAG.aquery_llm` → `operate.py#kg_query`
  - `_perform_kg_search` → `_get_vector_context`
- **Repo-wide,** 50,875 of 74,271 CALL edges (69%) end at `EXTERNAL_SYMBOL`
  placeholders.
- **These placeholders crowd out real nodes.** They took 43 of 61 (short) and
  90 of 126 (long) expanded IDs.

### F5. Evidence that expansion found is cut by the budget

- In the long run, expansion did reach `operate.py#kg_query`, `naive_query` and
  `query_routes.py#create_query_routes` (through test-file seeds). None of them
  reached the final context.
- `context_budget` = 4,096 tokens. The budget step cut the long run from
  37,091 to 4,027 tokens and the short run from 26,053 to 3,950. The 5 seeds
  alone fill most of it.
- One implementation function is enough to blow the budget: `kg_query` is
  11,576 characters and `create_query_routes` is 64,208. Token counts use a
  conservative UTF-8 byte estimate.

### F6. Generation guard

- The long run declined correctly.
- The short run did not decline. It answered from example code as if it were
  the implementation. The evidence-sufficiency work (#200) did not catch an
  answer built on the wrong kind of evidence.

## 4. External comparisons (Reported)

- **DeepWiki:**
  - Answered both trace questions with file and line citations to
    implementation code.
  - For our repo, it partly reconstructed `hybrid_retrieve` from old
    evaluation docs.
  - For LightRAG, it lacked the bodies of `aquery_llm`, `kg_query` and
    `naive_query`, and said so.
  - It is imperfect but substantially better. One example each is not proof
    that its whole architecture is better.
- **Codex** (read-only, Linux, 2026-11-11):
  - No early step classifies the question as being about implementation
    behavior.
  - The pipeline is: resolve repo → embed → vector search → keyword-rule
    traversal (`traversal_selector.py:64`) → assemble context → LLM
    (`service.py` around line 1236).
  - The code-preference tie-break is off by default (`config.py:35`).
  - Explicit-symbol promotion only applies to methods found during expansion.
  - `claim_type` is set by the caller, never inferred from the question.
  - Symbol-based trace endpoints exist but are not wired into `/v1/rag`.

## 5. Pattern across past fixes

**Owner's observation:** each simple fix was followed by another failure.
Known instances:

| Issue | Change | Outcome |
|---|---|---|
| #64 | Dead `doc_type="code"` seed filter fixed (#72) | The replacement filter does not separate docs from code (F3) |
| #141/#142 | Doc-type tie-break built | Shipped off by default. A 100-candidate pool cannot reach implementation ranked 300+ (F2) |
| #89/#91 | Expanded-doc truncation and ranking fixes | Expansion still loses to the budget (F5) |
| WP-L5 | Explicit-mention promotion | Only applies once expansion reaches the symbol |
| #200/#199 | Evidence sufficiency and provenance | Abstention works, but a wrong-evidence answer still passes (F6) |

**Related earlier signal:** the E1 feasibility work (2026-10-21) found that
chunk granularity, not the seed cap, limited code-evidence retrieval.

**Common thread:** each fix tuned a stage downstream of a seed step built on
pure semantic similarity. That step does not put implementation code anywhere
near the top for "how does X work / trace X" questions.

## 6. Hypotheses for the rethink (not decisions)

- **H1. Similarity is the wrong first step for code questions.** A natural
  language question is closer, in embedding space, to code that *uses* an API
  (examples, tests, reproduction scripts) and to prose about it than to the
  implementation. Supported by F2 on LightRAG; not yet tested more widely.
- **H2. Resolve structural anchors first.** When a question names an endpoint,
  route, symbol, class or file, resolve it through the graph or symbol inventory
  before vector search, and pin it as primary evidence. Even "API entry point"
  can map to route nodes: the graph has `route` doc_types (18 in LightRAG).
  Codex says the symbol and trace machinery already exists.
- **H3. Classify files by role.** Distinguish library code from examples,
  tests, reproduction scripts, docs and generated files, and use that role in
  ranking and budgeting. Today `doc_type` only says "python source" for all of
  them.
- **H4. Resolve calls through receivers.** Calls on parameters and instance
  attributes (`rag.aquery_llm`, `_rag_instance.aquery`) need resolution through
  type hints, constructor assignment or a unique-method-name fallback.
  Otherwise the graph cannot cross module boundaries.
- **H5. The budget is too small for code.** 4,096 tokens holds about one
  medium function. Code questions may need excerpts (signature plus the
  relevant call lines), a larger window, or a budget that pins
  anchor-resolved evidence before adding seeds.
- **H6. Ask what DeepWiki does differently.** It likely uses lexical
  identifier matching or wiki pages built from code structure. This deserves a
  look before designing anything new.
- **H7. Corpus freshness is secondary.** Both corpora predate ADR-056 and the
  Nov 11 release. Re-ingesting is unlikely to change F2–F5, but this is untested.

## 7. Proposed acceptance criterion (from the ChatGPT analysis, owner-endorsed direction)

> Given a query that explicitly identifies an endpoint, class or function, or
> asks how a named capability is implemented, the system must locate the
> implementing code and use it as primary evidence, or state precisely why it
> cannot.

Check it at three boundaries:
1. Is the implementation in the index?
2. Does retrieval resolve the anchor?
3. Does the implementation survive into the final context?

On 2026-11-11: (1) passed, (2) failed, (3) failed.

## 8. Open questions

- Does the same failure occur on Rust, TypeScript and Java repos, and on the
  held-out E1 corpora (hatch, pdfminer.six, werkzeug)?
- How much of the existing symbol and trace machinery could serve as an anchor
  resolver without a new LLM call?
- Should code questions and document questions keep sharing one retrieval
  path?
- Should the evaluation set add "trace X" and "how does X work" questions with
  expected symbol paths, alongside the frozen E1 questions?

## 9. Raw evidence

Raw evidence is in `DOCS/test_results/_raw/20261111-code-intelligence-control/`
(git-ignored), indexed in [raw-index.json](/DOCS/test_results/raw-index.json).
It contains:
- both LightRAG `/v1/rag` responses
- the similarity-rank output
- the read-only SQL and probe scripts. The host is read from the git-ignored
  `.env` and never written down.
