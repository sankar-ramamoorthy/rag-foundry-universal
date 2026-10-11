---
title: "Issue 254 local discovery and chunk-limit diagnostic checkpoint"
date: 2026-10-11
type: test-result
status: partial-diagnostic-checkpoint
tags: [retrieval, diagnostics, evidence-survival, issue-254]
related:
  - "[Issue #254](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/254)"
  - "[Diagnostic specification](/specs/009-evidence-delivery-diagnostics/spec.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Prior live evaluation](/DOCS/test_results/2026-10-10-py-coding-agent-real-repo-verification.md)"
---

# Local diagnostic checkpoint

Work is on `diagnostic/254-discovery-and-chunk-limits`, based on `6e558d1`.
This checkpoint adds diagnostic instrumentation and synthetic tests. It does
not establish a retrieval-quality improvement or close #254.

## Verified discovery mechanism

`hybrid_retrieve()` constructs canonical lookup requests from the union of
vector seeds and graph-expanded IDs. A symbol named in the question does not
independently enter that union. Synthetic tests contain an indexed
`pkg/engine.py#Engine.execute` method and a seed that calls an unresolved
`EXTERNAL_SYMBOL:engine.execute`. The exact method remains undiscovered with
either its full canonical ID or qualified name in the question. Ambiguous
and missing-name query variants do not introduce a fallback lookup. A resolved
CALL edge to the same method makes it discoverable and fetchable; changing
the ready generation aborts the request with HTTP 409.

This characterizes the existing hybrid discovery path. Overview mode shares
that path. Its later canonical policy selects fixed purpose/architecture
sources, while exact-source preservation operates on already selected chunks;
neither provides arbitrary named-symbol discovery.

## Diagnostic instrumentation

Requests supplying `trace_canonical_ids` now receive optional
`retrieval_plan.chunk_selection_trace` rows for the first exclusion of each
tracked retrieved chunk. Rows contain identities, stored ordinal, fetch
position, stage input position, document position where applicable, limiting
rule, limit, consumed capacity, evaluation status, and byte/token cost when
measured. They do not duplicate source text.

The instrumentation distinguishes plan per-document slicing, adapter
per-document slicing, explicit filtering, global chunk-count early stop,
optional adapter token stop, and final context bytes. Reranker and overview
policy exclusions have separate stage labels. Policy-internal exclusion
subrules are still reported by the existing policy diagnostics; this patch
does not decompose policy prepending/allocation into new individual rules.

When a global stop occurs, later tracked identities are recorded as unvisited
tail exclusions. Their filters and token callbacks are not evaluated. A
synthetic case with 50 earlier accepted chunks and a late three-chunk document
confirms `max_total_chunks=50` as that fixture's actual loss branch, despite
the per-document limit being five. Service tests confirm trace-on/off answer,
source, and final-context-manifest parity for count and byte exclusions.

The earlier live R2 trace still establishes only
`dropped_by_chunk_count_limits`. Its global 50-chunk explanation remains an
inference. No new instrumented live replay was performed at this checkpoint.

## Validation and remaining gates

Local orchestrator tests excluding Docker/integration tests passed
(`386 passed, 1 deselected`), including
the existing #240 structured HTTP and exact-source checks. Ruff and Pyright
passed on all changed Python files. Pyright used the root `.venv` interpreter
to resolve installed dependencies. The initial focused test failed before the
new tracing module existed; the implemented diagnostics satisfy that contract.

The pinned R1/R2 replay, actual replay allocation report, and any behavioral
correction remain pending. No production deployment, re-ingestion, frozen
11-case live rerun, or fresh held-out evaluation was performed. Under ADR-054,
the synthetic fixtures and known repositories are development/diagnostic data.
See the [remaining tasks](/specs/009-evidence-delivery-diagnostics/tasks.md).
