# Phase 0 Research: WP-L6a Language-Aware Retrieval

All items below were verified against live code (file/line references), not
assumed from the audit doc.

## Where language signal exists today

**Decision**: introduce a dedicated `language` value; do not overload the
existing `doc_type` field.

**Evidence**: `doc_type` is set per-extractor and mixes language strings
with non-language values:
- `ingestion_service/src/core/extractors/python_extractor.py:35` —
  `DEFAULT_DOC_TYPE = "python source"`.
- `ingestion_service/src/core/extractors/treesitter/typescript.py:144-148` —
  `"typescript source"` / `"javascript source"` (this one already
  disambiguates TS vs JS correctly, but as a side effect of its doc-type
  string, not a dedicated field).
- `ingestion_service/src/core/extractors/markdown_extractor.py:58,159` —
  `"markdown_module"` / `"markdown_section"` (not a language at all).
- `ingestion_service/src/core/codebase/graph_assembler.py` — `EXTERNAL_MODULE`/
  `EXTERNAL_SYMBOL` synthetic nodes get `"doc_type": "external"`.

Reusing `doc_type` as a language filter would require the orchestrator to
know internal strings like `"python source"` and to special-case
`"external"`/`"markdown_*"`/`"unknown"` as "not a language" — exactly the
leaky-abstraction risk the plan doc's WP-L6 directive ("`metadata.language`
on every node") already avoids by specifying a dedicated field.

## Where to derive `language`

**Decision**: a new module-level constant in `graph_assembler.py`,
computed from `relative_path`'s suffix — not per-extractor metadata. Full
rationale in plan.md's Constitution Exceptions table.

```python
LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}
```

Applied in `_lower_symbol`/`_lower_import` (both already receive
`relative_path`) as one extra top-level key on the returned entity dict,
mirroring exactly how `doc_type` is already promoted to a top-level key
(`graph_assembler.py`'s existing `"doc_type": sym.metadata.get("doc_type", "unknown")`
pattern). Files with no matching suffix (`.md`, and the empty
`relative_path=""` on `EXTERNAL_MODULE`/`EXTERNAL_SYMBOL` synthetic nodes)
naturally get no `language` key at all (`dict.get` returns `None`,
satisfying spec FR-002 with zero special-casing).

## Vector-chunk metadata plumbing

**Decision**: one new line in `_embed_repo_artifacts`
(`ingestion_service/src/api/v1/codebase_ingest.py:116-124`), alongside the
existing `chunk.metadata["doc_type"] = node.get("doc_type", "code")`:

```python
chunk.metadata["language"] = node.get("language")
```

**Evidence this is sufficient, no further plumbing needed**:
`ingestion_service/src/core/http_vectorstore.py:30` —
`HttpVectorStore._build_record` does `metadata_dict = dict(chunk.metadata or {})`
and puts the *entire* `chunk.metadata` dict into `record["metadata"]["source_metadata"]`
verbatim. Any key set on `chunk.metadata` (including a `None` value) lands
in `source_metadata` automatically — confirmed by reading `_build_record`
line-by-line, no allowlist of chunk-metadata keys exists there.

## Typed column + index

**Decision**: exact repeat of the `source_type` migration
(`migrations/versions/20260829_add_source_type_typed_column.py`), which
itself repeats the `repo_id`/`doc_type` migration
(`20260719_typed_filter_columns.py`):

```sql
ALTER TABLE ingestion_service.vector_chunks ADD COLUMN IF NOT EXISTS language TEXT;
UPDATE ingestion_service.vector_chunks SET language = source_metadata->>'language' WHERE language IS NULL;
CREATE INDEX IF NOT EXISTS ix_vector_chunks_repo_language ON ingestion_service.vector_chunks (repo_id, language);
CREATE INDEX IF NOT EXISTS ix_vector_chunks_language_col ON ingestion_service.vector_chunks (language);
ANALYZE ingestion_service.vector_chunks;
```

New revision id `20260831_language_col`, `down_revision = "20260829_src_type"`
(confirmed head of the migration chain via `grep -H "^revision\|^down_revision"
migrations/versions/*.py` — no migration currently declares
`down_revision = "20260829_src_type"`).

`vector_store_service/src/core/vectorstore/pgvector_store.py`:
- line 26: add `"language"` to `TYPED_FILTER_COLUMNS` (currently
  `frozenset({"repo_id", "doc_type", "source_type"})`).
- lines 50-56 (`add()`'s INSERT): add `language` to the column list and
  `%s` placeholder.
- lines 69-72 (the typed-copy tuple): add
  `source_metadata.get("language")`.

No change needed to `_filter_target`/`_build_filter_conditions`
(lines 78-130) — both are already generic over `TYPED_FILTER_COLUMNS`
membership; adding one frozenset entry is the entire behavioral change.

## `/v1/rag` request/response and service layer

**Decision**: thread one new optional field end-to-end, defaulting to
`None` everywhere, matching `repo_id`'s existing threading pattern exactly.

- `rag_orchestrator/src/api/v1/models.py:6-11` (`RAGQuery`) — add
  `language: Optional[str] = None` alongside the existing `repo_id`.
- `rag_orchestrator/src/api/v1/routes.py:42-48` (`rag_endpoint`) — add
  `language=rag_query.language` to the `run_rag(...)` call.
- `rag_orchestrator/src/core/service.py:333-341` (`run_rag`) — add
  `language: Optional[str] = None` parameter, pass to `hybrid_retrieve`.
- `rag_orchestrator/src/core/service.py:227-256` (`hybrid_retrieve`) — add
  `language: Optional[str] = None` parameter; build the filter dict
  conditionally:
  ```python
  metadata_filter = {"source_type": "code", "repo_id": repo_id}
  if language:
      metadata_filter["language"] = language
  payload = {"query_vector": query_embedding, "k": top_k, "metadata_filter": metadata_filter}
  ```
  and the fallback (line 254) the same way:
  ```python
  fallback_filter = {"repo_id": repo_id}
  if language:
      fallback_filter["language"] = language
  payload["metadata_filter"] = fallback_filter
  ```
  This preserves the exact-dict-equality assertions in
  `test_repo_scoping.py` when `language` is `None` (confirmed: those tests
  call `hybrid_retrieve` without a `language` kwarg at all, so the default
  `None` skips adding the key — dict stays exactly
  `{"source_type": "code", "repo_id": repo_id}` / `{"repo_id": repo_id}`).

No change needed to `/v1/vectors/search`'s Pydantic model
(`vector_store_service/src/api/v1/vectors.py:31-34`,
`metadata_filter: Optional[Dict[str, Any]]`) — already fully generic.

No change needed to graph-traversal expansion
(`_rank_expanded_canonical_ids`, `execute_traversals_from_seeds`) or
`_fetch_expanded_doc_chunks`/`/v1/vectors/search-by-doc` — expansion walks
graph edges from an already-language-scoped seed set (spec FR-008); it
fetches by `document_id`, which is already fully determined once the seed
set is scoped, so no separate language filter is needed there (verified:
`search-by-doc`'s request model takes only `document_id`/`k`, no filter
field to add one to even if it were needed).

## Test precedent

`rag_orchestrator/tests/test_repo_scoping.py` is the exact template:
`_run_hybrid_with_empty_store` monkeypatches `httpx.AsyncClient` with a
`MockTransport` handler that captures every `/v1/vectors/search` payload
into a list, then calls `hybrid_retrieve(...)` directly via `asyncio.run`.
New tests add an optional `language` kwarg to that harness and assert the
captured `metadata_filter` dict shape for each of: python-only,
typescript-only, javascript-only, no-language (must equal today's exact
dict), and the fallback-with-language case (mirrors
`test_fallback_relaxes_source_type_but_keeps_repo_scope`).

`vector_store_service/tests/core/vectorstore/test_typed_filter_columns.py`'s
`render()` helper (calls `PgVectorStore._build_filter_conditions` directly,
no DB) is the exact template for the new typed-column tests — one-line
equality/`"in"` tests parallel to the existing `doc_type`/`source_type`
ones.
