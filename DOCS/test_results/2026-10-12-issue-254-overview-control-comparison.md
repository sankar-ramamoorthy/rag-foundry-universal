---
title: "Issue #254: matched repository-overview control comparison"
date: 2026-10-12
type: test-result
status: complete-with-control-regression
tags: [issue-254, repository-overview, controls, evaluation, development-corpus]
related:
  - "[Local policy candidate and failed answer gate](/DOCS/test_results/2026-10-12-issue-254-policy-candidate.md)"
  - "[Frozen overview acceptance criteria](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Previous normal-mode verification](/DOCS/test_results/2026-10-11-issue-254-257-production-verification.md)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #254: matched repository-overview control comparison

The policy improves repository overview answers, but **does harm an explicit
code-flow query in Repository Overview mode**. The original #254 explicit-path
question retains the current `Agent.run` method with claim selection off;
turning claim selection on removes it and produces a false evidence-absence
answer. The claim-only arm reproduces this without structured rendering.
The requested improvement-without-code-regression gate therefore fails.

All 30 requests from the recorded contract completed against unchanged ready
generations and runtime version responses. The
[completion audit](/DOCS/test_results/2026-10-12-issue-254-overview-control-comparison-audit.json)
records matrix coverage, model/budget checks, source survival, and matched
retrieval comparisons.

## Contract and provenance

The [raw comparison](/DOCS/test_results/2026-10-12-issue-254-overview-control-comparison.json)
stores its contract before its first RAG request, then each full HTTP response.
The [context record](/DOCS/test_results/2026-10-12-issue-254-overview-control-comparison-context.json)
stores ORIENT snapshots, all four service version responses, exact pinned
Python source for the code-flow checks, and synthetic policy observations.
The runner is `scripts/issue254_overview_control_eval.py`.

| Identity | Value |
| --- | --- |
| Local commit and local `origin/main` | `24d956184d566753fe5ac80f57132191a4f7c3e1` |
| Deployed services' reported commit | `24d956184d566753fe5ac80f57132191a4f7c3e1` |
| Deployed release | `prod-2026-10-12-0801am` |
| Foundry generation | `854e8484-7144-45c4-951b-ad8bc647c4bf` |
| Foundry source commit | `f344bd58ffde5d98f4993bc0a27192b50c8decc3` |
| Python agent generation | `24f827d7-a33b-45f7-93f4-ff6e5eaf3856` |
| Python agent source commit | `f854303e6e44ff95d94792d24868442a28080ba2` |

`origin/main` is the locally available remote-tracking ref, not a fresh GitHub
HEAD attestation. HTTP version metadata is self-reported, not image attestation.
Unexposed model digests and process configuration remain unknown. No runtime
code, configuration, ingestion, or production release was changed.

Each request checks ready generation/source before and after, response repo
and generation, effective controls, and stable orchestrator/ingestion versions.
All requests use `rerank=false`, `top_k=10` (Q5k20 uses 20). The live
retrieved-context cap is 4096 bytes. Model-generated answers report
`ollama/Qwen3:4b`; structured answers bypass generation.

| Arm | Query mode | Claim selection | Structured answers | Canonical selection |
| --- | --- | --- | --- | --- |
| `overview_off` | Repository Overview | off | off | off |
| `candidate` | Repository Overview | on | on | off |
| `claim_only` | Repository Overview | on | off | off |
| `normal` | Normal RAG | off | off | off |

All 11 frozen #240 questions retain their original wording and acceptance
criteria and run in the first two arms. Two Python-agent controls run in all
four arms: the original explicit-path R1 prompt/tool/result trace, and
"What does Agent.run do?" The code controls require current `Agent.run`
evidence in final context and sources, a correct description of the requested
behavior, and no false claim that named code is absent. R1 additionally
requires the prompt-to-tool-to-model handoffs. Sources alone do not prove
answer correctness. The overall gate requires an overview improvement with
no explicit-code regression against matched controls.

These are development/regression corpora under ADR-054. A single pass per
arm does not establish reliability across repeated stochastic generations,
and success here would not establish held-out generalization.

## Synthetic software observations

With unrelated `src/launcher.py#launch` and `src/engine.py#Engine.execute`
identities and an implementation passage, "Using [paths], trace an input
through a tool call and the result returning to the model" produces
`current_structure`. Selection removes the implementation passage with
`orient_inventory_authoritative_for_structure`. "What does Engine.execute
do?" produces `current_behavior` and retains the same passage.

This is a deterministic local observation of classification/selection, not
a live answer-quality score or independent generalization test. It shows
that the behavior does not require the Python-agent repository's exact names.

## Frozen overview results

Passes require the frozen source and answer obligations, not merely a plausible
answer. An unsupported attribution in C1 prevents an unqualified repeat of
the previous 11/11 result.

| Case | Overview off | Candidate | Judgment |
| --- | --- | --- | --- |
| Q1 | F | P | Off omits file/language counts, docs and unresolved facets; candidate matches ORIENT and exposes gaps. |
| Q2 | F | P | Off treats missing manifest evidence as no Python package for `vector_store_service`; candidate reports observed package markers and distinguishes unknown from absent. |
| Q3 | F | P | Off substitutes archived `rag-foundry-docgraph` layout and denies the selected name; candidate binds observed structure to the correct repo/generation. |
| Q4 | F | P | Off substitutes a narrow ingestion diagram; candidate separates current HTTP, datastore, and startup dependency evidence and qualifies heuristics. |
| Q5 | F | P | Off cannot state purpose; candidate retains and cites canonical purpose and accurately describes read-only graph-aware RAG. |
| Q5k20 | F | P | Same purpose/source result at `top_k=20`. |
| Q6 | P | P | Both retain/cite canonical purpose and describe the read-only retrieval system; candidate additionally states all supported languages. |
| Q7 | F | P | Off substitutes an extraction subsystem and misses canonical purpose; candidate states code/document scope and supported languages from that passage. |
| C1 | P | F (attribution) | Both retain the requested note and explain historical fixture contamination. Candidate labels it historical, but falsely says the incident is specifically documented by `test_repo_scoping.py` under issue #30. That file tests cross-repo filter/forwarding defects, not the note's embedded-fixture incident. |
| C2 | Source F | P | Off broadly identifies a fixture but misses its exact authority; candidate retains/cites the smoke-fixture README and explains its purpose. |
| C3 | Source F | P | Off cites a class chunk without the requested method; candidate retains/cites `GraphAssembler.assemble` and correctly describes construction and resolution. |

Strict source-plus-answer acceptance is **10/11 candidate versus 2/11 off**.
The eight overview questions improve from **1/8 to 8/8**. The three original
controls score **2/3 candidate versus 1/3 off**; C1's core incident explanation
and source access improve, but its extra false attribution is an answer defect.
Counting only that core explanation would yield the earlier-style 11/11;
it would hide a factual error in this response.

Canonical purpose discovery/final-context survival/source listing is **4/4
candidate versus 1/4 off**. Requested exact historical/fixture/method source
survival and listing for C1-C3 is **3/3 candidate versus 1/3 off**. For Q1-Q3,
zero retrieved passage chunks is intentional: the candidate answers from
generation-matched inventory/graph structured facts. All four structured
answers report zero validation errors. Source listing is the response's
`sources` field; it does not imply every model answer includes an inline
canonical-ID citation.

The matched frozen suite has median latency **13.17s candidate versus 29.90s
off** (totals 133.01s versus 361.48s). This single run includes deterministic
rendering in the candidate; it is not a repeated performance estimate.
The Compose `!override` parsing gap remains, and Q4 scopes its map to the
base and test files rather than claiming active production-profile coverage.

## Explicit-code results and loss attribution

| Query / arm | Current `Agent.run` in final context / sources | Answer judgment |
| --- | --- | --- |
| R1 / normal | Yes / yes | Prompt, tool dispatch and result feedback are correct; `main` is omitted, so this is not a complete three-symbol trace. |
| R1 / overview off | Yes / yes | Retains the same method and explains the loop; also omits `main` and relies partly on the ADR. |
| R1 / claim only | No / no; zero final chunks and sources | F: claims no evidence of the named `py_mono` code, instead of tracing it. |
| R1 / candidate | No / no; zero final chunks and sources | F: says the question references code absent from pinned evidence. |
| R1_method / all four arms | Yes / yes in every arm | F in every arm: confuses `Agent.run` with a skill runner; no correct explanation of its LLM/tool loop. Normal, off and candidate quote a skill's three-argument signature as the agent's signature. |

For R1 all four arms have identical seed and expanded canonical-ID lists.
`Agent.run` is graph-discovered at expanded rank 0, fetched, and survives chunk
limits in every arm. Off/normal retain its two final chunks; both claim-on
arms record those chunks in `excluded_evidence` with
`orient_inventory_authoritative_for_structure`, classify the query as
`current_structure`, and reach zero retrieved-context size. This isolates
the regression to claim classification/selection, after discovery and chunk
selection. It is not a seed-set change, a lower byte cap, or structured
answer rendering.

The coarse `evidence_trace` labels the claim-on loss `dropped_by_reranker`
even though reranking is false. That label is misleading here. Attribution
uses the explicit policy exclusion records, matched retrieval lists, and
final manifests, corroborated by the synthetic selection observation.

R1 still has other limits in its successful method-survival controls:
`main` is fetched but lost to chunk-count limits, and the exact `start_cli`
method is lost to the context budget; a CLI file passage does survive.
This comparison verifies a regression in the requested `Agent.run` evidence
and loop explanation, not completion of every cross-file trace obligation.

For R1_method, `current_behavior` preserves the current method. The four
arms have the same final manifests. Nevertheless the model confuses a
historical `Skill.run(request, context, agent_tools)` contract with current
`Agent.run(self, user_input: str)`. The pinned code appends user input,
calls the active provider, dispatches `tool.run(**args)`, appends the tool
result and continues the LLM loop. Source survival is therefore insufficient
to claim explicit-code answer correctness. This shared authority/generation
failure is separate from the deterministic R1 policy loss.

## Decision and validation

The comparison objective is answered: overview correctness improves on this
development corpus, while explicit-path code behavior regresses with claim
selection enabled. Preserve the measured overview gains; any later routing
change must distinguish an inventory question from a code-behavior question
and pass both suites. This record does not implement or prescribe a policy
patch. Normal RAG remains the mode that preserves evidence for the tested
explicit-path question, with the completeness limits above.

Local validation: evaluator/control tests **10 passed**, existing overview
policy tests **14 passed**, Ruff clean, Pyright clean for the new runner/tests.
The audit verifies all **30/30** unique contract requests, unchanged runtime
versions and corpus pins, confirmed effective controls, 4096-byte caps,
reranking off, no fallback, and the reported model for generated answers.

Issue #254 remains open for the demonstrated policy regression and the
separate historical seed-set discrepancy. The latter was not investigated
or assigned a cause by this comparison. Held-out generalization remains
separate work under #243 and ADR-054.
