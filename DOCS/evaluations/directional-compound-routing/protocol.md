---
title: "Directional semantics and compound obligations: experiment protocol"
date: 2026-11-18
type: evaluation
status: proposed
tags: [phase-6, routing, evaluation, embeddings]
related:
  - "[Issue #400](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/400)"
  - "[#398 results](/DOCS/evaluations/intent-obligations/planning-comparison-results.md)"
  - "[#398 protocol](/DOCS/evaluations/intent-obligations/protocol.md)"
  - "[Evidence-aware router protocol](/DOCS/evaluations/evidence-aware-router/protocol.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Directional semantics and compound obligations

Proposed and unexecuted. This document authorizes no implementation, model call, sealed-set authoring or production change. Each of those is a later step that needs owner approval of a frozen manifest.

## Question

Can a local, embedding-only recognizer tell apart the direction of a code question (defined in a file, called from a file, callers of a symbol, imported by a file) and decompose a compound request (list, explain, cite) well enough that it never selects a wrong deterministic route?

A wrong deterministic route is the costly failure. A fall back to ordinary RAG is a lost optimization, not a wrong answer. The experiment is therefore scored asymmetrically: first, zero wrong deterministic routes, then how much useful inventory it still recovers.

## Evidence from #398

On the 25 held-out development questions the nearest-prototype embedding arm made ten wrong deterministic routes:

| Group | Cases | Behaviour |
| --- | --- | --- |
| Direction | h02, h04, h23, h16 | "called" or "imported" questions routed as inventory or compound |
| Ambiguity | h12, h14 | Unclear or multi-file questions routed as inventory |
| Compound | h05, h06, h15, h25 | Plain lists gained an explanation obligation, and a list-plus-description lost one |

A diagnostic on the captured vectors (no new calls, exposed development data, n=25) checked whether abstaining on a low similarity margin could remove these. It cannot be relied on. Top-1 cosine to a prototype was 0.75-0.99 even for wrong routes. The gap between the best and second-best prototype was 0.00-0.04 for most wrong routes, with a median of 0.015 against 0.030 for the correct ones, and several correct routes had margins near zero (h17 0.000, h19 0.006). The runner-up for most inventory routes was the callee prototype p04, which suggests that "functions in X" and "functions X calls" sit close together in the embedding space. That is a hypothesis about mechanism. It was not tested directly. The consequence for design is that a threshold on similarity or margin is not a safe gate, so this experiment tests structure instead of a cutoff.

## Hypotheses

- **H1 (coverage):** adding minimal-pair prototypes that contrast direction and compound obligations reduces wrong routes without any other change.
- **H2 (factoring):** recognizing direction, scope, explanation, evidence and target clarity as independent facets, each with its own "unsure" class that forces a RAG fallback, removes the coupling that makes one nearest prototype copy all of its facets onto a question.
- **H3 (verification):** requiring agreement from a small lexical cue check before any deterministic route can remove the remaining wrong routes. The cue check can only veto, never select.

Each hypothesis can fail independently. A negative result on all three is a valid outcome and ends this line without a model change.

## Arms

All arms embed each question once with `mxbai-embed-large:latest`, so arms share query captures. There are no generations.

| Arm | Description |
| --- | --- |
| A0 regex | Current inventory recognizer. Production baseline, unchanged. |
| A1 nearest prototype | The #398 embedding arm and prototype library, as the reference. |
| A1+V | A1 plus the cue verifier. |
| A2 contrastive | Nearest prototype over a library extended with minimal-pair prototypes (H1). |
| A3 factored | Per-facet prototype sets with an explicit "unsure" class. Any unsure facet makes the route non-deterministic (H2). |
| A3+V | A3 plus the cue verifier. |
| Control | Supplied labels through the same controller and executor. |

The cue verifier is a fixed lexicon of direction and obligation cues: define or list for definitions, call for callees, who or which calls for callers, import for imports, explain, describe, purpose or walk for explanation, cite, quote, source or passage for evidence. A deterministic route needs the verifier's cues to agree with the predicted facets. Conflict or absence vetoes the route to RAG. Its lexicon is part of the frozen arm and counts toward the tuning budget.

The controller, the eight policy scenarios, the investigation rule (the classifier never authorizes investigation), the executor and the #398 fixture are reused unchanged. The router in `src/` and the production regex are not touched. All experiment code lives under `rag_orchestrator/experiments/`.

## Label glossary

Frozen before any question is authored, so that direction labels do not drift:

- **Definitions:** functions or classes defined in the named file. Intent `inventory`.
- **Callees:** functions that the named file or symbol calls. Intent `calls`.
- **Callers:** places that call the named symbol. Intent `callers`.
- **Imports:** names or modules the named file imports. Intent `imports`.
- **Explain:** purpose or behaviour in prose. A request for a description of each listed function is `inventory` plus `explain`.
- **Evidence:** `source_evidence` only when the question asks for sources, citations, quotations or supporting passages (carried from #398).
- **Ambiguous direction:** "uses", "touches" and "involves" without a direction. The expected route is non-deterministic.
- **Non-deterministic:** the correct outcome is RAG or clarification. Selecting inventory is a wrong deterministic route.

## Case matrix

Cases are authored as minimal-pair groups. A group holds three to four questions that share a target and surface form and differ in one axis value, so a recognizer must change its answer exactly where the label changes.

| Axis | Values |
| --- | --- |
| Direction | definitions, callees, callers, imports, ambiguous |
| Compound | list, explain, list and explain, list and cite, explain and cite |
| Target | one clear file, two files, ambiguous basename, missing file, no target |
| Phrasing family | fronted, passive, polite, shorthand, noun phrase, question word |

Phrasing families stay whole within one split. Roughly one fifth of cases are abstention controls: ambiguous direction, unclear request or ambiguous target. They are scored by the wrong-deterministic rule and are not tuned for.

| Split | Size | Role |
| --- | --- | --- |
| #398 held-out | 25 | Exposed. Regression only |
| Development | about 32 (8 groups of 4) | Authored by the implementer. Used for tuning |
| Sealed | about 64 (16 groups of 4) | Authored independently. One run per frozen arm set |

## Sealed-set procedure (ADR-054)

1. This protocol and the glossary are merged first.
2. The implementer authors the development set and builds the arms, tuning only on the 25 and the development set.
3. An independent author (the owner or a separate agent) writes the sealed questions and labels from the matrix and glossary, without seeing prototype libraries, similarity values or arm outputs. Their hash is committed before the arms freeze. The text is not shown to the implementer before the run.
4. A run manifest freezes the commit, library, lexicon, thresholds, model digest, sealed hash, scoring and spend cap. The owner approves the exact manifest SHA-256.
5. The sealed set is run once. Any change to an arm after the run makes the sealed set development data and requires a fresh set.

At run time the runner executes the frozen code against the sealed file mechanically. This does not make the implementer blind to the questions after the run, which is reported as a limit.

## Tuning budget and stop rule

At most three recorded tuning iterations per arm, each logged with its reason and its effect on the development set, with no change made after any sealed run. If no arm reaches the primary gate on the development set within that budget, the experiment stops and reports. It does not escalate to an LLM arm. A larger model or a higher token cap would be a separate issue and manifest.

## Predeclared gates

Reported per arm on the sealed set, normal permissions, one capture per question.

- **G1, primary:** zero wrong deterministic routes, including abstention controls and entity mismatches (the #398 `incorrect_deterministic` definition). The 25 #398 questions must also show zero. With 64 sealed questions, zero errors gives a 95% upper bound of about 5% (rule of three). G1 is necessary for any adoption claim and is not sufficient.
- **G2, usefulness:** missed inventory at most 30% of expected inventory and compound routes (regex baseline: 6 of 7 on the 25). No question the regex routes correctly may regress.
- **G3, direction:** pair-flip accuracy, meaning the share of minimal pairs where the predicted direction changes exactly when the label changes, reported with exact intent-set accuracy per direction.
- **G4, compound:** precision and recall of the explanation and evidence facets separately. A compound route requires both inventory and explanation to be present.
- **G5, authority:** zero false investigations across all eight scenarios.
- **Cost:** one embedding call per question plus local comparison. Latency reported with the #398 caveats. Total budget at most 400 embedding calls, zero generations, zero hosted spend.

An arm passes the experiment only if it satisfies G1, G2 and G5. G3 and G4 explain why. Missing captures count against an arm and are reported separately.

## Production boundary

The production router stays unchanged. Even a pass is a development result. Adoption needs, in order: a passing sealed run, a fresh held-out repository with a frozen protocol (ADR-054), an ADR, and a separate issue for the router change. Nothing in this experiment is deployed.

## Limits

The development labels are author-written. The fixture is one pinned Python module plus two synthetic files, so file-structure variety is low. The prototype libraries and cue lexicon encode the implementer's judgement of the #398 failures. The sealed set protects arm selection but cannot make a result about this repository transfer to others.
