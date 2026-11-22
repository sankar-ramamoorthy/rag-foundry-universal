---
title: "Restart handoff for large-file inventory and intent recognition"
date: 2026-11-18
type: note
status: proposed
tags: [phase-6, inventory, intent-recognition, handoff]
related:
  - "[Evidence-aware router proposal](/DOCS/proposals/2026-11-17-evidence-aware-execution-router.md)"
  - "[Source navigation contract](/DOCS/architecture/source-navigation-api.md)"
  - "[Existing evaluation protocol](/DOCS/evaluations/evidence-aware-router/protocol.md)"
---

# Restart prompt

> Read CLAUDE.md and DOCS/notes/2026-11-18-inventory-router-restart.md. Resume the design discussion from the bounded inventory acceptance criteria and the offline router evaluation. Keep implementation and issue filing pending my decision.

## Large-file inventory

The owner reported successful automatic inventory for `codebase_utils.py`, apparent success for `ingest.py`, and `READ_TOO_LARGE` for `codebase_ingest.py`. The review inspected the local checkout only. Its `ingestion_service/src/api/v1/codebase_ingest.py` has 735 lines, 11 module-level functions, and 15 definitions including methods and nested functions. `_background_ingest_repo` spans lines 459–648. The existing executor asks for a whole file and the source API caps a read at 500 lines. [Executor](/rag_orchestrator/src/core/execution_policy.py) · [Source API](/DOCS/architecture/source-navigation-api.md)

Proposed acceptance criterion for a dedicated issue: automatic inventory on the matching indexed revision returns the same qualified names and spans as a whole-module AST parse, with zero model calls. Read from line 1, follow `next_start_line`, validate identity, generation and contiguous coverage through EOF, then parse the assembled text once. Respect request budgets and distinguish stale, incomplete and budget-limited outcomes. The formatter currently uses the last evidence record's digest; a paged inventory needs a digest for the assembled text. A structural index is another candidate if equivalent coverage can be demonstrated. [Formatter and recognizer](/rag_orchestrator/src/core/inventory_query.py)

## Intent recognition

The owner's draft separates entity extraction, intent recognition and execution policy. Preserve explicit RAG mode. A clear inventory can use deterministic execution; explanation can use ordinary RAG. Clarify when competing interpretations materially change the answer or multiple paths fit. Investigation requires caller authorization, an identified material evidence gap and an available action that could repair it. Classifier outages should preserve the existing recognizer-then-RAG behavior and leave a diagnostic. Record entities, proposed intent, classifier output and actual route in `retrieval_plan`.

The local regex spot check recognized “What functions are in ingest.py?” and “Which functions does ingest.py define?” It missed “Give me a function inventory for ingest.py” and “In ingest.py, what functions are defined?” It declined calls, filtered definitions and list-plus-explanation examples. Ordinary RAG had previously failed a straightforward inventory question according to the owner, so missed inventories carry a quality cost.

Proposed offline comparison under Phase 6 / #382:

1. Compare the current regex baseline, `mxbai-embed-large` prototype embeddings, and a constrained existing local LLM independently against the same labelled requests. Include typos, absent and multiple entities, defined/called/imported distinctions, filters, ambiguity and compound requests. Hold out whole phrasing families.
2. Label the entity, scope and answer requirements. “List and explain each function” requires both complete discovery and grounded explanations. Supply the human labels directly to the executor in a control run to distinguish execution failures from recognition errors.
3. Score intent, completed answers, incorrect deterministic routes, missed inventories, needless clarification or RAG fallback, false investigation escalation, latency and model/embedding cost. Measure query embedding latency even with cached prototypes. Test calibration on held-out data before considering a similarity threshold.
4. Replay identical questions under different permissions and evidence states. The controller must enforce investigation authority even with a confidently wrong classifier. Astra recommended using verified large-file inventory as the first end-to-end evaluation case. Classifier choice remains open.

## Owner decision

The session produced a design review and local spot checks. Issue filing, the labelled dataset, comparative runs and implementation are pending. The suggested sequence is a dedicated bounded-read issue, then an offline recognition comparison using its verified executor. The owner requires an issue before code and an accepted ADR for production router behavior.
