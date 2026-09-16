# Design decisions: bounded ingestion memory

Tracking issue: #160
Status: Amended after September 16 independent audit
Source: [design review](/DOCS/audit/2026-09-16-bounded-ingestion-memory-design-review.md)

- Explicit helper-scope exit ends graph ownership; removing a parameter does not.
- Bound pages, artifact bytes, chunk count and chunk bytes independently.
  Actual chunker probe: 143 chunks from one 128000-character node.
- Reject out-of-envelope artifacts before Python text loading. No silent
  truncation or changed successful-output semantics.
- Preserve document-local indices explicitly across persistence calls; existing
  persist_batch resets its counter each call, requiring an interface extension.
- Scope pages/count to repository plus attempt; coordinate #161/#166.
- Reuse suffix-derived language without a schema migration.
- Remove the whole-repo canonical-map dependency from this path.
- Partial commits survive interruption. No checkpoint/resume guarantee.
- Text references inside records do not necessarily copy text. Embedder-local
  truncated texts normally expire before persistence records are built.
  Whole-repo vector retention is confirmed; exact multiplicative RSS is not.
- Verify normalized content, not UUID equality or node/vector count equality.
- Measure current RSS by stage and whole-process high-water separately.

The original node-only slice design and one-slice retry claim are superseded
by [spec](./spec.md) and [plan](./plan.md).
