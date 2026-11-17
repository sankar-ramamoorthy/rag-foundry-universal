---
title: "ADR-055 supplement: generation-aware source navigation"
date: 2026-11-16
type: adr
status: accepted
summary: "Owner-approved direction and measured execution limits, implemented under #379. File navigation is distinct from deferred #282 batch/function-node access; production deployment remains operator-owned."
tags: [source-navigation, ag0, ingestion-service, source-provenance]
related:
  - "[Source Navigation API #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[ADR-055: bounded node-text access](/DOCS/adr/ADR-055-node-text-read-endpoint.md)"
  - "[Source Navigation API contract](/DOCS/architecture/source-navigation-api.md)"
  - "[Initial AG0 issue draft](/DOCS/proposals/2026-11-16-ag0-source-navigation-issue.md)"
  - "[Issue #282](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/282)"
  - "[Issue #361](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/361)"
  - "[Phase 6 roadmap](/DOCS/audit/07-Roadmap.md)"
---

# ADR-055 supplement: generation-aware source navigation

The owner approved this architectural direction on 2026-11-16. This is a
supplement to ADR-055, not a claim that either API has shipped. The work is
filed as [#379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379),
with the [#282 reconciliation](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/282#issuecomment-6937842241)
posted. After reviewing the [read-only Linux PostgreSQL assessment](/DOCS/test_results/2026-11-16-379-postgresql-source-ranges.md),
the owner explicitly accepted its adjusted limits and authorized implementation
of #379, tests, documentation, commits and merge, with no Linux deployment.
The [API contract](/DOCS/architecture/source-navigation-api.md) is authoritative
for the implemented request/response behavior. The initial draft is historical.

## Decision

Prioritize deterministic file discovery and stored-source reads before adding
an investigation agent. Deliver `find_files` and `read_source` in
`ingestion_service`, using existing persisted artifacts. Place the issue under
Phase 6 / AG / AG0; use the roadmap rather than GitHub Milestones, per
constitution Principle VI and the owner's clarification.

No new source store, schema expansion, service, database or framework is part
of this work. `find_symbols`, `search_code`, model tools, agent orchestration,
and changes to the RAG answering path remain separate work.

### Relationship to ADR-055 and #282

Retain #282 as the deferred, distinct batch/canonical-ID node-text capability
for the statement-level E1 experiment. Its function-node and batch access are
not delivered by this file-only API. Its experiment-specific start gate
remains in force. Do not implement both API surfaces in AG0 or close #282 as
completed by AG0.

Both capabilities must use common repository/generation validation and
stored-text primitives when implemented. This supplement adopts ADR-055's
no-completed-generation `404` and ready-generation mismatch `409` conventions.
The later batch endpoint retains its own envelope; source text, UTF-8 hash
meaning, provenance and limits policy must agree with the file API. The
snapshot-local generation check strengthens ADR-055's resolver description:
validation and data reads must share a read-only repeatable-read snapshot,
rather than use independent resolver and fetch transactions.

#361 continues to track end-to-end RAG discovery/delivery diagnostics. Adding
an API does not resolve that issue or demonstrate improved answer quality.

### Generation and source semantics

Only the current completed generation is supported. Existing node persistence
overwrites/retags surviving records and deletes removed artifacts; historical
source snapshots are not available as a product guarantee. An in-flight read
can finish coherently in the snapshot opened before a concurrent replacement
or deletion. Subsequent requests must not serve obsolete generations as current.

Return stored decoded text, preserving its characters and line endings. Do
not claim byte identity with Git. The existing raw-file `content_hash` is not
a stored-text hash. Bounded reads always hash their returned text; whole-file
hash and total line count may be unknown on a range response, explicitly
represented as null. Complete-file responses provide both.

### Readable file identification

Use exact file identity (`canonical_id = relative_path`), the supported code
extractors' source doc-type allowlist, and non-null text, all constrained to
the selected repository and generation. Do not infer a module from
`symbol_path IS NULL`: current lowering does not populate that column for
symbols either. An empty string in an eligible module is a valid empty file.
Structural inventory's `file`/`manifest` records are discoverable but have no
readable source under this contract. Unknown legacy types fail closed.

These distinctions require contract tests. This is an API eligibility rule
over the existing schema, not a new persisted artifact-kind model.

### Large artifacts and limits

Withdraw the proposed blanket 4 MiB source-artifact cap. A small range should
not be rejected merely because the containing file is large. PostgreSQL
supports character-oriented substring projection; that permits bounded data
transfer, but does not establish bounded internal decompression or cheap
late-line lookup. See the
[PostgreSQL string-function documentation](https://www.postgresql.org/docs/current/functions-string.html).

Before endpoint implementation, measure a database-window strategy on the
project's PostgreSQL version, including compressed/TOAST text larger than
4 MiB and early/late line ranges. Bound application allocations, returned
text, serialized response size and execution time. Do not build a whole-file
line array. The issue draft proposes 500 lines, 128 KiB returned text and
256 KiB serialized responses; these are starting values, not measured capacity.
The owner accepted a 1 MiB cumulative source-scan transfer budget, at most 32
data queries and a five-second overall logical-operation deadline in addition
to those response limits. Exceeding them fails explicitly without partial text.
There is no blanket artifact cap. The local PostgreSQL integration suite now
tests a 5 MiB source: an early range succeeds and a late range exceeds the scan
budget. Future policy changes require evidence, not silent limit changes.

## Evidence and limits

Code assessment at `87379aa` checked the DocumentNode model, graph lowering,
codebase persistence, structural inventory, extractors, generation resolver
and read-snapshot implementation. The linked assessment records the subsequent
read-only Linux measurements and stored-source verification. Local implementation
and isolated PostgreSQL testing followed the owner's separate approval; no
production endpoint deployment or live HTTP verification is claimed.

The owner's `codebase_utils.py` function-inventory query received unrelated
script/test evidence and an abstention. That motivates deterministic access;
the initial symptom alone did not establish deployed retention. The later
assessment independently verified that stored module against its Git revision.
Generation-pinned HTTP verification remains a post-deployment operator task.
