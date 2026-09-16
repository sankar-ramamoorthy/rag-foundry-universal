# Contract: `GET /v1/codebase/ingest-repo/{ingestion_id}` (additive change)

**Owning service**: `ingestion_service`
**Current implementation**: `ingestion_service/src/api/v1/codebase_ingest.py`
(`get_repo_ingest_status`, `RepoIngestResponse`)

## Current response shape (unchanged fields)

```json
{
  "ingestion_id": "649d038e-8d0f-43ea-8247-f491c2d4f90a",
  "status": "running"
}
```

## New response shape (additive)

```json
{
  "ingestion_id": "649d038e-8d0f-43ea-8247-f491c2d4f90a",
  "status": "running",
  "embed_progress": {
    "nodes_processed": 12000,
    "nodes_total": 23354
  }
}
```

- `embed_progress` is **optional** — `null`/absent before the embed stage
  begins (i.e. still in the graph-build/persist stage) and after it ends
  successfully callers should rely on `status == "completed"`, not on
  `embed_progress`, as the completion signal.
- `nodes_processed` / `nodes_total`: non-negative integers,
  `nodes_processed <= nodes_total` always holds (data-model.md Validation
  Rules).
- No existing field (`ingestion_id`, `status`) changes meaning, type, or
  presence. Existing callers (Gradio's `check_codebase_status`, any other
  API consumer) that only read `status` are unaffected.

## Backward compatibility

Purely additive per FR-005 and the spec's framing of progress as
"sub-stage detail," not a new lifecycle state (data-model.md). No version
bump or breaking-change process is triggered.

## Out of scope for this contract

- No new endpoint is introduced.
- No change to `POST /v1/codebase/ingest-repo` (submission) or to
  `DELETE /v1/repos/{repo_id}` (#158/PR #159).
- Surfacing `embed_progress` in the Gradio UI (`check_codebase_status`) is
  not required by this feature's acceptance criteria (SC-004 only requires
  the information to be *observable*, e.g. via this endpoint) — a UI
  enhancement can follow separately if wanted.
