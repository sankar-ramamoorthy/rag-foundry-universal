---
title: "Phase 6 checkpoint for request understanding and answer verification"
date: 2026-11-18
type: proposal
status: proposed
related:
  - "[Experiment protocol](protocol.md)"
  - "[Experiment issue](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/398)"
---

# Shared obligations across code and document intelligence

Before retrieval, the orchestrator should identify intents, typed entities, answer obligations and an ordered evidence strategy. After retrieval, it should check the evidence and the delivered answer against each obligation. A model may propose a plan. The controller owns execution authority, budgets and the rules for completion.

For a complete inventory with explanations, first establish the set of functions from verified source. Then check that each function has an explanation and that its cited lines support it. For policy comparison, resolve both document versions, identify corresponding provisions and support each reported change with passages from the two versions. Missing pages or uncertain version identity limit the comparison. Reaching a context limit leaves a different kind of gap from finding no support in the available text.

Use the same obligation record and controller in both domains. Code tools can supply definitions, callers, dependencies and source spans. Document tools can supply structure, section references, relationships and page quotations. A simple request may finish in one lookup. An additional action needs a specific open obligation, an available repair, caller authority and remaining budget.

## Sequence

1. Extend the #398 offline experiment to score pre-retrieval analysis and proposed tools independently of the authorized route. Retain the regex and supplied-label controls. Compare models on identical questions before choosing a recognizer.
2. Exercise a bounded evidence-sufficiency loop on two or three cases, beginning with inventory plus explanation. Record the remaining obligation and termination reason on every incomplete answer.
3. Apply the same contracts to document summary and version comparison. Decide production behavior through an ADR after evaluation.

The original experiment is reproducible at `72a02c2`. Its 8/17 regex result is a development diagnostic. Keep the original questions identifiable as the experiment grows. The labels are available for human review before freezing a model run.

## Restart here

The expanded #398 suite has 25 held-out development questions. Under normal permissions, the regex matched the expected route on 14/25, the ordered strategy on 2/25 and the typed entity mentions on 25/25. It recovered one of seven requests requiring executable inventory. Of nine cases in which the supplied-label control could verify at least one obligation, the regex understood the full request and delivered everything verifiable on one. Two compound controls verified the definitions and left explanations and their source support open.

Use the protocol commands with the frozen request pack for the live comparison. Installed local models are `mxbai-embed-large:latest` and `qwen2.5:1.5b`. Resume by checking the run manifest and receipt, then any final capture or partial journal before starting collection. Report accuracy on the same 25 questions, missing cells, latency, usage, avoidable routes, and verified completion. Model selection and document-tool execution remain open.

The runner and labels are frozen at `f928b3a`, after a pre-run label correction that is logged in [label-changes.md](label-changes.md). Source evidence is now an obligation only when the question asks for it. Seven labels changed, no question text changed, and the regex baseline is identical. The scorer also reports order-insensitive capability and dependency-validity scores beside the ordered strategy. The manifest SHA-256 is `0e24106d90551df50e7f064620ac963d65d3f4a8afb5efc3a8c2947a92e3de3b` for its committed UTF-8/LF bytes. It supersedes `43338571...`, which was never approved. The owner approved this manifest and the labels on 2026-11-18, and the live comparison ran. See the [results](planning-comparison-results.md). Next decisions: whether to test a larger local model or higher token cap under a new manifest, and how to address embedding direction and ambiguity errors. The run makes 42 embedding requests and 30 classification requests on loopback with zero hosted spend. Read the protocol's comparison caveats on prompting asymmetry, entity resolution and CPU timing before interpreting results. [Frozen manifest](planning-run-manifest.json) · [Capture index](/DOCS/test_results/raw-index.json)
