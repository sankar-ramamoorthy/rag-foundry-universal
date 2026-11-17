---
title: "#379 read-only PostgreSQL source-range assessment protocol"
date: 2026-11-16
type: evaluation
status: frozen
summary: "Fixed after metadata-only inventory and before timed range runs. Real stored sources only; no production fixtures, cache eviction or deployment."
tags: [ag0, source-navigation, postgres, performance, issue-379]
related:
  - "[Issue #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[ADR-055 supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md)"
---

# #379 PostgreSQL bounded-range assessment

Owner authorization: read-only assessment against the actual Linux database;
no endpoint implementation or production data modification. Tracking: Phase 6 /
AG / AG0, #379. This is infrastructure performance evidence, not an answer-quality
experiment or held-out retrieval evaluation.

## Fixed sample and queries

Inventory file-identity rows with supported code-source doc types and non-null
text in repositories having a single node owner whose ingestion is completed.
Record decoded UTF-8 bytes, physical column size, compression, generation and
source commit. A preliminary metadata-only probe found 5,640 module records,
largest 618,498 bytes, none above 4 MiB; do not manufacture missing large samples.

Choose the largest eligible source; files nearest 8 KiB and 64 KiB; the largest
uncompressed source; and every eligible `codebase_utils.py` module. Deduplicate
by repository/path. Selection is automatic, not based on benchmark results.

For each sample, record a first-observed `EXPLAIN ANALYZE` for its initial
32,768-character window. Then fetch full stored text once as a correctness
oracle, deriving 100-line early, middle and late ranges (clamped at EOF).
Compare five sequential repetitions of:

1. Exact character substring with precomputed offset: the lower-cost comparator
   given an offset oracle, not an implementation of line lookup.
2. 32,768-character SQL windows scanned from the start to locate the requested
   lines. Retain only requested characters, with a 128 KiB output cap and five-
   second logical-read deadline. Count all calls and transferred text bytes.
3. Full SQL line-array construction and slicing: a deliberately rejected
   comparator that may save transfer but materializes all lines server-side.
4. Full-source transfer and local slicing: a deliberately unbounded comparator.

All results must equal the exact LF-based stored-text oracle. Record query plans
with ANALYZE, BUFFERS and TIMING OFF for single-query comparators and a target
window. The latter is not the cost of the complete multi-query scanner.

## Read-only and workload controls

Connection defaults enforce read-only transactions, five-second statement
timeout, one-second lock timeout, and 30-second idle-in-transaction timeout.
Use repeatable-read isolation per file; verify its ready owner in that snapshot
and in a fresh transaction after the measurement. No DDL, DML, extensions,
configuration persistence, server restart, cache flush, parallel load or fixtures.
Stop on timeout/correctness failure rather than increase production budgets.

## Measurements and interpretation

Record client elapsed time including Python tracing, Python traced peak
allocations, UTF-8 text bytes transferred, number of round trips, PostgreSQL
execution/planning time and buffer hits/reads. Capture own-session backend
memory-context totals before/after if permitted; these are not transient peaks.
Python tracing excludes native driver/libpq allocations and does not represent
process RSS. Remote backend peak RSS is unmeasured; do not infer it from a plan.

True cold-cache timings are unavailable: metadata probes, other workloads and
the correctness oracle can warm storage. Label first observed access separately
from repeated warmed reads; buffer misses do not distinguish disk from OS cache.
Do not evict production caches. Five repetitions are descriptive, not enough for
tail-latency or capacity claims; fixed query order can introduce bias.

Record PostgreSQL version/settings and local, main, deployed-runtime and ingested
source commits where accessible; unknowns stay explicit. No address, credential
or source body goes in captures. Record source hashes and identities instead.
Use PostgreSQL 15.15 documentation and matching upstream code to explain TOAST
behavior, clearly separating that interpretation from instrumented measurements.

## Decision gate

Report practicality at measured sizes, early/late cost, transfer and memory
limits, and whether the proposed contract needs revision. Files above 4 MiB
cannot pass a live-size acceptance gate when absent; record that limitation.
No endpoint implementation follows automatically from this assessment.
