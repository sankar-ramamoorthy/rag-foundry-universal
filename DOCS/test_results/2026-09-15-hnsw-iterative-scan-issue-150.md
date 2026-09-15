---
title: "HNSW Iterative Scan Fix: Recall/Latency Evidence for Issue #150"
date: 2026-09-15
type: test-result
status: complete
tags:
  - rag
  - evaluation
  - retrieval
  - vector-store
  - pgvector
related:
  - "[Issue #150](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/150)"
  - "[Issue #149](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/149)"
  - "[Retrieval Technique Decision Gates](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md)"
---

# HNSW Iterative Scan Fix: Recall/Latency Evidence for Issue #150

**Status: complete.** Measured directly against the live database
(`vector_chunks`, 62,975 code chunks across 5 repos sharing one HNSW
index, `ix_vector_chunks_hnsw`, pgvector 0.8.1).

## The bug (issue #150)

A `repo_id`-filtered `similarity_search` call can silently return far
fewer rows than the requested `k`, with no error. `EXPLAIN ANALYZE`
against TradeForge's Candidate 6 query (`repo_id
d2fcf1f0-b934-5b74-b7ac-564dd8759d81`, filtered on `repo_id` +
`source_type='code'`, 13,911 of the 62,975 total chunks) showed the
query plan using `Index Scan using ix_vector_chunks_hnsw` and capping at
**28 rows** for every `LIMIT` from 28 up to 290 — only at `LIMIT=300` did
Postgres's planner abandon the HNSW index scan for a full scan, which
correctly returned all 300 rows. Every `LIMIT` value this codebase
actually uses today (`top_k=20`, and issue #142's widened pool of 100)
falls inside the broken range.

## The fix

pgvector 0.8's iterative index scan feature, applied only to filtered
searches (`PgVectorStore.similarity_search`, `vector_store_service/src/
core/vectorstore/pgvector_store.py`):

```sql
SET LOCAL hnsw.iterative_scan = relaxed_order;
SET LOCAL hnsw.max_scan_tuples = 20000;
```

## Recall measurement

Same query, `repo_id`-filtered, `LIMIT 100` (representative of the
current widened seed pool from issue #142):

| Configuration | Rows returned | `handleRequestFundamentals` (true rank 75) present |
|---|---|---|
| Baseline (no iterative scan) | 10–28 (varied by exact query shape) | No |
| `iterative_scan=relaxed_order`, `max_scan_tuples` unset (pgvector default) | 100/100 | Yes |
| `iterative_scan=relaxed_order`, `max_scan_tuples=5000` | 100/100 | Yes |
| `iterative_scan=relaxed_order`, `max_scan_tuples=20000` | 100/100 | Yes |
| `iterative_scan=relaxed_order`, `max_scan_tuples=40000` | 100/100 | Yes |
| `iterative_scan=relaxed_order`, `max_scan_tuples=70000` | 100/100 | Yes |

Full, correct recall at every `max_scan_tuples` value tested from 5,000
up — the fix isn't sensitive to the exact tuning within this range for
this query.

## Latency measurement

Same query/filter/`LIMIT 100`, wall-clock query time:

| Configuration | Latency |
|---|---|
| Baseline (broken, no iterative scan) | ~5ms |
| `iterative_scan=relaxed_order`, `max_scan_tuples` **unset** (pgvector default) | ~712ms |
| `iterative_scan=relaxed_order`, `max_scan_tuples=5000` | ~19ms |
| `iterative_scan=relaxed_order`, `max_scan_tuples=20000` | ~17ms |
| `iterative_scan=relaxed_order`, `max_scan_tuples=40000` | ~21ms |
| `iterative_scan=relaxed_order`, `max_scan_tuples=70000` | ~24ms |

**Leaving `max_scan_tuples` unset is much worse (712ms) than setting it
explicitly (~17-24ms)** — the unset/default behavior appears to let the
iterative scan keep expanding its traversal far more aggressively than
necessary for a repo-scoped filter. Explicitly bounding it at 20,000
gives full recall at a small, predictable latency cost (~12-17ms over
the broken baseline) rather than the much larger unbounded cost.

## Chosen configuration

`HNSW_ITERATIVE_SCAN = "relaxed_order"`, `HNSW_MAX_SCAN_TUPLES = 20000`
— mid-range of the tested values, correct recall confirmed, latency
essentially flat across the 5,000-70,000 range tested so this isn't a
finely-tuned knob, just a reasonable default. `relaxed_order` (not
`strict_order`) is appropriate: RAG retrieval needs a good candidate
set, not a guarantee of byte-exact similarity ordering.

## What this does and doesn't resolve

This fixes the *recall* defect: filtered queries now actually examine
enough of the index to find real matches instead of silently giving up
early. It does **not** by itself guarantee every relevant chunk lands
inside `top_k=20` — `handleRequestFundamentals`'s true raw-cosine rank
is 75, which is now *reachable* (issue #150 fixed) but still requires
either a wider pool or a reranker to enter a 20-slot final context.
Per `DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`, the reranker
question should be re-evaluated against the *post-fix* failure shape
(genuine near-misses vs. still-buried-deep matches), not against the
pre-fix data where many relevant chunks weren't even being examined.
