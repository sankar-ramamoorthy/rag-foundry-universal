---
title: "Issue #240 frozen repository-overview quality evaluation"
date: 2026-10-03
type: evaluation-protocol
status: preregistered
tags: [evaluation, repository-overview, provenance, retrieval]
related:
  - "[Failure localization](/DOCS/evaluations/2026-09-20-issue-240-orientation-failure-localization.md)"
  - "[Production observations](/DOCS/test_results/2026-09-20-issue-240-orientation-failure-localization.md)"
---

# Issue #240 frozen repository-overview quality evaluation

Freeze this set before an overview retrieval or classification change. Run
one complete pass per query for each candidate on the same repository source
snapshot, model, context budget, and retrieval settings. Repeats are reserved
for a disputed or variable result and must be identified as such. The five
original questions test the committed ORIENT policy as well as the purpose
retrieval failure. The three purpose variants prevent a one-string fix. The
three controls guard against suppressing relevant historical, fixture, or
implementation evidence when it is explicitly requested.

## Snapshot and request contract

| Field | Frozen value |
| --- | --- |
| selected repository | `f7641840-ba13-5f9d-9ae6-87e1f924709d` (`rag-foundry-universal`) |
| ready generation | `d3ecfaea-23a1-4067-8f1a-0010c3158004` |
| source SHA | `00e0cc9bf268a90ac85ed3b78ff7a8ba0afaf4bb` |
| baseline runtime | `d7fbf8748458d979a87cfbf233d357958198f233` |
| endpoint | `POST /v1/rag` |
| common request | `repo_id` above; `top_k=10`; `claim_type=repository_overview`; `rerank=false` |
| exact issue repro | Q5 additionally at `top_k=20` |
| model | `ollama/Qwen3:4b`; record the response's actual model/provider and fallback |
| budget | 8192 window, 1024 prompt reserve, 2048 output reserve; record effective `context_budget` in each retrieval plan |

Read the generation endpoint before and after each run. Accept a result only
when both reads and the RAG response report the same ready generation.
Record the runtime `/version` separately from the corpus source SHA. A
candidate orchestrator may point at the pinned production ingestion, vector,
and LLM services for read-only comparison; it must not ingest, delete, or
mutate production data.

## Questions and expected evidence

| ID | Query | Expected authority / answer check |
| --- | --- | --- |
| Q1 | I need information about the repo structure. | Current ORIENT file counts, languages, services, manifests, test/docs directories; say which facets are unavailable. |
| Q2 | Describe the actual directory, service, and package structure of this repository. | Current ORIENT services and directory evidence; do not promote a fixture or historical design into current layout. |
| Q3 | Describe the actual directory, service, and package structure of rag-foundry-universal. | Same as Q2, explicitly bound to the selected repository. |
| Q4 | Give me an architectural map of this repository. | ORIENT for observed services/manifests plus current `CLAUDE.md#claude_md.architecture_independent_services_over_http` or equivalent current implementation/config evidence for service relationships; acknowledge relationships not established by evidence. Do not claim `py-coding-agent` files belong to this repository. |
| Q5 | What is this repository about? | `CLAUDE.md#claude_md.what_this_project_is` in candidates **and final context**; describe read-only graph-aware code/document intelligence. |
| Q6 | What does rag-foundry-universal do? | Same canonical purpose source and check as Q5. |
| Q7 | Describe this project's purpose and the kinds of source it analyzes. | Same canonical purpose source; identify code repositories and documents. |
| C1 | According to the repository-understanding note, what went wrong with the `my_test_repo` answer? | The requested `DOCS/notes/20260906-repository-understanding-trace-and-structural-artifacts.md` discussion remains accessible; label it historical. |
| C2 | What is `shared/smoke_repo` used for? | `shared/smoke_repo/README.md` or relevant fixture source remains accessible; label it a fixture. |
| C3 | What does `GraphAssembler.assemble` do? | Current implementation source for that symbol remains accessible; do not answer from a historical plan alone. |

Canonical IDs for Q4 and controls must be copied from the pinned index before
scoring. The Q5–Q7 purpose target above is already confirmed indexed. The
separate `GenerateSkill.run` context-budget case belongs to context-survival
work and is not scored as an #240 overview question.

## Recording and acceptance

For every run record query, request, runtime/source SHA, generation, model,
trace ID, seeds, expanded candidates, target rank/presence, duplicate count,
`retrieval_plan.final_context_manifest`, `retrieval_plan.provenance_diagnostics`,
ORIENT response and overview policy, answer, citations, and a short judgment
for source correctness, selected-repository subject, missing-evidence
acknowledgment, and answer correctness. Empty diagnostics are information,
not proof of a clean answer. If the target is not in candidates, do not call
it a generation failure; if it is in candidates but not final context, record
a context-survival failure.

Q1–Q4 pass only when current structural facts that ORIENT can supply appear
in the answer, claims stay tied to this repository, and unsupported details
are qualified. Q5–Q7 pass only when the canonical purpose section reaches
final context, the answer states the purpose accurately, and the source is
identified. C1–C3 must keep their expected sources and correct answers.
Report counts separately for candidate recall, final-context survival,
answer correctness, and control regressions; no overall pass can hide a
regression. A candidate policy is eligible to merge only with recorded
before/after evidence and no control regression.

## Independent experiment matrix

| Variant | Change | What the result means |
| --- | --- | --- |
| Baseline | Current classifier and retrieval | Establish all stage measurements on the frozen corpus. |
| Classification only | Classify root `README.md` and `CLAUDE.md` as canonical repository descriptions; leave retrieval selection unchanged | Correct role metadata and improved authority treatment support the classification hypothesis. Unchanged seed membership is expected because current retrieval does not rank on role. |
| Selection only | Keep old roles; deterministically include selected-repository canonical overview passages for overview queries | Candidate inclusion, final-context survival, and correct answers support the selection hypothesis. Candidate-only success points to context budgeting; final-context success with a wrong answer points to generation. |
| Combined, only if needed | Apply both measured changes | Use only if independent results show a specific benefit beyond either change alone. |

Select the smallest change supported by the matrix. The committed `e00ddb2`
ORIENT policy is separately compared to the baseline for Q1–Q4; it does not
claim to solve Q5–Q7 seed selection.
