# Specification: exact-symbol discovery and chunk-limit diagnostics

**Issue:** #254
**Branch:** `diagnostic/254-discovery-and-chunk-limits`
**Status:** Local diagnostic checkpoint; pinned replay pending

## Scope and contract

Measure discovery separately from selection. Existing vector/graph retrieval,
authority, generation fences, chunk limits, and byte budgets remain the
baseline. A named canonical ID is not currently an independent retrieval seed;
tests must expose that behavior without pretending that source absence follows
from a retrieval miss. A behavioral correction requires a separate decision
based on the diagnosed mechanism.

## Discovery scenarios

Use a synthetic indexed method disconnected from the semantic seed. Test a
full canonical ID, qualified symbol, ambiguous same-name methods, and a missing
symbol. Record whether canonical lookup requests the target, whether traversal
reaches it, and whether it is fetched. Add a reachable control and a changed
generation case. An unresolved external CALL must not count as the indexed
method. These tests characterize the current discovery contract; they do not
encode an answer about py-coding-agent.

## Selection scenarios

When `trace_canonical_ids` is supplied, record the first actual exclusion of
each tracked retrieved chunk. Include canonical/document/chunk IDs, stored
ordinal, fetch position, stage input position, document position, rule, limit,
and consumed capacity. Positions are zero-based within the named stage.

Separate plan per-document slicing, adapter per-document slicing, filtering,
global count early stop, reranking, overview policy, and final byte budgeting.
For a global early stop, unvisited tail chunks are excluded by that stop; do
not evaluate their filters or claim they were individually considered. Traces
contain identities and accounting only, never copied source text.

Tests isolate each rule, equality boundaries, and a late three-chunk document
behind 50 accepted chunks with a per-document limit of five. Verify trace-on
and trace-off output identity/order equivalence and first-loss stability.

## Evaluation gate

Replay the saved R1/R2 requests locally against the pinned ready generation
without changing their retrieval settings. Record runtime, source commit,
generation, and whether the local candidate differs from the deployed runtime.
Keep historical observations and new replay findings distinct. A local replay
cannot retroactively prove the exact branch taken in the historical request.

Apply [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md).
These fixtures and both known repositories are development/diagnostic data.
Fresh held-out quality evaluation follows a behavioral correction and a
separately frozen protocol; diagnostic parity is not a generalization claim.
