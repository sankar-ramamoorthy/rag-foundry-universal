# Data contracts: bounded ingestion memory

Tracking issue: #160
Related: [spec](./spec.md), [status](./contracts/status-endpoint.md)

## Node page

Existing DocumentNode projection: document_id, canonical_id, relative_path,
doc_type, text. Keyset order document_id; every read binds repo_id+ingestion_id.
SQL octet_length preflight precedes text load. Count/iteration exclusions match
Python strip, including tabs/newlines. Verify no generation disappearance.

## Embedding buffer

Parallel chunks, document_ids and explicit chunk_indices. Bound count and
UTF-8 bytes. Ordinal continues across flushes within one artifact. No repo-wide
ordinal map. Release acknowledged state before accumulating successor.

## Progress

Fresh IngestionRequest.ingestion_metadata outer dictionary gains embed_progress:
stage, nodes_processed, nodes_total, chunks_persisted, max_buffer_chunks,
max_buffer_bytes. Initialize before allocation, including zero total. Preserve
existing keys and verify using a new session. Stage values include embedding,
completed and failed. Counters reflect acknowledged writes; ambiguous HTTP
failures do not establish whether the latest write committed. Not a checkpoint.

## Persistence

Optional explicit chunk_indices passes through pipeline to persist_batch.
Validate lengths, nonnegative values and embedding cardinality. Legacy callers
without indices retain document-local enumeration. Existing chunk_index column
is reused; no schema change here. Repo-attempt ownership is #161/#166.
