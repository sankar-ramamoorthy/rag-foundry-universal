# Plan: bounded repository ingestion memory

Tracking issue: #160
Roadmap: WP-R1
Status: Ready for implementation; no code/benchmark completion implied
Spec: [spec.md](./spec.md)

## Implementation decisions

1. Add positive settings with initial calibration defaults:
   INGESTION_NODE_PAGE_SIZE=32; INGESTION_EMBED_BATCH_SIZE=128 (chunks);
   INGESTION_EMBED_MAX_BYTES=262144; INGESTION_MAX_ARTIFACT_BYTES=1048576.
   Independent of Ollama HTTP size and persistence HTTP size.
2. CodebaseGraphPersistence preflights SQL octet_length before selecting text.
   Narrow page projection: document_id, canonical_id, relative_path, doc_type,
   text. Keyset by document_id, scoped to repo_id+ingestion_id. Count uses the
   same whitespace inclusion as iteration; a bounded Python counting scan is
   acceptable if SQL trimming is not exactly equivalent. Detect replacement.
   Inspect real PostgreSQL EXPLAIN before adding a composite paging index.
3. Extract the existing suffix/language helper. Move graph build/persist into
   a helper returning scalar stats only; prove graph/IR ownership ends before
   embedding. No ORM collection or generator may retain repository text.
4. Iterate capped node pages and artifact chunks. Existing one-artifact chunk
   lists may remain, accounted within the artifact envelope. Flush chunk
   buffer before either count or byte limit is exceeded. Oversized emitted
   chunks must fail explicitly, not truncate or exceed the contract.
5. Assign ordinals before buffering. Add optional explicit chunk_indices to
   IngestionPipeline.embed_and_persist_batch and HttpVectorStore.persist_batch.
   Old callers retain local enumeration. Validate cardinality and indices.
   This supersedes the original prohibition on persistence signature changes.
6. Remove whole-repo canonical-map use here. Emit stage BEFORE first page.
   Persist fresh outer JSON with acknowledged counts/maxima, including 0/0.
7. Add finite embedding connect/read timeout. Production rollout requires
   WP-R2/R3 admission and full-operation repo serialization. Never hold a
   transaction open for remote embedding merely to maintain a paging snapshot.

## Memory contract

Live additional state is bounded by page_size * artifact_byte_ceiling,
one artifact's chunk objects, buffer_bytes, buffer_count * embedding object
overhead, and bounded HTTP serialization. Measure Python/allocator overhead;
do not equate Python float lists with float32 storage. RSS may retain freed
graph allocations. Object lifetime and current RSS are separate measurements.

## Verification

Skeletal tests precede implementation. Compare normalized output at buffer
sizes 1, 7 and 128 with stub vectors. Include many chunks/node, Unicode,
NULL/whitespace, empty graph, oversize rejection and changed generation.
Real Postgres verifies paging and fresh-session JSON progress. Failure/kill
tests establish partial durability without resume. Run stage-aware isolated
Linux benchmarks and pinned DocsGPT per [quickstart](./quickstart.md).

## Constitution and knowledge-base impact

I: normalized canonical/topology parity. II: DB ownership unchanged; #165
disclosed. III/V: no retrieval/model/chunk changes. IV: routing unchanged.
VI: #160 and dedicated implementation PR. VII: ADR drift disclosed. VIII:
unit/integration/memory gates explicit. Update DOCS/status, roadmap and
OKF test-results with implemented versus validated state distinguished.
Keep dated audits historical. Merge required CI; keep #160 open if mandatory
memory evidence remains missing.
