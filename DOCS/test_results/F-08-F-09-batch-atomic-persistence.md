# F-08 (WP-S2) + F-09/F-06 (WP-S3) — test results

Date: 2026-07-18
Branch: `post-audit-branch` (commits `43a7232`, `7a882a5`)

## F-08 — batch embedding + persistence

Before: per artifact — 1 SQL lookup (`get_node_by_canonical_id`) + 1 Ollama
POST + 1 vector-store POST, all serial. 10k artifacts ≈ 10k SQL + 20k HTTP
round-trips.

After: 1 map query per repo; Ollama called once per `OLLAMA_BATCH_SIZE`
(50) chunks; vector-store `/v1/vectors/batch` called once per 500 records.

Unit tests (`tests/codebase/test_batch_embedding.py`, 12 tests, all pass):

- ceil(N/500) vector-store HTTP calls asserted via request counter
  (1200 chunks → exactly 3 POSTs of 500/500/200).
- `get_canonical_id_map` runs exactly once per ingest; test double raises
  if the per-node lookup is ever called.
- OllamaEmbedder splits 120 chunks at batch_size=50 into 3 POSTs of
  50/50/20, order preserved; raises on count mismatch; no HTTP on empty
  input.
- textless and DB-unmapped nodes skipped exactly as before; canonical_id /
  repo_id / source_metadata injection unchanged.

`get_canonical_id_map` also verified against the docker-compose.test.yml
Postgres (5433) with real inserts.

## F-09/F-06 — atomic bulk graph persistence + per-repo lock

Before: `upsert_nodes` committed the repo-wide delete in its own
transaction before inserting (crash ⇒ repo left with no graph); node
inserts were per-row; relationships cost 3 queries per edge; no
concurrency control.

After: `persist_graph()` — delete + bulk node insert + bulk relationship
insert in one transaction, endpoints resolved via an in-memory
canonical_id→document_id map, `ON CONFLICT DO NOTHING` on
`uq_document_relationship`, and a transaction-scoped
`pg_advisory_xact_lock` keyed on repo_id.

Integration tests (`tests/codebase/test_atomic_graph_persistence.py`,
5 tests, all pass against docker-compose.test.yml Postgres on 5433):

- failed rebuild (unique violation mid-transaction) rolls back fully;
  the previous graph (nodes and edges) is intact;
- rebuild fully replaces the prior version (old canonical_ids gone);
- 3 rounds of two concurrent rebuilds of the same repo with a thread
  barrier: final state is always exactly one complete version, never a
  mix;
- 50 nodes + 49 edges persist in ≤10 SQL statements (old path: ~3 per
  edge ≈ 150 for the edges alone);
- unknown-endpoint edges skipped and counted, round-trip shape verified.

## End-to-end (real stack)

Rebuilt `ingestion-service` image and ingested `/app/shared`
(21 files):

- status `completed`; `Graph persisted: {'deleted': 209, 'nodes': 210,
  'relationships': 178, 'skipped_relationships': 0}` — prior graph
  replaced atomically;
- `Embedded 133 chunks (0 nodes had no DB record)`;
- DB check: 133 `vector_chunks` rows for the ingestion, 48 distinct
  `document_id`s — per-chunk document linkage preserved through the
  batch path.

Regression: full ingestion_service unit suite 73 passed / 1 pre-existing
skip (3 files excluded per issue #25).
