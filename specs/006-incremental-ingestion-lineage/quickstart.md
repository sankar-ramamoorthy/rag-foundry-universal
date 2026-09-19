# Quickstart: validating incremental ingestion + snapshot lineage

Prerequisites: `docker-compose.test.yml` stack up (`ingestion_test` DB,
port 5433) with migrations applied — same setup `ingestion_service`'s
existing `integration`-marked tests already use.

## 1. Baseline: full ingestion establishes generation 1

```
POST /v1/ingest-repo  {"git_url": "<fixture repo>"}
```

Wait for `status: completed`. Then:

```
GET /v1/repos/{repo_id}/generation
```

Expect: `generation_status: "ready"`, `is_incremental: false`,
`parent_generation_id: null`, `commit_sha` set to the fixture repo's
resolved HEAD SHA at clone time.

## 2. Edit one file, re-ingest — confirm incremental path and SC-001

Edit exactly 1 file in the fixture repo (content change, not a
whitespace-only change — see spec Edge Cases for why whitespace-only
still counts as "changed"). Push/commit.

```
POST /v1/ingest-repo  {"git_url": "<fixture repo>"}
```

Expect: `is_incremental: true`, `parent_generation_id` = generation
1's `ingestion_id`, `commit_sha` = the new HEAD SHA. Measure wall-clock
time from accept to `completed`: SC-001's target is under 30 seconds
for a ~2,000-file fixture with this single-file edit.

Confirm re-embedding was actually skipped for unchanged files, not
just fast: query `vector_store_service` for the unchanged files'
chunks and confirm their `document_id`s match generation 1's (R1 — no
new UUIDs minted for unchanged files), and their `ingestion_id` now
reads generation 2's (FR-007b).

## 3. Delete a file, re-ingest — confirm FR-008/SC-003

Delete a file that had graph nodes and vectors. Re-ingest.

```
GET /v1/graph/repos/{repo_id}/nodes?canonical_ids=<deleted file's canonical_id>
```

Expect: no rows for that `canonical_id` or any of its symbol-level
children. Confirm via direct DB check (or an equivalent read path)
that no `vectors` rows reference that file's former `document_id`
either.

## 4. Equivalence check (FR-012/SC-002) — the acceptance bar

This is an automated CI test, not a manual step, but the manual
version for spot-checking: ingest the fixture repo fresh (generation
A, full), separately perform the edit-1-file-and-reingest flow from
step 2 against a *different* fresh clone (generation B, incremental,
same target commit as if A had been rebuilt from scratch at that
commit). Compare:

- Graph: same set of `(canonical_id, relation_type)` edges for both,
  ignoring `document_id`/`ingestion_id` (internal, not part of the
  equivalence claim).
- Vectors: same set of `(canonical_id, chunk_index, chunk_text)`
  tuples for both.
- Lineage: both record the same `commit_sha`.

The CI version of this (FR-012) scripts steps 1-3 above against a
fixture repo with deterministic scripted edits and asserts the same
comparisons programmatically.

## 5. Force-full-rebuild override (FR-005a)

```
POST /v1/ingest-repo  {"git_url": "<fixture repo>", "force_full_rebuild": true}
```

Expect: `is_incremental: false` even though a valid prior `ready`
generation existed; every file re-embedded (confirm via new
`document_id`s for every node, including files that didn't change);
`parent_generation_id` still set to the immediately prior generation
(lineage recorded, not skipped — FR-005a's explicit requirement).

## 6. Recovery fallback (FR-005 / Acceptance Scenario 3)

Simulate an interrupted prior ingestion (e.g. a generation left at
`status: failed` or `running` for the `repo_id` — same mechanism
existing ADR-050/ADR-049 recovery tests already use to produce this
state). Re-ingest.

Expect: `is_incremental: false` — falls back to full ingestion rather
than diffing against the inconsistent prior state, per FR-005.
