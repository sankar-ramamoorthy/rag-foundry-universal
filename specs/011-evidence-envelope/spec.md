# Evidence envelope on evidence-bearing responses

[Phase 6 implementation issue #406](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/406).
Plan: `DOCS/notes/20261120-evidence-api-assessment-404.md`.

## Contract

Each evidence-bearing orchestrator response gains one additive field,
`envelope`. Nothing already returned changes: no field is renamed, removed or
re-typed, and no route is added.

| Field | Meaning |
| --- | --- |
| `schema_version` | Envelope schema version, the string `"1"` |
| `repo_id` | Repository the response is about |
| `generation_id` | Generation the evidence came from, or `null` if the response does not say |
| `commit_sha` | Commit recorded for that generation, or `null` |
| `coverage` | `complete`, `partial` or `unknown` (see below) |
| `limitations` | Human-readable strings; empty only when there is nothing to qualify |

Covered responses: `POST /v1/rag` (including the Python inventory path),
`POST /v1/repos/{id}/evidence`, `GET /v1/repos/{id}/orient`,
`GET /v1/repos/{id}/trace` and `GET /v1/repos/{id}/impact`. `/v1/rag/simple`
(flat document RAG) is out of scope.

## Rules

- `generation_id` is the generation the response was computed from, never a
  re-read of "current". A stale generation still returns the existing 409.
- `commit_sha` comes from the ingestion service's generation lineage for that
  same generation. It is `null` when the generation recorded none, when the
  lookup fails, or when the generation changed between the response and the
  lookup. Each `null` adds a `limitations` entry saying why. A failed lookup
  never fails the request.
- `coverage` describes coverage of what was asked for, not of the repository:

| Response | `complete` | `partial` | `unknown` |
| --- | --- | --- | --- |
| RAG, verified Python inventory | completion `verified_complete` | `budget_limited` | any other completion |
| RAG, ordinary retrieval | never | always (ranked, bounded evidence) | generation missing |
| Evidence workflow | assessment `satisfied` | `partial` | `needs_clarification` |
| Orient | no gaps | one or more gaps | n/a |
| Trace and impact | not truncated or depth-limited | truncated or depth-limited | n/a |

- Static graph results (trace, impact) always carry a limitation that they are
  indexed relationships at that generation, not runtime behavior.
- `limitations` are derived from facts the service already holds (gaps,
  missing obligations, truncation); none is invented.

## Acceptance cases

| Case | Observable result |
| --- | --- |
| Any covered response | `envelope.generation_id` equals the generation used |
| Generation recorded a commit | `envelope.commit_sha` equals it |
| No commit recorded or lookup fails | `commit_sha` is `null` and a limitation says why |
| Existing consumers | Every previously returned field is unchanged; the full set of old fields and values is the same |
| Stale generation | Existing 409 behavior unchanged |
| Orient with gaps | `coverage` is `partial`; each gap appears as a limitation |
| Truncated trace | `coverage` is `partial` and the limitation names truncation |

## Non-goals

Structured citations (issue #407), new routes (#408), changing any retrieval,
ranking or generation behavior, and model calls. The envelope is computed from
data already in hand plus one cheap generation-lineage lookup.
