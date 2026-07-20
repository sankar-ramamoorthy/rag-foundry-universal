---
title: "RAG Quality Evaluation Methodology — Chunking → Retrieval → Generation → Reranker Gate"
date: 2026-07-20
type: audit-methodology
status: proposed
issue: "#49 (Phase 2.5 acceptance pass is issue #48 and is a prerequisite)"
tags:
  - audit
  - rag-quality
  - evaluation
  - rag-foundry
related:
  - "[[00-Audit-Overview]]"
  - "[[04-Scalability-Plan]]"
  - "[[../adr/ADR-039-artifact-level-embedding-strategy]]"
  - "[[../adr/ADR-040-code-intelligence-embedding-strategy]]"
  - "[[../adr/ADR-045-hybrid-vector-graph-rag]]"
---

# 🔬 RAG Quality Evaluation Methodology

> [!abstract] Purpose
> Before adding a reranker (or swapping the embedder, or tuning chunk sizes), verify the
> foundations in order: **chunking → retrieval → generation**. This doc records that
> methodology, maps each stage to the actual code in this repo, and gives a decision rule
> for when — and only when — a reranker is justified. Nothing here has been executed yet;
> this is the eval plan, not eval results. Results go in `DOCS/test_results/` per WP.

## 🧭 The core rule

> A reranker only helps when the correct chunk is already somewhere in the candidate set
> but ranked too low. It **cannot** fix: missing content, broken chunk boundaries, wrong
> repository filtering, poor embeddings, or incomplete ingestion.

Diagnostic order — do not skip ahead:

```text
verify ingestion → inspect chunking → measure retrieval recall → test generation
→ add reranking only if ranking is the proven bottleneck
```

Decision table once a known-answer query has been run:

| Observation | Likely problem |
|---|---|
| Relevant evidence absent from the retrieved candidate set (top 20) | Chunking, embedding, filtering, query formulation, or retrieval — **not** a reranker problem |
| Relevant evidence appears around rank 8–20 | Reranker may help |
| Relevant evidence already in the top 3, but the answer is poor | Prompting, context assembly, or generation model — **not** a reranker problem |
| Correct evidence retrieved, but from the wrong repository | Repo-isolation or metadata-filtering defect (ADR-030 correctness bug) |
| Many near-identical chunks occupy the result set | Chunking overlap or deduplication problem |
| Answer omits an important fact present in the supplied context | Generation or context-formatting problem |

`WP-S8` in [[04-Scalability-Plan]] already stubs a flag-gated reranker with the
acceptance criterion *"reranker flag on/off compared on a small eval set"* — this doc is
the prerequisite work that produces that eval set and proves (or disproves) the need
before WP-S8's reranker half is picked up.

> [!tip] The most valuable outcome may be a negative result
> If the eval below shows the reranker isn't the bottleneck, that's not a null result —
> it means the system can still improve through chunking fixes, metadata filtering,
> deduplication, traversal tuning, and prompt assembly, **without** adding another model,
> another latency stage, or another operational dependency. Proving a reranker
> unnecessary is cheaper than building one and finding out later.

---

## 0 · Recommended execution order (WP-Q0)

The work is **empirical, not architectural** — this is one evaluation pass over a small
curated corpus, not three independent audits. Do it in this order, in one pass per query:

1. **Build a small, curated evaluation corpus** containing both code (an ingested repo)
   and uploaded documents — reuse `shared/smoke_repo` (already a live-smoke fixture) plus
   2–3 representative documents, so the corpus is real ingested data, not synthetic text.
2. **Define answerable questions**, each with an exact expected source artifact
   (`canonical_id` for code, a specific passage for documents) — 8–12 questions, mixing
   code and document queries, per §2's known-answer-set guidance.
3. **For every question, record all of the following in one row** (not just rank —
   the full diagnostic surface in a single pass):

   | Field | What it tells you |
   |---|---|
   | Source present in index | Ingestion actually succeeded for this artifact — if false, stop here, it's an ingestion bug, not a retrieval or reranker question |
   | Seed rank (top-k vector search) | Where §2's decision table starts |
   | Expanded-context rank (after graph traversal) | Whether graph expansion recovers a seed miss |
   | Duplicates in candidate set | Whether redundant chunks are crowding the window (§2) |
   | Repository leakage | Whether `repo_id` scoping actually held (ADR-030 correctness bug if not) |
   | Final answer quality | Pass/fail against the expected passage, using the *actual* end-to-end path (not clean context yet) |

4. **Run the clean-context generation test (§3) for every failed answer only** — not
   for every question. If the answer already passed end-to-end, there's nothing to
   isolate.
5. **Classify every failure** using the decision table before changing anything:
   absent from top 20 (chunking/retrieval/filtering problem) vs. rank 8–20 (reranker
   candidate) vs. top-3-but-bad-answer (prompting/model problem). Do not touch chunking,
   retrieval, or the generator until this classification is done for the whole corpus.
6. **Only after classification**, change chunking or retrieval to fix whatever the
   dominant failure class actually is.
7. **Consider a reranker only if** enough failures consistently classify into the rank
   8–20 bucket — "enough" meaning a real fraction of the corpus, not one query's
   coincidence.

**Acceptance criteria (WP-Q0):**
- [ ] Curated corpus assembled (repo + documents) and committed or referenced (e.g. `shared/smoke_repo`)
- [ ] 8–12 answerable questions defined with exact expected source artifact/passage
- [ ] One recording table (the six fields above) filled in per question, in `DOCS/test_results/`
- [ ] Clean-context test (§3) run for every failed answer, not every question
- [ ] Every failure classified per the decision table before any chunking/retrieval change is made
- [ ] Explicit go/no-go verdict recorded on the reranker, with the failure-count breakdown that justifies it

Sections 1–3 below give the background and per-stage detail (why chunking looks the way
it does today, what "seed rank" and "expanded rank" mean concretely, how the clean-context
test is scored) for executing steps 1–4 above; they are reference, not a second pass.

---

## 1 · Chunking quality

**What exists today** (read before assuming a generic "chunking problem"):

- Code artifacts do **not** go through a text chunker at all. Per [[../adr/ADR-039-artifact-level-embedding-strategy|ADR-039]] / [[../adr/ADR-040-code-intelligence-embedding-strategy|ADR-040]], the *artifact is the embedding unit* — a MODULE embeds the whole file, a CLASS/FUNCTION/METHOD embeds its whole def block (`RepoGraphBuilder` via `ast.get_source_segment`). There is no chunk-boundary question for code today because there are no sub-artifact chunks.
- Plain documents and uploaded files go through `shared/chunkers/text.py` (`TextChunker`) via `shared/chunkers/selector.py` (`ChunkerFactory.choose_strategy`), which picks a strategy **purely from content length**, not structure:
  - `< 2000` chars → `sentence`, `chunk_size=200, overlap=20`
  - `< 10000` chars → `paragraph`, `chunk_size=500, overlap=50`
  - `>= 10000` chars → `fixed_char`, `chunk_size=1000, overlap=100`
  - This heuristic has no awareness of Markdown headings, fenced code blocks, or table boundaries — a fenced code block or heading can be split mid-block if it straddles a `chunk_size` boundary.
- Docling/OCR ingestion (ADR-047) sits in front of this for documents — check whether Docling's own structural chunking is used, or whether Docling output is re-chunked by `TextChunker` (would be a double-chunking bug if so).

**Questions to answer:**

- Are chunks semantically coherent — does a chunk read as a complete thought when shown in isolation?
- Are headings, code fences, and surrounding context preserved, or does a chunk boundary land mid-sentence / mid-code-block?
- Are chunks too large (diluting embedding relevance with unrelated content) or too small (losing context needed to answer)?

**How to check (manual, no new tooling required):**

1. Pick 5–10 representative source documents already ingested (mix of long Markdown with code fences, and a large plain-text doc that hits the `fixed_char` branch).
2. Pull their chunks via `GET /v1/chunks` (`ingestion_service`) or a direct read of `vector_chunks`.
3. For each chunk, read it standalone and score: coherent / truncated mid-thought / structure broken (heading separated from its section, code fence split).
4. Record pass/fail per chunk in `DOCS/test_results/`.

**Acceptance criteria (WP-Q1):**
- [ ] 5–10 documents' chunks manually reviewed and scored coherent/broken, results in `DOCS/test_results/`
- [ ] At least one confirmed example of a heading- or code-fence-split chunk, or a documented finding that none occurred
- [ ] Explicit note on whether Docling output is being re-chunked by `TextChunker` (double-chunking risk)

---

## 2 · Retrieval quality

**What exists today:**

- Seed vector search defaults to `k=5` (`vector_store_service/src/api/v1/vectors.py:33`), filtered to `doc_type="code"` for the graph-aware path (ADR-045). `EXPANDED_DOC_CHUNKS=3` chunks are pulled per graph-expanded doc, capped at `MAX_EXPANDED_DOCS=20` and `MAX_TOTAL_CHUNKS=50` overall (`rag_orchestrator/src/core/config.py`).
- Embeddings are `mxbai-embed-large:latest` (1024-dim) via Ollama (`rag_orchestrator/src/core/config.py`, `vector_store_service/src/core/config.py`).
- Repo scoping is supposed to be a hard filter (ADR-030) — every query is scoped by `repo_id`, so cross-repo leakage in results would be a correctness bug, not a tuning issue.

**Questions to answer:**

- For a known question with a known correct chunk, does that chunk appear in the initial top 5 (seed vector search) or top 10–20 (after graph expansion)?
- Are results actually restricted to the queried repo, or does another repo's content leak in?
- Are near-duplicate chunks (e.g. the same function embedded twice from a stale re-ingest, or overlapping chunk windows) crowding out distinct useful matches?

**How to check:**

1. Build a small known-answer set: 8–12 (question, expected `canonical_id` or expected chunk substring, `repo_id`) tuples covering both code and document queries.
2. For each, call `/v1/vectors/search` (or the orchestrator's retrieval path) directly and record the rank position of the expected chunk (absent / 1–5 / 6–10 / 11–20 / not found in 20).
3. Cross-repo check: run the same query against a `repo_id` that should *not* contain the answer and confirm zero relevant hits.
4. Duplicate check: scan the top-20 for near-identical `chunk_text` and note how many distinct *useful* chunks are actually present versus redundant repeats.
5. Apply the decision table above per query.

**Acceptance criteria (WP-Q2):**
- [ ] Known-answer eval set (8–12 queries) checked in under `DOCS/test_results/`, with rank position recorded per query
- [ ] Recall@5 and Recall@20 computed and reported
- [ ] Cross-repo isolation confirmed (zero leakage) or filed as a bug if violated
- [ ] Duplicate/near-duplicate rate in top-20 reported

---

## 3 · Answer quality with clean context

**Goal:** isolate the generator from retrieval noise — hand-pick the best 2–4 chunks for a known query and judge the LLM's answer on its own merits.

**Procedure:**

1. For each known-answer query from §2, manually select the 2–4 best chunks (skip retrieval entirely — this step assumes retrieval already found the right chunk, per the decision table's "top 3, answer is poor" branch).
2. Call the model directly (bypassing the LiteLLM-routed `/generate` service is fine for this diagnostic) — e.g. Ollama's `/api/chat` with `think:false` against `Qwen3` — with only those chunks as context.
3. Score: grounding (does the answer only assert what's in context?), citation (does it point back to the right file/symbol?), omission (did it miss something present in the context?), latency.

**Acceptance criteria (WP-Q3):**
- [ ] 8–12 clean-context generations scored for grounding/citation/omission, recorded in `DOCS/test_results/`
- [ ] Latency recorded per generation (cold and warm) for the model actually in use
- [ ] Explicit verdict per query: prompting/model problem vs. no problem found

---

## 4 · Reranker decision gate

Do not start reranker work (the reranker half of `WP-S8` in [[04-Scalability-Plan]]) until
WP-Q0's recording table (§0) shows:

- [ ] A non-trivial fraction of the corpus's questions have the correct chunk landing at rank 8–20 (not absent, not already top-3)
- [ ] Those same failures are not already explained by a chunking defect (§1) or a generation defect confirmed via clean-context (§3)

If the eval set instead shows "correct chunk absent from top 20" as the dominant failure mode, the next work is chunking/embedding/filtering fixes (§1/§2), not a reranker. If it shows "top 3 but bad answer," the next work is prompting or model choice (§3), not a reranker. If neither dominant pattern holds, record the negative result — see the callout in §0 — and move on to whichever lever (chunking, metadata filtering, dedup, traversal, prompt assembly) the corpus actually points to.

---

## Related

- [[04-Scalability-Plan#WP-S8 — Retrieval quality/perf at scale|WP-S8]] — where the reranker itself would land, flag-gated, once this doc's gate is satisfied
- [[../adr/ADR-045-hybrid-vector-graph-rag|ADR-045]] — the retrieval flow being evaluated
- [[../adr/ADR-039-artifact-level-embedding-strategy|ADR-039]] / [[../adr/ADR-040-code-intelligence-embedding-strategy|ADR-040]] — why code has no chunk-boundary question today
- `DOCS/test_results/` — where every WP above must record its eval output, per the roadmap's "nothing ships without its benchmark/eval delta recorded" rule
