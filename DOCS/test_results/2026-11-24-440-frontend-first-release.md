---
title: "#440 product frontend first-release verification: local stack, real models, real browser"
date: 2026-11-24
type: test-results
status: current
summary: "Local run of the verification plan on one small repository. Eleven of twelve steps passed in Chromium and over HTTP through the frontend origin (step 9 with a poor error message); step 6 (a citation with no range) was not run live. 19 of 19 citations across three real questions carried ranges and every one read back to the same interval (14 byte-identical to the cited passage, 5 identical except the final newline). The run found and fixed one real bug (Ask returned a bare 500) that unit tests with fakes had missed."
tags: [evaluation, results, frontend, citations, issue-440, development-diagnostic]
related:
  - "[Issue #440](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/440)"
  - "[Verification plan](/specs/016-product-frontend/verification-plan.md)"
  - "[First-release spec](/specs/016-product-frontend/spec.md)"
  - "[#416 live verification](/DOCS/test_results/2026-11-22-416-live-verification.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #440 first-release verification (local run)

**Evidence class: development measurement (ADR-054).** One small repository,
author-chosen questions, a local developer machine. Not a held-out claim and not
a statement about any deployed host. No host addresses or credentials are
recorded. The run contacted the owner's model host for embeddings and
generation, as the owner authorized for this run.

## What was tested

- **Tree:** local-only branch `verify/440-local`, `154f27ac9`, a merge of the
  verification-plan branch (`f791a3ba7`) and the Investigate branch
  (`bac296527`). Together these hold the product API (#432, #433), the contract
  (#434), the UI (#435, #436), the container (#437), and the Foundry side of
  Investigate (#439). The branches were later updated with the fix in the
  findings below.
- **Stack:** the four backend services from images built earlier, with their
  source bind-mounted from the tested tree; the frontend image built from the
  tested tree (`de4460721402`) behind the opt-in `frontend` profile; Gradio
  alongside. Investigate was left disabled (the default).
- **Database:** a throwaway Postgres volume migrated to head
  (`20261121_node_source_span`). The developer's existing dev database was not
  used or changed: it predates the line-span migration, and the first ingestion
  against it failed with `column "start_line" of relation "document_nodes" does
  not exist`.
- **Repository:** local path `/app/shared/chunkers` (4 Python files), repo
  `771297cb-6794-5aff-908a-8be00f877343`, generation
  `6ed60178-28bd-4fa6-a3bd-df471e23bf8a` (commit not recorded for a local path).
  A second generation, `666c549f-1018-42f7-8c1a-1ce3ecf561d9`, came from
  re-ingesting the same path (incremental reuse, 4 s).
- **Browser:** Chromium driven by Playwright through the frontend origin
  (`http://localhost:8080`); HTTP checks used the same origin.
- **Models:** the answering model reported by the service was `ollama/Qwen3:4b`.

## Results by step

| # | Step | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Select repository; readiness | **Pass** | Browser and HTTP: generation shown; "not recorded for this generation" for the commit. |
| 2 | Overview | **Pass** | Renders with the reported limits (heuristic fields, commit not recorded). |
| 3 | Locate path and basename | **Pass** | `base.py` matched with a verified definition span (lines 16-24); the page states it is file search; selecting a file opens it in the shared viewer. The glob returned all four files, no cursor. |
| 4 | Ask | **Pass** | Three real questions answered in 27.5 s, 20.7 s and 10.1 s through the frontend origin. The answer shows the generation, the limits and the consulted-passage label. |
| 5 | Ranged citation: highlighted text equals stored source | **Pass** | In the browser, the highlighted lines for `text.py` 278-304 (27 lines) equal the source route's text for that interval line by line. Over HTTP all 19 cited intervals read back with the same range (below). |
| 6 | Citation without a range | **Not run live** | The freshly indexed corpus produced no citation without a range. The behavior is covered by unit and UI tests only. |
| 7 | Range yield | **Pass, small sample** | 19 of 19 citations carried a range across three questions, and 7 of 7 on a fourth question after incremental reuse. Not comparable to the 88.4% Mealie figure in #416: different repository, Python only, three questions. No regression observed. |
| 8 | Generation change while a result is open | **Pass** | After the re-ingest, opening an old citation showed the stale notice and no source text; the next question was rejected with the stale banner; "Refresh and rerun my last question" produced an answer for the new generation only. |
| 9 | Orchestrator unavailable | **Pass, with a defect** | With the orchestrator stopped the UI showed an error and recovered once it returned (nginx re-resolved the upstream). The message was "Unexpected response", which is not helpful (finding 2). |
| 10 | Error contracts | **Pass** | Start beyond EOF and an inverted interval: `invalid_range` (416). More than 500 lines: `resource_limit`. Missing path: `not_found`. Wrong generation: `stale` (409). |
| 11 | Other API paths through the frontend origin | **Pass** | `/v1/rag` and `/v1/repos` returned 404 through port 8080; the product list worked. |
| 12 | Gradio alongside | **Pass** | Gradio on port 7860 loaded and answered a question (1,759 characters) while the frontend ran. |

Also observed: no Content Security Policy violations and no other console or
page errors during the browser run; the frontend process runs as a non-root
user.

## Citation range check (step 5, over HTTP)

For each of the 19 citations, the cited interval was read through
`GET /v1/product/repos/{id}/source` with the cited path, generation and lines.

- 19 of 19 returned the same start and end lines, and each response's own
  digest matched its returned text.
- The citation's passage digest versus the read-back text: **14 byte-identical,
  5 identical except for the final newline, 0 different.** A passage digest and
  a source-read digest therefore describe slightly different payloads, as the
  [API assessment](/DOCS/notes/20261123-frontend-api-assessment.md) warned. The
  UI never claims digest equality; it highlights the returned interval.

## Findings

1. **A real bug, found and fixed.** The first live Ask returned a bare HTTP 500.
   The pipeline returns its own result model, not `RAGResponse`, and the new Ask
   code asserted the latter; unit tests used a fake that already returned
   `RAGResponse`, so they passed. Fixed by coercing the result, plus a safety net
   so any unanticipated failure in a product route answers with the stable error
   body without leaking exception text. Regression tests cover both and fail
   against the old code. The fix is on every branch of the stack.
2. **Poor message when the orchestrator is down.** nginx answers 502 with an HTML
   body, which the client shows as "Unexpected response". It is visible and
   recoverable but should say the service is unavailable. Not fixed here;
   tracked as #450.
3. **The developer database must be migrated before any run.** The dev
   database used by Compose predates `20261121_node_source_span`; ingestion
   against it fails. Any new host, including the planned Linux one, needs
   `alembic upgrade head` before ingesting.
4. **First start is slow.** Containers resolve their dependencies at start (#41),
   so the ingestion service took about 2.5 minutes to become healthy; ingesting the
   4-file repository (25 nodes) took about two minutes, most of it embedding.

## Not verified

- Anything on a deployed host (the Linux run is next).
- A citation without a range, live (step 6).
- Markdown citation ranges (#430) and any repository with documents or other
  languages.
- Investigate against the real investigation service or any model run. The mode
  was disabled, and no run was made.
- Larger repositories, concurrent users, long answers, or any audience beyond a
  single local user (see the [access review](/DOCS/notes/20261124-product-api-access-enforcement-review.md)).
- Behavior with `INVESTIGATE_BACKEND=fixture` through the container.

## Reproducing

Plan: [verification-plan.md](/specs/016-product-frontend/verification-plan.md).
Raw captures (answers, step results, screenshots and the scripts used) are
indexed in `raw-index.json` under the prefix `2026-11-24-440-`; the files are
git-ignored.

## Status of #440

Not closed. Step 6 was not run live and step 9's message needs the follow-up.
The owner may accept step 6 as covered by tests, or it can be exercised on the
Linux host against a generation indexed before the line-span migration.
