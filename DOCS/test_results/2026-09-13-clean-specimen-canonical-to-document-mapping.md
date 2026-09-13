---
title: "Clean Specimen: Correct Evidence Reached the Prompt, Generation Fabricated a Citation"
date: 2026-09-13
type: test-result
status: complete
tags:
  - rag
  - evaluation
  - retrieval
  - evidence-survival
  - generation-quality
  - hallucination
related:
  - "[WP-T1 planning doc](/DOCS/audit/WP-T1-retrieval-evidence-trace.md)"
  - "[WP-T1e first live run](/DOCS/test_results/2026-09-12-wp-t1e-evidence-survival-run.md)"
  - "[Self-ingestion eval-corpus policy (#106)](/DOCS/notes/20260912-self-ingestion-eval-corpus-policy.md)"
  - "[Evidence-survival question set](/DOCS/evaluations/2026-09-07-evidence-survival-question-set.md)"
---

# Clean Specimen: Correct Evidence Reached the Prompt, Generation Fabricated a Citation

## Why this specimen, and why it's a fresh question

Per the corpus-contamination policy (issue #106, `DOCS/notes/20260912-self-ingestion-eval-corpus-policy.md`),
answer-quality grading against this repo's self-ingested corpus is only trustworthy for questions
whose answer isn't already written down somewhere in `DOCS/evaluations/`, `DOCS/test_results/`, or
similar. A first attempt at reusing frozen Candidate 3
(`DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`) confirmed exactly that risk: the
model's answer explicitly reasoned about "the frozen 8-question experiment" and "Candidate 3,"
i.e. it could see its own answer key. That run is **not** counted as evidence here — see the
"Discarded first attempt" note below.

This specimen instead uses a question formulated fresh for this run, targeting current
implementation and never written down anywhere in the ingested corpus:

> **When graph expansion returns candidate canonical IDs, how does the orchestrator map those
> canonical IDs back to document IDs before fetching chunks?**

Target canonical_ids (confirmed present in the live graph before running):
- `rag_orchestrator/src/core/service.py#canonical_to_document_map_http`
- `rag_orchestrator/src/core/service.py#hybrid_retrieve`

## Setup

- Executed via `run_rag()` in-process (not the plain `/v1/rag` HTTP endpoint, which doesn't expose
  `trace_canonical_ids`), with `INGESTION_SERVICE_URL`/`VECTOR_STORE_URL`/`LLM_SERVICE_URL`/
  `OLLAMA_BASE_URL` pointed at the Tailscale-reachable production instance (`100.105.24.12`) — the
  same pattern used for WP-T1e and the issue #107 repro.
- Repo: `rag-foundry-universal`, repo_id `f7641840-ba13-5f9d-9ae6-87e1f924709d`.
- Model: default alias, resolved to `ollama/Qwen3:4b`.
- Runtime: this run postdates the issue #107 fix (PR #109) and the prod-refresh.sh review fixes
  (PRs #113-#115) — production is current with `main` as of this session.

## Discarded first attempt: reusing frozen Candidate 3

Before formulating the fresh question above, a first attempt reused
`DOCS/evaluations/...#candidate_3_hybrid_retrieve_s_cross_module_ranking_mapping_fetch_chain`'s
question text directly. The real implementation source (`hybrid_retrieve`) did appear in the
returned sources, but the answer opened with *"Based on the provided evidence from the frozen
8-question experiment and the specific candidate context (Candidate 3)..."* and justified a claim
using "Candidate 2's expected answer" — the model was visibly reading its own answer key. Graded:

```text
Answer correctness:          PASS
Implementation source found: YES
Clean retrieval test:        NO
Clean generation test:       NO
Reason:                      evaluation/self-reference contamination (#106)
```

Kept here only as evidence for #106, not counted as a retrieval- or generation-quality result.

## Trace: the fresh-question run

**`trace_id`**: `1ddc457a9435476693cc211753801f9e`

**Seed candidates (17 total)**: a mix of real implementation (`rag_orchestrator/src/core/service.py`
and both target functions, `ingestion_service/src/api/v1/graph.py#get_nodes_by_canonical_ids`,
`ingestion_service/src/core/graph_utils.py`, `rag_orchestrator/src/retrieval/codebase_utils.py` and
its `canonical_ids_to_document_ids` function) alongside the expected corpus-contamination
candidates (the WP-T1 planning doc, the evaluations doc, two ADRs, an architecture diagram, a
research spec, and a WP-T1a test file). Real implementation is present in roughly 7 of 17 seeds —
less contaminated than the discarded first attempt, though not clean.

**Graph expansion**: 182 candidates considered, capped to 20 (`MAX_EXPANDED_DOCS`). All 20 that
survived the cap are `DEFINES` children of one of two source documents — i.e. expansion here mostly
surfaced sibling functions of whichever seed module anchored it, not anything further afield.
Irrelevant to this question's outcome, since both targets were seed hits, not expansion-dependent.

**Evidence trace for both targets** — both survived every stage cleanly:

```json
{
  "canonical_id": "rag_orchestrator/src/core/service.py#canonical_to_document_map_http",
  "found_by_vector": true, "found_by_graph": false, "survives_cap": false,
  "chunk_fetched": false, "survives_chunk_limits": true, "reaches_final_context": true,
  "drop_reason": null
}
{
  "canonical_id": "rag_orchestrator/src/core/service.py#hybrid_retrieve",
  "found_by_vector": true, "found_by_graph": false, "survives_cap": false,
  "chunk_fetched": false, "survives_chunk_limits": true, "reaches_final_context": true,
  "drop_reason": null
}
```

(`survives_cap`/`chunk_fetched` are `false` because both were seed hits fetched directly, never
needing the expanded-doc fetch path they'd otherwise measure — not a failure signal here.)

**Final-context manifest** confirms both chunks actually crossed into the prompt:

```text
canonical_to_document_map_http  chunk_index=0  399 chars  52 tokens  selection_reason=seed
hybrid_retrieve                 chunk_index=0  457 chars  26 tokens  selection_reason=seed
```

**Token budget**: 2560 tokens before and after — nothing was cut by the budget; all 50 selected
chunks fit under the default 4096-token cap.

## The answer

The model fabricated an entirely fictional mechanism instead of using the correct evidence in
front of it:

> "The orchestrator maps candidate canonical IDs to document IDs **by directly accessing the
> `document_id` field stored in the graph object**. This field is explicitly set during ingestion
> (via `ingestion_service/src/core/codebase/graph_assembler.py`)... **O(1) lookups**."

It invented a nonexistent function (`map_canonical_ids_to_documents()`) with a fabricated code
snippet, and fabricated a quoted citation attributed to `2026-09-07-current-state-retrieval-audit.md`
Section 3.2 — no such section or quote exists in that document.

**The real answer**, present verbatim in the model's own context (per the final-context manifest
above): `canonical_to_document_map_http` (`rag_orchestrator/src/core/service.py:128`) POSTs the
canonical_ids to `ingestion_service`'s `POST /v1/graph/repos/{repo_id}/nodes/lookup` endpoint (the
issue #107 fix) at query time and builds the map from the JSON response — an HTTP round trip, not a
precomputed field, not O(1), and not something set during ingestion.

## Classification

```text
Retrieval:                   CLEAN PASS — seed hit, no cap loss, reached final context
Implementation source found: YES, both targets, confirmed via final_context_manifest
Answer correctness:          FAIL — confident fabrication
Fabricated citation:         YES (invented audit quote, invented code snippet)
Contamination present:       YES (evaluation-doc seeds still in context) but not causal --
                              unlike the discarded first attempt, there was no answer key
                              available for this fresh question to parrot; the model
                              hallucinated from scratch despite correct evidence being present
Category:                    G -- evidence reached final context, generation failed
```

## Why this specimen matters more than the contaminated ones

Every prior category-G finding (WP-T1e candidates 7 and 10) could be partly attributed to a
contaminated corpus supplying a plausible-sounding wrong answer alongside the real one. This
question had no such answer key anywhere in the corpus — the model wasn't retrieving and echoing a
written wrong answer, it invented one, complete with a fabricated supporting citation, while the
correct implementation sat in the same prompt unused. This is the cleanest demonstration yet that
retrieval correctness and generation reliability are genuinely separate failure modes, and that the
current default model (`Qwen3:4b`) fails at the second even when the first is flawless.

This is now the **third independent occurrence** of category G (after WP-T1e's candidates 7 and
10), reinforcing the same conclusion via
`DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`'s own decision principle (a pattern
recurring on ≥2 independent questions justifies attention): the next lever worth investigating is
generation reliability, not another retrieval-side change.

## Not done here

- No fix attempted for the fabrication itself (prompting, model choice, or otherwise) — recording
  the finding, not intervening, per this project's evidence-first discipline.
- No further batch of narrow questions run yet — planned as a follow-up to build a larger, still
  uncontaminated sample before drawing a stronger conclusion than "this recurs."
