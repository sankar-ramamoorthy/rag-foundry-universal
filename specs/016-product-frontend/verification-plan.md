# Product frontend first-release verification plan (#440)

**Status:** Proposed, not yet run. Nothing in this file is evidence; it is the
procedure that produces evidence.

**Tracking:** Phase 6, [#440](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/440),
part of [#402](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/402).
Implements the plan's release gate in [plan.md](plan.md) and the acceptance
criteria in [spec.md](spec.md).

## What this verifies

That the accepted Ask flows work end to end through the intended API boundary
on a known indexed revision, and that cited ranges resolve to the stored source
the viewer displays. The unit and fixture tests (#432-#437) show the pieces
behave against fakes; only this run shows them working together.

## Who runs what

- **Local stack runs** (the developer's own Compose stack) may be run by an
  agent when the owner authorizes contact with the model host. They contact the
  owner's Ollama host and spend model time, so they need an explicit go-ahead.
- **Deployed runs** are the operator's. An agent does not deploy or change the
  running release. Read-only HTTP GETs against a deployed stack are allowed only
  when the owner asks, and only within
  [agent-execution-and-verification.md](/DOCS/deployment/agent-execution-and-verification.md).
- Production exposure is a separate decision (#438). This run does not
  establish that the product API is safe to expose.

## Preconditions

1. The #432-#437 PRs are merged to `main` and CI is green on the commit under
   test. Record that commit SHA and the SHA of every running image.
2. A **known indexed revision**: one repository with a ready generation, its
   generation ID and commit recorded before the run. Prefer a repository that
   already has live citation-range evidence (the #416 Mealie verification) so
   range yield is known in advance.
3. The stack is up with the opt-in profile:
   `docker compose --profile frontend up --build`, frontend on port 8080.
4. Endpoints come from environment variables or the local endpoints file, never
   from this repository (no private addresses in code, config or reports).

## Procedure and pass criteria

Record each step's result, the request and response (or a screenshot) and the
time. Raw captures go to `DOCS/test_results/_raw/` and are indexed with
`scripts/raw_index.py update`; the report links the index, not the raw files.

| # | Step | Pass when |
| --- | --- | --- |
| 1 | Open the frontend origin. Select the known repository. | Readiness shows the recorded generation ID, and the commit if it was recorded (otherwise "not recorded for this generation"). |
| 2 | Open the overview. | It renders without error and shows the limits the backend reports. |
| 3 | Search a known path and a known basename. | Matches appear; an ambiguous basename keeps every match selectable; the page states it is file search. |
| 4 | Ask a question the repository can answer. | An answer appears with the indexed generation, evidence limits, and consulted passages. |
| 5 | Open a citation that has a range. | The viewer shows the same generation, highlights exactly the cited lines, and **the highlighted text equals the stored source for that interval**. Verify by reading the same interval through `GET /v1/product/repos/{id}/source` and comparing the returned digest and text. |
| 6 | Open a citation without a range. | It stays visible with its stated reason; opening the file highlights nothing. |
| 7 | Compare citation range yield with the recorded #416 figure for the same generation. | The yield matches or the difference is explained. A drop is a finding, not a pass. |
| 8 | Force a generation change (re-ingest or a new commit) while a result is open, then open the earlier citation. | The old citation never opens against the newer generation; the stale banner appears; refresh and rerun produce a result for the current generation. |
| 9 | Make the orchestrator unavailable (stop it) and use the UI. | Errors are visible and recoverable; nothing renders stale results as current. |
| 10 | Request a read over 500 lines and a start line beyond the end of a file through the API. | `resource_limit` and `invalid_range` error bodies, not a crash. |
| 11 | With the frontend origin, request `/v1/rag` and `/v1/repos`. | Both return 404 through that origin. |
| 12 | Confirm Gradio still answers on its own port with the frontend profile running. | Gradio loads and answers a question. |

A step that cannot be run is recorded as **not run**, with the reason; it is
never marked passed.

## Report

Write `DOCS/test_results/<date>-440-frontend-first-release.md` with: the
commit and image SHAs, the repository, generation and commit, each step's
result, the range-yield comparison, what was **not** verified (for example any
audience beyond a single user, Markdown ranges #430, Investigate), and the raw
index link. Update `DOCS/status.md` in the same PR. #440 closes only when every
step is passed or explicitly accepted as a known limitation by the owner.

## Investigate

A second pass covers Investigate once #439 ships. It additionally verifies a
partial run's explicit stop reason, rejection of a stale-generation result, and
that Ask stays usable when the agent service is unavailable. It needs the
owner's authorization to run a model profile.
