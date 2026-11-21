# Source read and locate through the orchestrator

[Phase 6 implementation issue #408](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/408).
Depends on the evidence envelope (`specs/011-evidence-envelope/spec.md`).
Reuses the source navigation API (`DOCS/architecture/source-navigation-api.md`)
and the verified Python inventory in `execution_policy.py`.

## Routes

Three read-only GET routes in the orchestrator. No new storage, no model call.

| Route | Behavior |
| --- | --- |
| `GET /v1/repos/{id}/source/files` | Proxies the ingestion file listing. Query: `generation_id` (optional), `pattern`, `limit`, `cursor` |
| `GET /v1/repos/{id}/source/read` | Proxies the bounded source read. Query: `generation_id` (optional), `path`, `start_line`, `end_line` |
| `GET /v1/repos/{id}/locate` | Candidate files and Python definitions for a path or glob. Query: `query`, `generation_id` (optional), `limit`, `include_definitions` |

When `generation_id` is omitted the orchestrator resolves the repository's
current ready generation once and uses it; the ingestion service still
enforces the generation fence. Every successful body keeps the ingestion
fields unchanged and adds `envelope` (spec 011).

## Errors

An ingestion-service error is returned with its own status and JSON body
(`error_code`, `message`, `details`). An unreachable ingestion service is 502.
A read whose `returned_text_sha256` does not match the returned text is 502.
A non-UUID repository or generation id on `locate` is 400.

## Locate

`query` is a path, glob or basename. A basename (no `/`, no glob characters)
matches `**/<name>`. Matching is exactly the file listing's glob semantics.
Each candidate reports `path`, `canonical_id`, `doc_type`, `source_status`,
`match` (`glob` or `basename`) and definitions:

- Python source files (up to 5 candidates, when `include_definitions` is true)
  get `definitions`, the same names and spans as a whole-module AST parse,
  via the verified paged inventory, with `definitions_status`
  `verified_complete`, or the inventory's stop reason if it could not finish.
- Other languages and files beyond the cap get `definitions: null` and a
  `definitions_status` of `not_covered_language` or `not_attempted`.
  Absence of coverage is never reported as an empty result.

`coverage` is `complete` only when there is no further page and every
requested definition inventory is verified; otherwise `partial` with the
reasons in `limitations`. Locate matches paths only: definition-name and
semantic search are not part of it, and a limitation says so.

## Acceptance cases

| Case | Observable result |
| --- | --- |
| Read | Same text and digest as the ingestion service; stale generation conflict returned unchanged |
| Locate a named Python file | Definitions equal a whole-module AST parse; zero model calls |
| Locate a TypeScript or Markdown path | Candidate listed, `definitions: null`, status `not_covered_language`, coverage `partial` |
| No match | 200 with an empty candidate list and a limitation, not an error |
| Omitted generation | Envelope `generation_id` is the resolved ready generation |
| Digest mismatch on read | 502 |

## Non-goals

Markdown readability, definition-name or semantic search, relationships,
investigate, and any ingestion-service change.
