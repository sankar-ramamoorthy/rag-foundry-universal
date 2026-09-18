# Contract: `POST /v1/ingest-repo` — `force_full_rebuild` addition

Existing endpoint, `ingestion_service/src/api/v1/codebase_ingest.py`
(`RepoIngestRequest` / the `Form(...)`-based multipart variant at line
~311). Additive change only — every existing field/behavior is
unchanged.

## Request (new field)

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `force_full_rebuild` | `bool` | No | `false` | FR-005a. When `true`, bypasses FR-004's reuse classification entirely and performs a full ingestion, as if no prior generation existed — even if a valid prior `completed` generation exists. |

Both the JSON (`RepoIngestRequest`) and multipart `Form(...)` request
shapes gain this field, matching how `provider` is already present in
both.

## Behavior

- `force_full_rebuild` omitted or `false`: existing behavior, extended
  by FR-004/FR-005 — automatically incremental if a prior `completed`
  generation exists for the resolved `repo_id`, full otherwise.
- `force_full_rebuild: true`: always full, regardless of prior
  generation state. The resulting generation still records
  `parent_generation_id` (pointing at whatever generation was current
  before this request, if any) and the rest of lineage metadata
  (FR-005a) — it is a processing-mode override, not a lineage opt-out.

## Response

No change to the existing response shape (ingestion accepted,
`ingestion_id` returned). Lineage is not synchronously available at
accept time (ingestion is asynchronous, per the existing
`_background_ingest_repo` pattern) — it becomes readable via the
lineage endpoint (`ingest-repo-lineage.md`) once the ingestion reaches
`completed`.
