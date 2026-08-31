# Phase 1 Data Model: WP-L6a Language-Aware Retrieval

No new entity types. This feature adds one attribute (`language`) to two
existing shapes, and one optional request field.

## Graph entity dict (in-memory, `GraphAssembler` output)

| Field | Type | Notes |
|---|---|---|
| `language` (new) | `str \| None` | Top-level key, sibling to the existing `doc_type` key. `None`/absent for MARKDOWN_SECTION, MARKDOWN_MODULE, EXTERNAL_MODULE, EXTERNAL_SYMBOL — anything whose `relative_path` suffix isn't in `LANGUAGE_BY_SUFFIX` (empty string included). One of `"python"`, `"typescript"`, `"javascript"` for CLASS/INTERFACE/FUNCTION/METHOD/MODULE/IMPORT nodes from a recognized source file. |

## Vector chunk `source_metadata` (JSONB) + typed column

| Field | Type | Notes |
|---|---|---|
| `source_metadata.language` (new) | `str \| null` | Copied verbatim from the owning graph node's `language` at embed time. `null` for chunks from non-code content (unchanged from today, since those never had this key). |
| `vector_chunks.language` (new DB column) | `TEXT`, nullable | Denormalized copy of `source_metadata->>'language'`, written at insert time by `PgVectorStore.add()` — cannot drift, mirrors `repo_id`/`doc_type`/`source_type`. Indexed via `ix_vector_chunks_repo_language (repo_id, language)` and `ix_vector_chunks_language_col (language)`. |

## `/v1/rag` request (`RAGQuery`)

| Field | Type | Notes |
|---|---|---|
| `language` (new) | `Optional[str] = None` | One of `"python"`, `"typescript"`, `"javascript"` to scope retrieval; omitted or `None` preserves today's unfiltered behavior exactly (FR-006). An unrecognized value is not rejected — it simply matches no stored `language` value and yields zero seed results (spec Edge Cases/Assumptions), consistent with scoping to a language with no ingested content. |

No response-model change: `RAGResponse.retrieval_plan` already carries
arbitrary diagnostic keys; no new field is required there for this
feature's acceptance criteria (a query with 0 seed results already
surfaces correctly via the existing `seed_docs: 0` plan field).

## `hybrid_retrieve`'s seed-search `metadata_filter`

| Scenario | `metadata_filter` value |
|---|---|
| No language requested (today's behavior, unchanged) | `{"source_type": "code", "repo_id": repo_id}` |
| Language requested, primary search | `{"source_type": "code", "repo_id": repo_id, "language": language}` |
| No language requested, fallback (today's behavior, unchanged) | `{"repo_id": repo_id}` |
| Language requested, fallback | `{"repo_id": repo_id, "language": language}` |
