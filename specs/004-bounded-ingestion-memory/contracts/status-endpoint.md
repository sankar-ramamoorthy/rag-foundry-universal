# Contract: repository ingestion progress

Tracking issue: #160
Endpoint: GET /v1/codebase/ingest-repo/{ingestion_id}

Preserve ingestion_id/status. Add optional embed_progress with stage,
nodes_processed, nodes_total, chunks_persisted, max_buffer_chunks and
max_buffer_bytes. Absent before initialization; present BEFORE first
embedding page. Empty input reports completed stage with all counters zero.

Counters do not imply one vector/node. They are monotonic and updated after
acknowledged writes; repeated polls may show identical counts. New database
sessions must observe progress without lost metadata. A failed request can
have partially committed writes beyond acknowledged progress. No resume
guarantee. Tests cover initialization, old clients, empty input, failure and
fresh-session persistence.
