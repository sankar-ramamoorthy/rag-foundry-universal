# Contract: `GET /v1/repos/{repo_id}/generation` — lineage fields addition

Existing endpoint (ADR-051, `ingestion_service/src/api/v1/repos.py`,
`RepoGenerationResponse`). Chosen over a new endpoint because it
already returns exactly "the current generation's identity" for a
`repo_id` — lineage is an enrichment of that same response, not a
distinct concern (FR-010's "existing or new read endpoint" is
satisfied by extending this one).

## Response (new fields)

Existing fields (unchanged): `repo_id`, `ingestion_id`,
`generation_status`.

New fields, all `Optional`, populated only when `generation_status ==
"ready"` (the ADR-051 vocabulary `generation_status` actually returns —
`ready`/`building`/`failed`/`unknown`; it never returns the literal
string `"completed"`, which is instead `ingestion_requests.status`'s
vocabulary at the DB layer). Mirrors the existing field's own
nullability pattern for a repository with no generation yet.

| Field | Type | Description |
|---|---|---|
| `commit_sha` | `str \| None` | FR-001/FR-009. The resolved source commit SHA for this generation; `None` for a non-git (`local_path`) ingestion. |
| `ingested_at` | `datetime \| None` | FR-009. When this generation completed. |
| `parent_generation_id` | `str \| None` | FR-009. The prior generation this one was built from; `None` for a repository's first-ever generation. |
| `is_incremental` | `bool` | Whether FR-004's reuse classification actually ran for this generation (`false` for a full or forced-full ingestion). |

Per spec Assumptions: this endpoint does **not** expose per-file
fingerprint data — only generation-level lineage. Per-file
`content_hash` values remain internal change-detection state.

## Example

```json
{
  "repo_id": "c2675711-53a7-5a62-8b1c-edb61c50a695",
  "ingestion_id": "649d038e-8d0f-43ea-8247-f491c2d4f90a",
  "generation_status": "ready",
  "commit_sha": "a1b2c3d4e5f6...",
  "ingested_at": "2026-09-18T14:32:07Z",
  "parent_generation_id": "12040f1c-...",
  "is_incremental": true
}
```
