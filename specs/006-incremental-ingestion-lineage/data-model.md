# Phase 1 Data Model: Incremental ingestion + snapshot lineage

All changes are additive columns on existing tables — no new table
(FR-011). Existing rows get `NULL`/default values; no backfill is
required for correctness (a `NULL` `commit_sha` or `content_hash`
simply means "no lineage recorded before this feature shipped," which
correctly falls back to full-ingestion behavior per R6 — an ingestion
whose prior generation has `content_hash IS NULL` on its file rows
cannot be diffed against, so it fingerprints as create-new-content
instead of matching, i.e. it degrades safely to "treat as changed," not
to an incorrect reuse decision).

## `ingestion_requests` (existing table, `ingestion_service/src/core/models.py`)

New columns:

| Column | Type | Nullable | Populated by |
|---|---|---|---|
| `commit_sha` | `String` | Yes | R5 — resolved post-clone for git-backed ingestions; `NULL` for local-path ingestions |
| `parent_generation_id` | `UUID` | Yes | The `ingestion_id` of the generation this one was built from (FR-009); `NULL` for a repository's first-ever generation. Set for both incremental **and** forced-full generations (FR-005a) — it records lineage, not "was reused from." |
| `is_incremental` | `Boolean` | No, default `false` | `true` only when FR-004's reuse classification actually ran and was not bypassed by `force_full_rebuild` (FR-005a) or an absent/non-`completed` prior generation (FR-005) |
| `chunking_config_version` | `String` | Yes | R4 — the `chunk_strategy` value used this ingestion |
| `embedding_config_version` | `String` | Yes | R4 — the embedding model identifier used this ingestion (e.g. `mxbai-embed-large:latest`) |

No new index required beyond the existing `ingestion_id` primary key
and `repo_id` index (ADR-050) — lineage reads are always by a single
`ingestion_id` or the already-indexed `repo_id`.

## `document_nodes` (existing table, `shared/models/document_node.py`)

New column:

| Column | Type | Nullable | Populated by |
|---|---|---|---|
| `content_hash` | `String` | Yes | R3 — SHA-256 hex digest of raw file bytes, for file-level nodes only (`canonical_id` with no `#symbol` suffix); `NULL` for symbol-level nodes |

**Persistence behavior change** (R1, the plan's central risk): the
existing `UNIQUE(repo_id, canonical_id)` constraint (`uq_repo_canonical`)
becomes the `ON CONFLICT` target for an upsert. `document_id` is never
included in the `DO UPDATE SET` clause, so a surviving row keeps its
original primary key. `ingestion_id` **is** included in `DO UPDATE
SET` on every row, reused or not — every row present in the new
generation, however it got there, ends up tagged with the new
generation's `ingestion_id` (FR-007b's node half). Rows for
`canonical_id`s absent from the freshly resolved graph are explicitly
`DELETE`d (FR-008), which still cascades to their `document_relationships`
and `vectors` rows exactly as today.

## `document_relationships` (existing table, `shared/models/document_relationship.py`)

New column:

| Column | Type | Nullable | Populated by |
|---|---|---|---|
| `repo_id` | `String` | No | R2 — denormalized from either endpoint's `document_nodes.repo_id` at insert time (both endpoints always share the same `repo_id`, per ADR-031's repository-scoping rule — never cross-repo) |

New index: `(repo_id)`, to make the every-ingestion `DELETE FROM
document_relationships WHERE repo_id = :repo_id` (R2) an indexed
operation, consistent with existing indexing conventions on
`document_nodes` (`ix_repo_canonical`).

## `vectors` (existing table, `shared/models/vector_chunk.py`)

No new columns. Behavior change only: for a file classified "unchanged
and eligible for reuse" (FR-006), its existing `vectors` rows are
`UPDATE`d in place to set `ingestion_id` to the new generation's value
(FR-007b's vector half) — no re-embedding, no row deletion/re-insertion.
Because `document_id` is preserved for that file (R1), these rows'
existing `document_id` foreign key remains valid without any change to
that column.

## Entity relationship summary (unchanged shape, changed lifecycle)

```text
ingestion_requests (repo_id, ingestion_id = generation identity)
    │  commit_sha, parent_generation_id, is_incremental,        <- NEW
    │  chunking_config_version, embedding_config_version         <- NEW
    │
    ├─ owns exactly one generation's worth of, per repo_id:
    │
    document_nodes (repo_id, canonical_id) UNIQUE
    │   content_hash (file-level rows only)                      <- NEW
    │   document_id now STABLE across generations for a
    │   canonical_id whose row survives unchanged                <- BEHAVIOR CHANGE
    │
    ├─ document_relationships (repo_id)                          <- NEW COLUMN
    │       from_document_id / to_document_id -> document_nodes
    │       fully replaced every ingestion (R2), regardless of
    │       node reuse
    │
    └─ vectors (document_id -> document_nodes, ON DELETE CASCADE)
            ingestion_id re-tagged on reuse, not re-embedded       <- BEHAVIOR CHANGE
```

## Validation rules

- A `document_nodes` row's `content_hash` MUST be non-`NULL` only when
  `symbol_path IS NULL` (file-level rows) — enforced at the
  application layer (persistence code sets it only for file-level
  nodes), not a DB constraint, consistent with how `symbol_path`
  itself is already handled (nullable, app-populated).
- `ingestion_requests.parent_generation_id`, when non-`NULL`, MUST
  reference an `ingestion_id` that previously existed for the *same*
  `repo_id` — enforced at the application layer (R6 resolves it from
  `resolve_current_generation(repo_id)` immediately before use, not
  from caller input), not a DB foreign key, to avoid a self-referential
  FK lifecycle concern when a referenced generation is later cleaned
  up by ADR-050's superseded-generation cleanup (a `parent_generation_id`
  MAY reference an `ingestion_id` whose row no longer exists after
  cleanup — this is expected and acceptable: it is a historical pointer,
  not a live dependency).
- `is_incremental=true` MUST imply `parent_generation_id IS NOT NULL`
  (an incremental generation always has a parent by definition) —
  enforced at the application layer.
