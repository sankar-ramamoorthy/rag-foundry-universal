---
title: "Experimental execution policy vertical slice"
date: 2026-11-17
type: test-result
status: complete
tags: [phase-6, execution-policy, orchestrator]
related:
  - "[Implementation issue #384](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/384)"
  - "[Experimental specification](/specs/009-evidence-aware-execution-router/spec.md)"
---

# Phase 6 experimental execution policy

Python callers explicitly invoke `await run_execution_policy(request, propose)`
in [execution_policy.py](/rag_orchestrator/src/core/execution_policy.py).
`Request` pins repository and generation UUIDs, task family, strategy ceiling
and resource caps. Inventory accepts a path or unique basename. For tracing,
the injected asynchronous proposer takes a JSON prompt and remaining output
byte allowance and returns one JSON repair action or a cited finish response.
The service function returns evidence, decisions, unresolved work, counters,
completion and termination reason. Existing HTTP callers continue to use
`run_rag`. Both paths call the same passage selection and manifest code.

From `rag_orchestrator/`, run `python -m pytest -q tests/test_execution_policy.py`
in the project test environment. Eleven mocked cases exercise the normal entry
point and adapters. Ordinary RAG and search returned identical ordered passages,
hashes and text under matched defaults. The evidence tool made zero answer
generation calls. Scope overrides, wrong-repository data, changed generations,
duplicate actions and call/byte caps produced explicit stops.

The inventory fixture reads this checkout's `codebase_utils.py` via a mocked
source response and verifies 13 functions with one tool call and zero model
calls. The H-3 fixture uses the original question and a scripted retrieval hit
for the Mealie export route. The controller reads the pinned handler excerpt
and reports its background cleanup callback, citing the second tool record.
It reports the JSON/ZIP selection branch as unresolved. This exercises the
transport and control flow with two tool and two mock model calls. Retrieval
quality, independent discovery and hosted-model behavior remain unmeasured.

The implementation enforces wall time, tool and model call counts and serialized
model input/output bytes. The byte budget applies to the mocked proposer.
Provider token accounting, spend reservations and model identity verification
remain prerequisites for hosted experiments. Inventory requires a complete
source response. The initial finish contract checks citation IDs and leaves
semantic support for independent evaluation.
