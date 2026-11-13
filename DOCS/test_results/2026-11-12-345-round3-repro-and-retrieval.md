---
title: "#345 round 3: cache-controlled reproducibility, and the retrieval candidates for the Step 0 question"
date: 2026-11-12
type: test-result
status: current
tags: [evaluation, inference, retrieval, qwen3, ollama, prompt-cache, issue-345, issue-342, issue-194]
related:
  - "[Issue #345](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/345)"
  - "[Issue #342](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/342)"
  - "[Issue #194](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/194)"
  - "[Round 2](/DOCS/test_results/2026-11-12-345-round2.md)"
  - "[Inference-side handoff](/DOCS/notes/20261112-inference-baseline-and-provider-capture-handoff.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #345 round 3: reproducibility, and the Step 0 retrieval candidates

This round has two parts, each owner-authorized on 2026-11-12. No
production configuration changed and nothing was re-ingested. All raw
records are in the main checkout's `DOCS/test_results/_raw/`, outside any
worktree, and indexed with sha256 in `raw-index.json`.

## Part 1: cache-controlled reproducibility (inference, #345)

**Design.** One fixed request, byte-identical every time (body sha256
`e6150d31…`): the reviewed implementation context, the `ollama/` body,
`num_ctx` 16,384, seed 11. It is the same request as rounds 1 and 2. It was
sent 7 times under three conditions:

| Condition | How it was produced | Runs |
|---|---|---|
| A, after unload | `POST /api/generate {"model", "keep_alive": 0}` before each run | 3 |
| B, same prompt cached | Sent again immediately after A, with nothing in between | 2 |
| C, after a prefix prime | Preceded by a 1-token request (`num_predict: 1`) with the mixed implementation-first prompt, which shares the implementation prefix | 2 |

Plan: [`round3-repro-plan.json`](/DOCS/evaluations/inference-pilot-345/round3-repro-plan.json).
Each record carries the step index, the preceding step and the `/api/ps`
reading before the call.

**Results.**

| Run | Condition | `/api/ps` before | load s | prompt eval s | completion tokens | answer / thinking sha256 |
|---|---|---|---|---|---|---|
| r3-02 | A (verified unloaded) | empty | 17.4 | 3.18 | 5,203 | `98f39607` / `c81a1eca` |
| r3-04 | A (see note) | loaded | 2.0 | 3.33 | 5,203 | `98f39607` / `c81a1eca` |
| r3-06 | A (see note) | loaded | 2.4 | 3.35 | 5,203 | `98f39607` / `c81a1eca` |
| r3-07 | B | loaded | 0.3 | 0.02 | 7,284 | `58cabfdd` / `892ae374` |
| r3-08 | B | loaded | 0.2 | 0.02 | 7,284 | `58cabfdd` / `892ae374` |
| r3-10 | C | loaded | 0.3 | 0.11 | 5,803 | `bbfc7168` / `d6279745` |
| r3-12 | C | loaded | 0.2 | 0.12 | 5,803 | `bbfc7168` / `d6279745` |

**Unload note.** Only the first unload was verified: `/api/ps` was empty
afterwards. For r3-03 and r3-05, `/api/ps` still listed the model
immediately after the unload request, and again right before the next
call. Yet those runs re-evaluated the full prompt (3.3 s, against 0.02 s
when cached), showed a non-trivial `load_duration`, and produced output
byte-identical to the verified-cold r3-02. Two explanations fit, and this
run cannot distinguish them:

- The unload request reset the runner's state before `/api/ps` reflected
  it.
- Only the prompt cache, not the model load, matters.

Asking Ollama to unload is therefore **not reliably verifiable** with an
immediate `/api/ps`.

**Findings.**

1. **With the cache condition held fixed, output is reproducible.** In each
   condition, every run produced byte-identical answers and reasoning:
   3/3, 2/2 and 2/2.
2. **With only the cache state changed, the output changes.** The same
   request gave three different answers and completion lengths (5,203,
   7,284 and 5,803 tokens). The only difference between conditions was
   what preceded the request. This is a controlled demonstration, not an
   inference, that prompt-cache state affects Qwen3:4b output on Ollama
   0.32.1.
3. **Not everything is explained.** Rounds 1 and 2 sent the same request
   and got 4,279 and 5,712 tokens; neither matches any condition here:
   - Round 1's run had an uncached main prompt, but it followed a request
     that shared the system-prompt prefix. That differs from condition A,
     which was fully cold.
   - Round 2's run followed a full generation with a shared implementation
     prefix. Condition C used a 1-token prime and gave 5,803, not 5,712.

   So the exact cache contents, not just "cached or not", matter, or a
   further factor does. Rounds 1 and 2 are not reproducible from their
   records alone.
4. **The answer's content depends on cache state too:**

   | Condition | Grade | Ollama `/api/embed` HTTP call |
   |---|---|---|
   | A | Correct, all 8 key identifiers | Omitted (in neither answer nor reasoning) |
   | B | Correct, all 8 key identifiers | Named as an HTTP call to Ollama (reasoning cites `/api/embed`) |
   | C | Correct, all 8 key identifiers | Omitted from the answer (present in reasoning) |

   **A single run cannot establish whether the model "includes"
   `/api/embed`.** Round 2's reading (inconsistent salience) stands, and is
   now shown to vary with run state, not only between seeds.

**Consequence for #345 measurement:**

- Any further comparison must fix the cache state per arm and record it.
  Condition A is preferable: each arm starts with a cold cache, verified by
  `prompt_eval_duration` (a full re-evaluation) rather than by `/api/ps`.
- Differences between arms then need repetition across seeds; the seed alone
  does not make a run reproducible.

## Part 2: retrieval candidates for the Step 0 question (retrieval, #342)

**Method.** `scripts/retrieval_candidates_345.py` runs the unchanged local
orchestrator (`run_rag`, git HEAD). Its service code is identical to the
deployed `82b70cd`. It runs against the deployed read-only services, with
llm_service replaced by a local stub, so **nothing was generated**. The
only model call is the query embedding. For each witness it then runs one
read-only deep vector search (k = 2,000) and one read-only per-document
search with exact scores. The repository generation `e423d1bb…` (commit
`8e063350`) was the Step 0 generation and was unchanged before and after.
The script ran three times, and the candidate pool was identical across
runs.

**Fidelity: partial.** The reproduced final context starts with the exact
3,950 bytes Step 0 sent (the first four chunks are byte-identical), but
locally a fifth chunk is added: pool rank 35, the 3-byte text `---` from
`DOCS/architecture/ADR-032-layered-resolution-example.md`, for 4,078 bytes
in total. Production either did not receive that chunk or did not have
room for it. Two plausible causes:

- A production `.env` override of a pool or budget setting, such as
  `MAX_TOTAL_CHUNKS` below 35 or a smaller effective context budget.
- A difference this run cannot see.

The candidates below are therefore the local reproduction, **whose first
4 KB matches production exactly**. The difference cannot affect the witness
findings: none of the witnesses is anywhere in the pool.

**Seed and pool.**

- The seed search (k = 20, filter `source_type: code`, the repository and
  the generation) returned **20 Markdown chunks** (scores 0.751-0.798). In
  this corpus, repository documentation is ingested as `source_type: code`.
- These form 13 seed documents. Graph expansion added **0 documents**
  (`expanded_docs_considered` 0).
- The pre-budget pool is 38 chunks (36,476 bytes by the UTF-8 estimate),
  all `markdown_section` or `markdown_module`, from DOCS test results,
  audits, ADRs and notes. **There is not a single Python chunk.**
- In the deep top 2,000 under the same filter, 1,549 hits are Markdown and
  451 are Python source.

**Implementation witnesses** (all exist in the generation as `python
source` with `source_type: code`; the scores are exact cosine
similarities):

| Witness | Best chunk score | Rank under the seed filter |
|---|---|---|
| `service.py#hybrid_retrieve` | 0.666 | 676 |
| `service.py#run_rag` | 0.660 | 819 |
| `routes.py#rag_endpoint` | 0.638 | 1,777 |
| `service.py#resolve_repo_id_http` | 0.611 | > 2,000 |
| `vectors.py#similarity_search` | 0.605 | > 2,000 |
| `pgvector_store.py#PgVectorStore.similarity_search` | 0.586 | > 2,000 |
| `service.py#_query_generation` | 0.576 | > 2,000 |
| `ollama.py#OllamaEmbedder.embed` | 0.551 | > 2,000 |
| `query.py#embed_query` | 0.547 | > 2,000 |
| `factory.py#get_embedder` | 0.446 | > 2,000 |

The seed cut-off is 0.751; the 2,000th result scores 0.634. The evidence
trace reports `not_found_by_vector_or_graph` for all 10 witnesses.

**Findings.**

1. **This is a vector-ranking failure, not a budget truncation.** No
   witness reaches the pool at all. The documentation that *describes*
   this pipeline (test results, audits, ADRs) is semantically closer to the
   question than the code that *implements* it, by 0.09-0.30 in cosine
   score. Asking for "implementation code rather than documentation" in
   the question does not change that.
2. **Graph expansion cannot rescue it from these seeds.** All 13 seed
   documents are Markdown, and none expanded to code. Whether that is
   because doc→code `DOCUMENTS` edges are missing for these documents or
   because of expansion policy is for #342 to determine; this run only
   observes "0 expanded".
3. **Witness discoverability is very uneven.** The orchestration functions
   (`hybrid_retrieve`, `run_rag`) are nearest. The cross-service hops
   (`similarity_search`, `_query_generation`) and the embedding chain
   (`embed_query`, `OllamaEmbedder.embed`, `get_embedder`) are furthest.
   The embedding chain is the part answers most often omitted.

## For #194 (budgeting): what a larger budget would contain

With the current retrieval, a 16 KB or 32 KB budget would be filled from
the same 38-chunk pool: more of the same documentation, still **zero
implementation witnesses**. For this query, a larger evidence budget alone
cannot help. Budget experiments (step 3) are only meaningful with
candidate sets that contain witnesses. Those come either from a retrieval
change (#342) or from a constructed "realistic" package, and constructing
one is a design decision, not an observation.

## Not done (as instructed)

Steps 3-4 (16 KB and 32 KB evidence packages and full call-path grading)
were not started. No new evidence-selection mechanism was built, nothing was
re-ingested, and no production setting changed.

## Open items

- **Production pool or budget settings:** the operator can check them
  without changing anything, by reading `MAX_TOTAL_CHUNKS`,
  `CONTEXT_WINDOW_TOKENS`, `PROMPT_RESERVE_TOKENS` and
  `OUTPUT_RESERVE_TOKENS` from the production `.env`. That would explain the
  3-byte fidelity gap.
- **Unload verification:** before cold-cache arms are relied on, decide how
  "cold" is verified. A full prompt re-evaluation is the practical signal.
