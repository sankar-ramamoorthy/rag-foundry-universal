-- SELECT statements executed read-only through psycopg using db_inspect.py's
-- connection configuration; results: 2026-10-13-lightrag-direct-sql.json.
-- The command below is an alternative for operator execution, not the route used.
-- Run on the Linux host, without changing data:
-- docker exec -i ingestion-db psql -U ingestion_user -d ingestion_db \
--   -v ON_ERROR_STOP=1 < DOCS/test_results/2026-10-13-lightrag-readonly.sql
\set repo '4f76a36f-caf8-5532-9ee2-977ec412ed6c'
\set generation '128c494e-0aae-4e1d-81d0-b7e52f2006b1'
\pset pager off
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '30s';

-- Verify actual live schema; do not infer it from the legacy ORM vectors model.
SELECT table_name, column_name, data_type, udt_name, is_nullable
FROM information_schema.columns
WHERE table_schema = 'ingestion_service'
  AND table_name IN ('ingestion_requests', 'document_nodes',
                     'document_relationships', 'vector_chunks')
ORDER BY table_name, ordinal_position;

SELECT ingestion_id, repo_id, status, commit_sha, created_at, started_at,
       finished_at, parent_generation_id, is_incremental,
       chunking_config_version, embedding_config_version
FROM ingestion_service.ingestion_requests
WHERE repo_id::text = :'repo'
ORDER BY created_at DESC;

-- Full stored DocumentNode.text is not exposed by the graph HTTP response.
SELECT document_id, canonical_id, relative_path, symbol_path, ingestion_id,
       doc_type, content_hash, octet_length(text) AS text_bytes,
       md5(text) AS text_md5, text
FROM ingestion_service.document_nodes
WHERE repo_id::text = :'repo'
  AND canonical_id IN ('lightrag/operate.py#_build_query_context',
                       'lightrag/operate.py#_apply_token_truncation',
                       'lightrag/operate.py#_build_context_str')
ORDER BY canonical_id;

-- Include real vector dimensions, identity, ordinal, and full passage content.
SELECT dn.canonical_id, vc.document_id, vc.ingestion_id, vc.chunk_id,
       vc.chunk_index, vc.chunk_strategy, vc.provider,
       vector_dims(vc.vector) AS embedding_dimensions,
       vc.source_metadata->>'canonical_id' AS metadata_canonical_id,
       vc.source_metadata->>'repo_id' AS metadata_repo_id,
       vc.source_metadata->>'source_type' AS source_type,
       octet_length(vc.chunk_text) AS text_bytes, vc.chunk_text
FROM ingestion_service.vector_chunks vc
JOIN ingestion_service.document_nodes dn ON dn.document_id = vc.document_id
WHERE dn.repo_id::text = :'repo'
  AND vc.ingestion_id::text = :'generation'
  AND dn.canonical_id IN ('lightrag/operate.py#_build_query_context',
                         'lightrag/operate.py#_apply_token_truncation',
                         'lightrag/operate.py#_build_context_str')
ORDER BY dn.canonical_id, vc.chunk_index, vc.chunk_id;

SELECT dn.canonical_id, count(*) AS chunks,
       min(vc.chunk_index) AS first_ordinal, max(vc.chunk_index) AS last_ordinal,
       count(DISTINCT vc.chunk_index) AS distinct_ordinals,
       count(DISTINCT vc.chunk_id) AS distinct_chunk_ids,
       count(*) FILTER (WHERE vc.vector IS NULL) AS missing_vectors,
       count(*) FILTER (WHERE vc.source_metadata->>'canonical_id'
                         IS DISTINCT FROM dn.canonical_id) AS canonical_mismatches,
       count(*) FILTER (WHERE vc.ingestion_id::text IS DISTINCT FROM :'generation')
           AS generation_mismatches
FROM ingestion_service.vector_chunks vc
JOIN ingestion_service.document_nodes dn ON dn.document_id = vc.document_id
WHERE dn.repo_id::text = :'repo'
  AND dn.canonical_id IN ('lightrag/operate.py#_build_query_context',
                         'lightrag/operate.py#_apply_token_truncation',
                         'lightrag/operate.py#_build_context_str')
GROUP BY dn.canonical_id;

SELECT source.canonical_id AS caller, target.canonical_id AS callee,
       rel.relation_type, rel.relationship_metadata
FROM ingestion_service.document_relationships rel
JOIN ingestion_service.document_nodes source
  ON source.document_id = rel.from_document_id
JOIN ingestion_service.document_nodes target
  ON target.document_id = rel.to_document_id
WHERE source.repo_id::text = :'repo'
  AND rel.relation_type = 'CALL'
  AND source.canonical_id IN ('lightrag/lightrag.py#LightRAG.aquery',
                             'lightrag/lightrag.py#LightRAG.aquery_llm',
                             'lightrag/operate.py#kg_query',
                             'lightrag/operate.py#_build_query_context')
ORDER BY caller, callee;
ROLLBACK;
