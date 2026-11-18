---
title: "Label change log for the #398 planning comparison"
date: 2026-11-18
type: evaluation
status: experimental
tags: [phase-6, routing, evaluation]
related:
  - "[Protocol](protocol.md)"
  - "[Cases](cases.csv)"
---

# Label changes before the first live model capture

These corrections were made at the owner's direction after a consistency review of the labels frozen at `e1354b6`, and before any embedding or LLM capture existed. No question text changed. All 25 held-out questions keep their IDs, families and wording. Only the labels in the `obligations` column changed. The manifest hash, request-pack digest and prompt changed with them. The earlier manifest (`43338571…`) is superseded and was never approved.

## Rule

`source_evidence` is an obligation only when the question asks for sources, citations, quotations or supporting passages. A question that asks for callers, impact, a comparison, a summary or per-function explanations does not request sources unless it says so. Grounding is still how any synthesized answer is judged, but it is not a separate obligation. The same rule holds for prototypes and held-out cases.

## Changes

| Case | Split | Question | Before | After | Reason |
| --- | --- | --- | --- | --- | --- |
| p09 | prototype | Which functions call `save_repo`? | callers, source_evidence | callers | Sources not requested |
| p10 | prototype | Compare old-policy.pdf and new-policy.pdf. | changes, source_evidence | changes | Sources not requested |
| p11 | prototype | What breaks if I remove `save_repo`? | dependencies, source_evidence | dependencies | Sources not requested |
| p12 | prototype | Summarize contract.pdf. | summary, source_evidence | summary | Sources not requested |
| h18 | held-out | Who calls `save_repo` from codebase_ingest.py? | callers, source_evidence | callers | Sources not requested; now matches h19 |
| p03 | prototype | List and explain every function in codebase_ingest.py. | definitions, explanation_per_function, source_evidence | definitions, explanation_per_function | Directly related: same rule |
| h05 | held-out | codebase_ingest.py function names plus a description of each please. | definitions, explanation_per_function, source_evidence | definitions, explanation_per_function | Directly related: same rule |

Unchanged on the same rule: h20 ("with quotations"), h21 ("Cite the affected code"), h22 ("source-backed account") and h24 ("supporting passages") keep `source_evidence`. Strategy and route labels are unchanged for every case.

## Related code and prompt changes

- The router accepts a compound inventory with or without `source_evidence`, so p03 and h05 still expect `inventory_then_rag`.
- The LLM system prompt no longer says "for list and explain use … source_evidence". It now says to add `source_evidence` only on an explicit request, and to list tools in dependency order. The request-pack digest is `bc6236ce41fc9cdfa57bebd41e0c050bd93f2daf2d42f4ac4848c67b2b4ceaef`.
- Routing to inventory now tests the tool set plus dependency validity rather than an exact ordered tuple. Otherwise a correct tool set in a different valid order would be misrouted for ordering alone.
- New order-insensitive scores sit beside the unchanged ordered `strategy_correct`: `capabilities_correct`, `order_valid` and `understood_capabilities_and_delivered_verifiable`.

## Effect on the regex baseline

Recomputed on the same 25 held-out questions under normal permissions: route 14/25, ordered strategy 2/25, entities 25/25, obligations 2/25, intents 2/25, capability set 2/25, order valid 25/25, delivered all verifiable 1/9, understood and delivered 1/9. Every pre-existing figure is identical to the pre-correction run, so the label changes alter no regex outcome. They matter to the embedding and LLM arms, which are no longer penalized for omitting an unrequested obligation. The supplied-label control still delivers all verifiable obligations in 9/9 cases and a complete answer in 7/25.
