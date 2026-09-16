# Phase 1 Data Model: Bounded Ingestion Memory

No new tables and no new columns (see research.md Decisions 2-3). This
feature introduces one new read-path query shape and two in-memory/transient
concepts; the ingestion status record gains two optional fields.

## Embeddable Node Page (new read query, not a new table)

A bounded slice of a repo's embeddable `document_nodes` rows, keyset-paginated
so paging cost doesn't degrade as the repo grows.

**Source**: `document_nodes` (existing table, `ingestion_service`-owned,
`shared/models/document_node.py`).

**Selected columns** (all already exist on `DocumentNode`):
- `document_id` — needed as the chunk's `document_id` for vector persistence.
- `canonical_id` — needed for chunk metadata (`canonical_id`,
  `source_metadata.canonical_id`), matching current `_embed_repo_artifacts`
  behavior.
- `relative_path` — needed for chunk metadata, and to derive `language`
  (research.md Decision 3).
- `doc_type` — needed for chunk metadata.
- `text` — the content to chunk/embed; excluded from selection when `NULL`
  or empty (mirrors today's `if not text.strip(): continue` skip, applied as
  a query filter instead of a post-fetch check where practical).

**Filter**: `repo_id = :repo_id AND text IS NOT NULL AND text != ''`

**Ordering / pagination key**: `document_id` (primary key, already indexed) —
keyset pagination (`WHERE document_id > :last_seen_id ORDER BY document_id
LIMIT :page_size`) rather than `OFFSET`, so page N's query cost doesn't grow
with N.

**Page size**: the new working-set setting (research.md Decision 5),
independent of `OLLAMA_BATCH_SIZE` / `PERSIST_BATCH_SIZE`.

**Not selected**: `title`, `summary`, `summary_embedding`, `source`,
`ingestion_id`, `symbol_path` — unused by the embed stage today; omitting
them from the query keeps each page's row size minimal.

## Working-Set Slice (transient, in-process only)

One page's worth of `Chunk` objects (from `pipeline._chunk()`) plus their
parallel `document_ids` list — the direct replacement for today's whole-repo
`all_chunks`/`document_ids`. Scoped to one iteration of the bounded loop;
eligible for release once that iteration's `embed_and_persist_batch()` call
returns and the loop fetches the next page.

**Lifecycle**: created → chunked → embedded (`_embed`) → persisted
(`persist_batch`) → released, entirely within one loop iteration. Never
exists concurrently with the next slice's data (sequential, not pipelined,
per FR-002's persist-before-next-slice requirement).

## Ingestion Progress (extends existing `IngestionRequest`, no schema change)

Reuses the existing `ingestion_metadata` JSON column on `IngestionRequest`
(`ingestion_service/src/core/models.py` — already used today by
`StatusManager.mark_failed()` to store an `error` key). Adds an
`embed_progress` key:

```json
{
  "embed_progress": {
    "nodes_processed": 12000,
    "nodes_total": 23354
  }
}
```

**Written by**: `StatusManager`, once per completed working-set slice (new
method, e.g. `update_embed_progress(ingestion_id, processed, total)`),
during `_embed_repo_artifacts`'s bounded loop.

**Read by**: `GET /v1/codebase/ingest-repo/{ingestion_id}` — see
`contracts/status-endpoint.md`.

**Not** a new state in the `status` enum (`accepted`/`running`/`completed`/
`failed` unchanged) — `embed_progress` is sub-stage detail within `running`,
not a new top-level status (FR-005 asks for observable progress, not a
lifecycle change; the separate orphaned-`running` lifecycle problem is
issue #161, out of scope here per spec Non-Goals).

## Validation Rules

- `nodes_processed` MUST NOT exceed `nodes_total` for a given ingestion.
- `nodes_total` is fixed once computed at the start of the embed stage (a
  `COUNT(*)` against the same filter as the Embeddable Node Page query) and
  does not change during the run.
- A repo with zero embeddable nodes (FR-008) yields `nodes_total = 0` and the
  embed stage's bounded loop performs zero iterations — this is a valid,
  non-error terminal state for `embed_progress`.
