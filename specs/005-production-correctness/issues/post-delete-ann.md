# WP-R3/R4 follow-up: post-delete ANN recall

Tracking: [#176](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/176)
Status: reproduced in isolated CI; production impact and exact cause unverified.

## Evidence

#160 calibration run 35220047904 at d0b6603 (GitHub synthetic merge SHA in raw
JSONL) ingested and deleted 1,024 + 4,096 + 1,144 benchmark vectors. All 11
ingestion integration checks passed. The following existing ANN suite inserted
its 60-row deterministic fixture but three searches returned zero rows:
language-scoped, end-to-end doc_type-scoped, and hybrid repo/source-type-scoped.
Earlier runs without this bulk churn passed. Hypothesis: dead HNSW entries or
index maintenance; do not present this as a proven production root cause.

## Required work and acceptance

- [ ] Reproduce with exact-search eligible-row counts and actual pgvector version.
- [ ] Compare ANN/EXPLAIN before and after isolated VACUUM; retain original
      failed gate (diagnostic success is not a production fix).
- [ ] Add a deterministic insert/delete/reinsert/search regression owned by the
      vector service. Separate benchmark databases for performance isolation,
      without hiding this lifecycle regression or claiming isolation fixes it.
- [ ] Choose a measured correctness mechanism: scope/rerun/search guarantees or
      bounded maintenance as justified by evidence. Do not place a global
      blocking VACUUM in an async delete route or silently force unbounded scans.
- [ ] Verify recall and latency after large delete and re-ingestion, preserving
      unrelated corpora and respecting service/database ownership.
- [ ] Separate implementation PR, green CI, KB evidence and target-host gate.

Coordinate #166 (delete/generation), #167 (retrieval correctness), #170
(availability), and #171 (post-delete query in full lifecycle smoke). This is
new measured evidence in the existing correctness programme, not a reason to
change chunking, embedding models or rerankers in #160.
