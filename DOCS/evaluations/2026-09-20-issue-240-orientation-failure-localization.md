---
title: "Issue #240: orientation failure-localization evaluation"
date: 2026-09-20
type: evaluation-protocol
status: preregistered
tags: [evaluation, orientation, retrieval, graph, inventory, provenance, generation]
related:
  - "[[../notes/20260906-repository-understanding-trace-and-structural-artifacts]]"
  - "[[../audit/2026-09-07-repository-intelligence-architecture-audit]]"
---

# Purpose

Determine which boundary causes each ORIENT failure. This is a small
failure-localization evaluation, not an aggregate answer-quality benchmark.
The same case must expose retrieval evidence, the deterministic ORIENT
response, the final-context manifest, provenance diagnostics, and a
pre-registered answer check.

## Failure decision table

| Order | Class | Evidence of failure |
| --- | --- | --- |
| 1 | `seed_retrieval` | Requested target is absent from both vector seeds and graph expansion. |
| 2 | `graph_resolution` | A graph-target anchor is present, but the expected target is not found by graph expansion. |
| 3 | `missing_structural_inventory` | A required ORIENT facet is empty, unknown, or explicitly covered by a gap. |
| 4 | `authority_evidence` | Evidence reaches final context, but provenance diagnostics flags the overview claim. |
| 5 | `generation` | Required authoritative evidence reaches context, but the answer misses a required term. |

The first failing boundary wins. A case is `no_failure` only when its required
evidence and answer terms pass. The classifier lives in
`rag_orchestrator/src/retrieval/orientation_failure.py` and has five isolated
controls in `rag_orchestrator/tests/test_orientation_failure.py`.

## Controlled cases

Use one case for each class, keeping all non-target stages healthy:

1. **Seed control:** mark the structural-map target absent from both seed and
   graph sets.
2. **Graph control:** provide the anchor as a seed, but omit the expected
   service/inventory target from graph expansion.
3. **Inventory control:** return a valid response with an empty required
   `services` facet and no retrieval/generation claim.
4. **Authority control:** place an embedded fixture subject in the final
   context and run the `repository_overview` provenance diagnostic.
5. **Generation control:** provide current selected-repository evidence and
   deliberately omit one required answer term.

For a live run, record the repository id, generation id, runtime revision,
corpus revision, model/provider, query, target canonical ids, full evidence
trace, ORIENT JSON, final-context manifest, and answer. Do not classify a live
failure from prose alone.

## Interpretation gate

If the five controls reproduce their expected labels and real failures map to
one label without an unclassified remainder, use the label to choose the next
engineering experiment. Do not change retrieval, graph resolution, inventory,
provenance policy, or prompting based on a single end-to-end answer.
