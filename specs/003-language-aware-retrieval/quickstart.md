# Quickstart: Validating WP-L6a (Language-Aware Retrieval)

## Prerequisites

- Repo checked out on `feat/wp-l6a-language-aware-retrieval-issue-85`.
- For the unit tests: each service's own venv (or root `.venv` per
  `[[memory:disk-and-test-environment]]`).
- For the manual mixed-language validation below: a running stack
  (`docker compose up --build`, migrations applied) and a repository
  fixture mixing Python and TypeScript/JavaScript files ingested into it.

## Run the new unit tests

```sh
cd vector_store_service
uv run pytest tests/core/vectorstore/test_typed_filter_columns.py -v

cd ../rag_orchestrator
uv run pytest tests/test_language_scoping.py tests/test_repo_scoping.py -v
```

Expected: all new tests pass, and `test_repo_scoping.py`'s existing exact
`metadata_filter` dict-equality assertions still pass unchanged (the
no-regression check for FR-006/SC-002).

```sh
cd ingestion_service
uv run pytest tests/codebase/test_ts_repo_graph_golden.py tests/codebase/test_repo_graph_builder.py -v
```

Expected: unchanged — these assert on `(artifact_type, canonical_id)`
tuples, not whole-entity-dict equality, so adding a `language` key doesn't
affect them.

## Apply the new migration

```sh
uv run alembic upgrade head
```

Expected: `vector_chunks` gains a `language` column and two new indexes;
`alembic downgrade -1` cleanly reverses it (mirrors the `source_type`
migration's own downgrade).

## Manual follow-up validation (not a merge gate — see spec.md Evaluation Evidence)

This is the actual point of pulling WP-L6a forward: use it as the
measurement apparatus for WP-L2 confidence-building against a real
mixed-language repository.

1. Ingest a repository containing both Python and TypeScript/JavaScript
   source (e.g. a backend+frontend monorepo, or two smaller repos merged
   into one fixture directory) via `/v1/ingest-repo`.
2. Ask the same question three ways against `/v1/rag`:
   ```json
   {"query": "...", "repo_id": "...", "language": "python"}
   {"query": "...", "repo_id": "...", "language": "typescript"}
   {"query": "...", "repo_id": "...", "language": "javascript"}
   {"query": "...", "repo_id": "..."}
   ```
3. Confirm each language-scoped response's `sources` only ever cite files
   of that language (SC-001), and that the unscoped call's `sources`/
   `retrieval_plan` are unchanged from before this feature shipped
   (SC-002).
4. **The actual diagnostic step**: for a query where the unfiltered answer
   looks wrong, compare it against the same query scoped to just the
   language you'd expect the answer to come from. If the scoped answer is
   *better*, the unfiltered failure was retrieval mixing languages — not
   an extraction/resolution bug in WP-L2. If the scoped answer is *also*
   wrong, the bug is upstream in that language's extractor/resolution,
   not in retrieval. Record which outcome you see — this is exploratory
   diagnostic evidence for WP-L2 follow-up work, not a pass/fail gate for
   this feature.
