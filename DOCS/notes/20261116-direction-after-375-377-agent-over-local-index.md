---
title: "Direction after #375 and #377: an agent loop over the local index (proposal)"
date: 2026-11-16
type: note
status: proposed
summary: "Proposal for the owner, not a decision. The #375 and #377 diagnostics showed that models with only source search and file reads recover the execution-path evidence the frozen graph selector could not, down to models costing a few cents per question. Proposed direction: keep ingestion, embeddings and the graph local; answer code questions with a small tool loop whose model is swappable through LiteLLM; give the graph a new job as tools and checks for that loop; make the graph earn that job in one bounded experiment; validate on a fresh sealed repository before any general claim. #373 stays paused. Nothing here is authorized for implementation."
tags: [direction, proposal, handoff, code-intelligence, agent, graph, model-ladder, issue-375, issue-377, issue-373, issue-207, issue-359]
related:
  - "[#375 source-navigation agent diagnostic](https://github.com/sankar-ramamoorthy/rag-foundry-universal/blob/docs/377-agent-model-ladder/DOCS/test_results/2026-11-15-375-source-navigation-agent-diagnostic.md)"
  - "[#377 agent model ladder](https://github.com/sankar-ramamoorthy/rag-foundry-universal/blob/docs/377-agent-model-ladder/DOCS/test_results/2026-11-15-377-agent-model-ladder.md)"
  - "[#359 final report and recommendation](/DOCS/test_results/2026-11-14-359-final-report-and-recommendation.md)"
  - "[Issue #373 (paused)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/373)"
  - "[Issue #207 (deferred agentic investigator)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/207)"
  - "[ADR-045 hybrid vector and graph retrieval](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Retrieval-side handoff](/DOCS/notes/20261112-code-intelligence-342-354-handoff.md)"
---

# Direction after #375 and #377: an agent loop over the local index

**Status: proposal for the owner.** This note records a recommended
direction and the evidence behind it. It decides nothing and authorizes no
implementation. Each step below needs its own issue, and the architectural
steps need an ADR.

Any agent picking this work up should read this note, then the two reports
it rests on, before proposing more graph or resolver work.

## 1. What changed

Until 2026-11-14 the working question was how to make the graph complete
enough for a deterministic selector to pre-pick sufficient evidence inside
a small budget. Two diagnostics on 2026-11-15 changed the question.

| Approach on the three revealed `mealie` questions | Core witnesses found |
|---|---|
| Frozen #359 graph selector, correct handler supplied | 2/16, 2/17, 5/14 |
| Capable model with only search and file reads (#375) | 16/16, 17/17, 14/14 |

The #377 ladder then asked what a correct, well-supported answer costs:

| Tier | Passing the fixed bar | Correct in prose | Cost per passing answer | Time per answer |
|---|---:|---:|---:|---:|
| Fable 5.2 | 3 of 3 | 3 of 3 | about $2.25 (estimate) | about 4 min |
| Opus 5.5 | 3 of 3 | 3 of 3 | about $1.21 (estimate) | about 3 min |
| Sonnet 5.5 | 4 of 6 | 6 of 6 | about $0.50 (estimate) | about 1.5 min |
| Haiku 5.5 | 4 of 6 | 6 of 6 | about $0.06 (estimate) | about 2.5 min |
| Qwen 3.8 27B (hosted) | 4 of 6 attempts | 5 of 5 answers | about $0.08 (published rates) | about 8.5 min |
| GLM 4.7 Flash (free) | 1 of 6 | 3 of 6 | $0 | about 4 min |

GPT-6 Luna was also run (two runs per question, 40 to 60 seconds and 1 to
4 cents each, with core-witness coverage like Haiku's). Its correctness
grades were pending when this note was written; the #377 report is the
record.

Three findings carry the proposal:

1. **The evidence is reachable without the missing graph edges.** Source
   navigation recovered what #359 lost to route prefixes, class-based
   controllers, injected services, callbacks and `self.*` receivers.
2. **Correct prose is cheap. Complete evidence is what costs.** The cheap
   tiers wrote correct answers; they failed the bar by leaving two or three
   leaf calls uncited on one question.
3. **Free tiers were not usable for this.** GLM 4.7 Flash made material
   false statements in half its answers.

## 2. What this does not show

- It is development evidence: three forward-trace questions in one public
  repository, with revealed answers, one to two runs per cell.
- Correctness was graded by a model, blind, with anchor checks. No person
  has reviewed the grades.
- Forward traces are the agent's best case. Callers, impact and route
  inventory questions, where an index should help most, are untested.
- The Claude tiers and the other models ran in different harnesses.
- Nothing was measured on a locally hosted model.
- It does not show the graph is useless. It shows that pre-selecting
  evidence from the graph alone was the wrong job for it.

## 3. Proposed direction

1. **Keep ingestion, embeddings, the graph and everyday document queries
   local.** Nothing measured argues for changing them.
2. **Answer code questions with a small tool loop**, not retrieve-once then
   generate. The model is swappable through the existing LiteLLM
   integration. Default to a cheap hosted model in the Haiku, GPT-6 Luna or
   Qwen 27B class; treat a local model as a privacy mode to be measured.
3. **Give the graph a new job: tools and checks for that loop.**
   - Tools: route inventory with composed public paths, callers of a
     function, call sites inside a function, `/trace` as a lead.
   - Checks: confirm cited lines exist, and flag functions on the path
     whose call sites the answer did not cite.
   - The graph then has to be useful when present, not complete.
4. **Make the graph earn that job in one bounded experiment** (section 4).
5. **Validate on a fresh sealed repository** (ADR-054) before any claim
   that this generalizes.

### What this would change in the architecture

- `llm_service` exposes generation and summarization only. A tool loop
  needs tool-calling passed through, or the loop lives in
  `rag_orchestrator`.
- ADR-045 fixes the query flow as vector seed then graph expansion with no
  LLM router. A tool loop is a different flow and needs a new ADR, with
  ADR-045 kept for the paths it still serves.
- Sending source to a hosted model changes the project's "everything stays
  local" character. That is a product decision for the owner. A hosted
  default with a local-only mode is the suggestion.
- The read-only invariant is unaffected: the tools read, and never edit,
  the ingested code.

## 4. The next experiment (needs its own issue)

**Question:** does giving the agent graph tools improve answers or reduce
cost, compared with search and file reads alone?

- **Arms:** agent alone; agent plus graph tools; the frozen graph selector
  as the existing baseline where it applies.
- **Model:** one cheap tier, the same in both agent arms, in one harness
  (`scripts/agent_navigation_ladder_377.py`).
- **Questions:** the three forward traces, plus three to six reverse and
  global questions with source-derived answers (callers of a function,
  what a change affects, the full route inventory of a package).
- **Measures:** the #377 pass bar, tokens, tool calls, wall time, cost.
- **What would count:** graph tools close the evidence gap on forward
  traces, or win on reverse and global questions, or cut tokens
  materially at equal quality. If none of the three holds, the graph is
  not earning its place in this path.

Two cheaper checks can run alongside:

- An evidence-completion pass on a cheap model ("list every call in the
  functions you cited"), to see if the gap closes without the graph.
- Jedi or Pyright definition lookup on the call sites #359 left
  unresolved, as the comparator #373 would otherwise lack.

## 5. What to stop or hold

- **#373:** stays paused with its protocol frozen. Measuring the resolver's
  gaps in detail is not the next most useful thing while the graph's job
  is being reconsidered.
- **Custom call-resolver work:** hold until the experiment in section 4
  says which edges a tool needs.
- **#370 query-time transparency:** still reasonable on its own terms for
  the existing path; unaffected by this note.
- **Hardware purchases:** nothing measured points to a GPU. The local
  question is whether a model in the 27B class is fast enough on available
  machines, which is a measurement, not a purchase.
- **Long protocols for single decisions:** the #375 and #377 loop took a
  day and under $2 of metered spend. Keep the fixed bar, the blind grading
  and the mechanical scorer; keep the loop that short.

## 6. Working without a top-tier model

- The product path does not need one. The top tiers bought complete
  citations, not more correct answers.
- The method is in the repository and does not depend on any one model:
  the scorer, the runner, the bundle and merge scripts, the rubric and the
  pass bar.
- For grading, prefer a grader from a different model family than the
  answers being graded, keep the anchor check, and have a person
  spot-check a sample.

## 7. Open decisions for the owner

1. Is hosted reasoning acceptable by default, with a local-only mode, or
   must code questions stay local?
2. Is the section 4 experiment the next piece of work, ahead of #373?
3. Which cheap tier is the default candidate: Haiku 5.5, GPT-6 Luna, or
   Qwen 3.8 27B?
4. Which fresh repository is reserved, unseen, for validation?
