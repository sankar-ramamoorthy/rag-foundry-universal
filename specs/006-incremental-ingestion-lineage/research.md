# Phase 0 Research: Incremental ingestion + snapshot lineage

All findings below were verified against current code in this session
(not inferred from docs/audit text alone), per Constitution Governance's
verification discipline.

## R1: How can a reused file's vectors survive the new generation's persist step?

**Decision**: Change `CodebaseGraphPersistence.persist_graph` from
unconditional delete-all-then-insert-all (with a freshly minted
`document_id` UUID per node, every call) to an upsert keyed on the
existing `(repo_id, canonical_id)` unique constraint
(`uq_repo_canonical`), via `INSERT ... ON CONFLICT (repo_id,
canonical_id) DO UPDATE SET <every column except document_id>`. For a
`canonical_id` already present, this updates its row in place —
**critically, leaving `document_id` untouched** — instead of deleting
and re-inserting it under a new PK. For `canonical_id`s no longer
present in the freshly resolved graph (FR-008's deleted-file case), an
explicit `DELETE ... WHERE repo_id = :repo_id AND canonical_id NOT IN
(:current_canonical_ids)` replaces the old blanket delete.

**Rationale**: Verified `shared/models/vector_chunk.py:61-64` —
`vectors.document_id` is `ForeignKey(..., ondelete="CASCADE")`. Verified
`ingestion_service/src/core/codebase/codebase_persistence.py:171-179` —
`persist_graph` today does exactly one thing per ingestion: `DELETE
FROM document_nodes WHERE repo_id = :repo_id`, then bulk-insert every
node with `document_id = str(uuid.uuid4())` freshly generated in
Python before the insert (line 122). Combined, these two facts mean
that today, *every* ingestion — even a hypothetical one that changed
nothing — destroys every vector for the repo via cascade, then the
embedding step re-creates them all from scratch. There is currently no
concept of a vector "surviving" an ingestion at all; incremental reuse
(FR-007) requires inventing that concept for the first time, and the
only way to do so without inventing a new document-identity scheme is
to stop regenerating `document_id` for rows whose `canonical_id`
didn't change.

**Alternatives considered**:
- *Copy reused rows into new rows under a new `document_id`, leave the
  old ones for cleanup.* Rejected: `document_nodes` has a hard
  `UNIQUE(repo_id, canonical_id)` constraint (ADR-031) — a copy would
  collide with the still-present old row for the same `canonical_id`
  until the old row is deleted, and deleting it first re-introduces
  the exact CASCADE problem this option was trying to avoid (a window
  where the vector has no valid `document_id` to attach to).
- *Give `vectors` its own independent identity keyed on
  `(repo_id, canonical_id, chunk_index)` instead of `document_id`,
  decoupling it from `document_nodes` entirely.* Rejected as
  disproportionate: it would touch `vector_store_service`'s schema and
  query paths (out of this feature's service boundary per Constitution
  Principle II) for a problem the upsert approach solves entirely
  within `ingestion_service`.

## R2: How are stale relationships (including ones touching reused, unchanged nodes) removed each run?

**Decision**: Add a `repo_id` column to `document_relationships`
(denormalized, populated at insert time from the same value already on
both endpoint nodes), and change the relationship-replace step to an
explicit `DELETE FROM document_relationships WHERE repo_id = :repo_id`
before inserting the freshly resolved edge set — run every ingestion,
full or incremental, immediately after the node upsert/delete above.

**Rationale**: Verified `shared/models/document_relationship.py` — it
has no `repo_id` column today; its only path to a repo is indirectly,
through `from_document_id`/`to_document_id`'s `ON DELETE CASCADE` to
`document_nodes`. That indirection is exactly why relationship cleanup
"worked for free" under the old delete-all-nodes approach — deleting
every node cascaded to every relationship. Once node deletion becomes
selective (R1: only genuinely-removed `canonical_id`s are deleted), a
node that survives unchanged no longer triggers cascade cleanup of its
*relationships*, even though FR-002 requires the whole graph
(including every edge touching that node) to be freshly re-resolved
every run — a relationship from a previous generation that's no longer
true (e.g. a caller that stopped calling it, from a *different* file
that *did* change) must not survive alongside the freshly resolved
set. A direct `repo_id` column makes this an ordinary indexed delete
instead of a `document_id`-subquery join, and is the natural,
minimal, "extend the existing generation/artifact substrate" move FR-011
already commits to.

**Alternatives considered**:
- *Scope the delete via `WHERE from_document_id IN (SELECT document_id
  FROM document_nodes WHERE repo_id = :repo_id) OR to_document_id IN
  (...)`.* Works without a schema change, but is a correlated
  subquery/join on every ingestion instead of an indexed equality
  filter, and is easy to get subtly wrong (e.g. forgetting the `OR`
  side) in a way a direct column can't be. Rejected in favor of the
  small, explicit column.

## R3: Where does per-file content fingerprint data live?

**Decision**: Add `content_hash` (nullable `String`, SHA-256 hex
digest) to `document_nodes`, populated for file-level nodes (i.e. rows
whose `canonical_id` has no `#symbol` suffix per ADR-031's format —
one row per file, not per symbol). `snapshot_diff.py`'s
changed/unchanged/new/deleted classification reads the prior
generation's file-level `content_hash` values (queried once per
ingestion, keyed by `canonical_id`, *before* `persist_graph` overwrites
them) and compares against freshly computed hashes of the current
checkout.

**Rationale**: FR-011 forbids a new per-artifact-type table; a column
on the existing `document_nodes` table (which already has exactly one
row per file via its file-level `canonical_id`, per ADR-031) is the
direct extension the requirement calls for, and reuses the row this
feature already needs to read/write for R1 — no second query pattern
or table join required to get a file's fingerprint alongside its other
metadata. Symbol-level nodes leave `content_hash` `NULL` — their
identity and reuse status is governed entirely by their owning file's
hash, not their own.

**Alternatives considered**:
- *A `file_fingerprints` table keyed on `(repo_id, ingestion_id,
  relative_path)`.* Rejected: this is exactly the "new per-artifact-type
  table" FR-011 forbids in spirit — it would store the same
  file-identity information `document_nodes` already stores, just
  duplicated into a second table.
- *Store all fingerprints as one JSON blob on `ingestion_requests.ingestion_metadata`.*
  Rejected: the spec's own Assumptions section flagged this as
  unresolved and asked for a design decision; a JSON blob makes the
  per-file lookup R1 needs (by `canonical_id`) an application-side scan
  instead of an indexed column read, and would grow unboundedly with
  repository size in a single JSON column — a poor fit for repos in
  the thousands of files SC-001 targets.

## R4: Where does chunking-config and embedding-model identity for the reuse gate (FR-006) live?

**Decision**: Add two columns to `ingestion_requests`:
`chunking_config_version` and `embedding_config_version`, both plain
strings, populated once per ingestion from the config actually used
(chunking: the active `chunk_strategy` value already used per-chunk in
`vectors.chunk_strategy`, per `ingestion_service/src/core/chunkers/selector.py`;
embedding: `settings.OLLAMA_EMBED_MODEL` — e.g. `mxbai-embed-large:latest`
— already the config identity `embedders/factory.py` resolves per
ingestion). FR-006's reuse gate compares the *new* ingestion's values
against the *prior generation's* recorded values; any mismatch forces
re-embedding for every file, not just changed ones.

**Rationale**: Both identifiers already exist as live config values
consumed once per ingestion (not per file) — verified in
`ingestion_service/src/core/chunkers/selector.py` and
`ingestion_service/src/core/embedders/factory.py`. Recording them
per-generation (not per-file) matches their actual granularity and
keeps the reuse-gate check a single cheap comparison per ingestion,
not per file.

**Alternatives considered**:
- *Record chunking/embedding identity per file, alongside its
  `content_hash`.* Rejected: both are ingestion-wide config, not
  per-file data — recording them per file would be redundant storage
  with no benefit, since they're always identical across every file in
  a single ingestion run.

## R5: How is the source commit SHA resolved and recorded?

**Decision**: Immediately after `git.Repo.clone_from(git_url,
temp_dir)` in `_background_ingest_repo`
(`ingestion_service/src/api/v1/codebase_ingest.py`), resolve
`git.Repo(temp_dir).head.commit.hexsha` and pass it through to the
ingestion-completion path that writes `ingestion_requests.commit_sha`
(new column) alongside the existing status/timestamp updates
`StatusManager` already performs. Non-git (`local_path`) ingestions
leave `commit_sha` `NULL` (per spec Non-Goals — local-path ingestion is
out of scope for the commit-identity half of this feature).

**Rationale**: `GitPython` (`import git`) is already a dependency and
already used for the clone itself (verified,
`codebase_ingest.py:203-207`); `Repo.head.commit.hexsha` is its
standard, already-resolved-by-the-clone way to read the checked-out
commit with no extra network call. No new dependency, no new I/O.

**Alternatives considered**:
- *Shell out to `git rev-parse HEAD`.* Rejected: `GitPython` already
  wraps this and is already imported in the exact function that would
  need it; shelling out would be a second way to do the same thing for
  no benefit.

## R6: What identifies "the previous generation" to diff against, and how is it read before it's overwritten?

**Decision**: Reuse `db_utils.resolve_current_generation(repo_id)` and
`db_utils.generation_status(repo_id)` (both already shipped for
ADR-051's cheap generation-check endpoint) at the *start* of
`_background_ingest_repo`, before cloning. If `generation_status`
returns anything other than `"completed"` (including `"unknown"` for a
first-ever ingestion), or if `force_full_rebuild` is set (FR-005a),
proceed as a full ingestion (every file classified "new" by
`snapshot_diff`, which degenerates R1's upsert to plain inserts — see
plan.md's Required Non-Regressions). Otherwise, read that prior
generation's file-level `content_hash` values before calling
`persist_graph`, since `persist_graph`'s upsert (R1) will overwrite
them for changed files as part of publishing the new generation.

**Rationale**: `resolve_current_generation`/`generation_status`
already implement exactly ADR-050's "current generation" semantics
(the single owner of `document_nodes` rows for a `repo_id`, gated on
its `ingestion_requests.status`) that FR-005's "previous successful
snapshot" language maps directly onto — verified in
`ingestion_service/src/core/db_utils.py:305-355` (read during this
session's original #196 scoping investigation, prior to this plan).
No new "what is the previous generation" logic needs inventing.

**Alternatives considered**:
- *A dedicated `parent_generation_id` lookup query independent of
  `resolve_current_generation`.* Rejected: would duplicate logic
  `resolve_current_generation` already gets right (including the
  edge case of no completed generation existing yet) for no benefit.
