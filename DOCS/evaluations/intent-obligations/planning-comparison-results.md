---
title: "Local planning comparison results for #398"
date: 2026-11-18
type: evaluation
status: experimental
tags: [phase-6, routing, evaluation, local-models]
related:
  - "[Protocol](protocol.md)"
  - "[Label change log](label-changes.md)"
  - "[Frozen manifest](planning-run-manifest.json)"
  - "[Phase 6 checkpoint](phase-6-checkpoint.md)"
  - "[Experiment issue #398](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/398)"
---

# Local planning comparison results

Run `398-planning-local-01`, authorized by the repository owner for manifest SHA-256 `0e24106d90551df50e7f064620ac963d65d3f4a8afb5efc3a8c2947a92e3de3b`. The checkout was clean at `6dd97a6`, with runtime commit `f928b3a` and request-pack digest `bc6236ce41fc9cdfa57bebd41e0c050bd93f2daf2d42f4ac4848c67b2b4ceaef`. Models were `qwen2.5:1.5b` and `mxbai-embed-large:latest` on local Ollama 0.40.16, with zero hosted spend. All 72 scheduled requests (42 embeddings, 30 generations) returned HTTP responses. Model digests matched before and after collection. Raw captures are indexed in [raw-index.json](/DOCS/test_results/raw-index.json) under `398/`.

This is a development comparison on exposed questions and a pinned fixture. The labels were authored by the experiment and not independently adjudicated. The embedding arm saw prototypes that share intents with part of the held-out set, and the LLM arm was zero-shot. See the [protocol caveats](protocol.md#comparison-caveats). These results do not establish production reliability and do not select a router.

## Held-out results

25 held-out questions, normal permissions, one capture each.

| Measure | Regex | Embeddings | Local LLM | Supplied labels |
| --- | --- | --- | --- | --- |
| Expected route | 14 | 15 | 11 | 25 |
| Intent set exact | 2 | 11 | 6 | 25 |
| Scope exact | 4 | 18 | 13 | 25 |
| Obligation set exact | 2 | 7 | 1 | 25 |
| Entities exact | 25 | 25 | 14 | 25 |
| Ordered strategy exact | 2 | 11 | 1 | 25 |
| Tool set exact, order ignored | 2 | 11 | 1 | 25 |
| Valid tool order | 25 | 25 | 18 | 25 |
| Delivered all verifiable obligations (of 9) | 1 | 7 | 2 | 9 |
| Understood and delivered (of 9) | 1 | 2 | 1 | 9 |
| Demonstrated complete answers | 1 | 5 | 2 | 7 |
| Incorrect deterministic route | 0 | 10 | 0 | 0 |
| Missed inventory (of 7 expected) | 6 | 0 | 6 | 0 |
| Needless clarification | 0 | 0 | 9 | 0 |
| Needless RAG | 11 | 0 | 5 | 0 |
| False investigation | 0 | 0 | 0 | 0 |
| Classifier outages (regex fallback) | 0 | 0 | 9 | 0 |

"Verifiable" means the supplied-label control satisfied the obligation with the executor. Nine held-out questions qualify. "Understood and delivered" also requires exact intent, entities, scope, obligations and strategy. Capability and ordered-strategy scores are equal for every arm here, so no valid-but-reordered plan was lost to the ordered metric.

## Findings

1. **Embeddings understood far more of the request than the regex** (intent 11 against 2, obligations 7 against 2) and never missed an inventory. Their route accuracy gain is small (15 against 14) because they made ten incorrect deterministic selections: three groups. Direction: h02, h04 and h23 (called or imported, not defined) went to inventory, and h16 (called) went to the compound route. Ambiguity: h12 (unclear) and h14 (which file) went to inventory instead of clarification. Compound mix-ups: h06, h15 and h25 (plain lists) got an unrequested explanation, and h05 (list plus description) lost its explanation. The nearest-prototype choice carries no notion of direction or ambiguity.
2. **Embedding delivery overstates understanding.** Seven of nine verifiable cases were delivered, but only two with every plan field exact. Over-selecting inventory satisfies a definitions obligation by accident. Judge it by the joint score.
3. **The 1.5B model was not usable as configured.** Ten of 30 generations stopped at the 256-token limit (`done_reason: length`). Nine of them were held-out questions and became "incomplete LLM response" outages that fell back to the regex. The remaining outputs were cautious and often wrong: obligations exact on 1/25, entities exact on 14/25, nine needless clarifications and six missed inventories. It made no incorrect deterministic selection.
4. **Nothing authorized investigation.** There were no false investigations in any arm.
5. **The ordered-strategy metric was not the main limit.** Valid ordering was 25/25 for regex and embeddings and 18/25 for the LLM, whose failures were mostly truncation. The tool sets themselves were wrong.

## Latency

Per request, including model loading and switching (no warm-up, alternating embed and generate calls, CPU only). Prototype setup excluded. Not steady state.

| Arm | Median | Max |
| --- | --- | --- |
| Embedding | 156 ms | 260 ms |
| Local LLM | 9.1 s | 28.4 s |

The LLM arm produced 4,304 output tokens over 30 calls. Electricity cost is unknown. Regex recognition runs in microseconds and is in the report rows.

## What this does and does not support

- Single-pass request understanding from embeddings is materially better than the regex at about 150 ms per question, with a specific, correctable weakness in direction and ambiguity.
- This setup of a 1.5B model with a 256-token cap cannot be evaluated further. Whether a larger model or a higher cap would change the result is untested and needs a new manifest.
- No router is selected. Choosing a recognizer, adding an iterative planning loop and any production change remain open and need a held-out set that was not used for development.

## Reproduction

```powershell
cd rag_orchestrator
$env:PYTHONPATH = '..'
..\.venv\Scripts\python.exe -m experiments.intent_obligations --llm-model qwen2.5:1.5b --captures ..\DOCS\test_results\_raw\398\planning-captures.json --output planning-comparison.json
```

Raw captures are git-ignored. If they are absent, the indexed hashes identify what was run, and a rerun needs the collector and the approved manifest.
