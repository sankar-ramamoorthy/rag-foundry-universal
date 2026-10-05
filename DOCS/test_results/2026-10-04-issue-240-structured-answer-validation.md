---
title: "Issue #240 structured-answer and validation experiment"
date: 2026-10-04
type: test-result
status: complete
tags: [repository-intelligence, structured-answer, evaluation]
related:
  - "[Prior typed-fact experiment](/DOCS/test_results/2026-10-04-issue-240-typed-fact-experiments.md)"
  - "[Frozen overview protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
---

# Structured-answer and validation experiment

The preceding Q2–Q4 runs showed that better prompt facts did not prevent
omitted fields, `UNKNOWN`-to-absence conversion, or mixed relationship types.
This follow-up tests a different path: deterministic observations become typed
objects; validators check those objects against the observations; fixed
renderers turn the validated objects into answers. It does **not** add another
general authority prompt.

## Snapshot and source proof

The experiment read the same selected repository
`f7641840-ba13-5f9d-9ae6-87e1f924709d`, ready generation
`f873147c-a1d1-4891-bb98-972672db8e9a`, and source commit
`7a805d5b3cee031c44fbe0d9b8048065ce8ef039`. Generation reads before
and after matched. ORIENT and the 9,068-node graph came from ingestion's
read-only APIs. The graph API does not expose Compose file text or its own
generation ID, so the run fenced the graph read with the generation checks.

For Q4, the script read local `docker-compose.yml` and
`docker-compose.test.yml` only after checking their Git blob hashes against
GitHub's file blobs at the exact source commit. The hashes matched:
`7dc65b11e177eab96d2d7aeeec3ea8d658995679` and
`e66f3755ab0ba30e534b955bbfda30cb8a290c39`. Windows checkout CRLF
was normalized to Git's LF blob bytes for the comparison. The run did not
read or change production database content. Other Compose files, including
the production override, were outside this experiment's source scope.

## Three isolated results

| Case | Structured check | Rendered result |
| --- | --- | --- |
| Q2 | Six service-keyed rows; nine declarations; required Compose, repository directory, indexed implementation source, Dockerfile, direct manifest, test directory, package state, and language-count fields match ORIENT/graph. Nested fixture Cargo manifests and test fixture language files are excluded from service implementation fields. | All six rows and whole-repository totals appear. The output is 2,644 characters. |
| Q3 | Package state is one of `OBSERVED`, `UNKNOWN`, `PROVEN_ABSENT`. The pinned graph establishes markers for four services; `gradio` and `postgres` remain `UNKNOWN`. A mutation test changing `UNKNOWN` to `PROVEN_ABSENT` is rejected. | `gradio/` is observed as a repository directory, while its package state remains `UNKNOWN`; no absence claim is rendered. The output is 2,406 characters. |
| Q4 | `components`, `http_edges`, `datastore_edges`, `deployment_edges`, and `ports` are separate fields. Graph `CALLS_SERVICE` edges retain heuristic labels. Compose URLs establish configured app HTTP links; `DATABASE_URL` establishes datastore configuration, and `depends_on` establishes startup dependencies only. | PostgreSQL is a datastore, not an HTTP application. Main Compose publishes `5434:5432`; test Compose publishes `5433:5432`. The output is 2,490 characters. |

All three structured validators returned no errors. The full objects,
rendered answers, generation fence, and Compose blob proofs are in the
[machine-readable record](/DOCS/test_results/2026-10-04-issue-240-structured-answer.json).
The experiment is reproducible with
[`scripts/issue240_structured_answer_eval.py`](/scripts/issue240_structured_answer_eval.py).

## Model-output check

A separate read-only [Qwen structured-output run](/DOCS/test_results/2026-10-04-issue-240-llm-structured.json)
gave `ollama/Qwen3:4b` a compact, already validated claim object for each
case and asked it to return JSON with identical fields and values. The
[reproduction script](/scripts/issue240_llm_structured_eval.py) checked the
generation before and after each request and accepted only an exact object
match before any prose rendering.

All three candidate objects were rejected. Q2 returned parseable JSON but
nested the other five service rows under `gradio`, leaving only one top-level
service key. Q3 and Q4 returned prose claiming no repository claim object was
provided, despite the object being sent in `context`. This is a single run per
case, so it measures this bounded candidate, not a general limit of the
model or every possible structured-output API. It does show that asking this
model through the current `/generate` text interface to copy typed facts is
not an adequate validation strategy.

| Case | Saved failure classification | Observed failure mode |
| --- | --- | --- |
| Q2 | `semantic_or_field_mismatch` | Structural mutation: valid JSON, but five service rows became nested beneath other rows instead of remaining top-level service keys. |
| Q3 | `invalid_json` | Syntax/contract failure: prose said the context contained no repository claim object; no JSON object was parsed. |
| Q4 | `invalid_json` | Syntax/contract failure: prose said the context contained no repository claim object; no JSON object was parsed. |

These are the classifications recorded by the copy-check script. The Q3/Q4
responses were prose, not evidence that the supplied claim objects were
actually absent. This run did not observe a standalone state mutation, type
conflation, or value mutation in a parsed Q3/Q4 object. Future model-output
evaluations should classify syntax failure, structural mutation, state
mutation, type conflation, and value mutation separately rather than grouping
them as a generic generation error.

## Interpretation and gate

This establishes that the available evidence can support complete, typed
Q2–Q4 answers when finite facts are derived and validated before rendering.
The follow-up model-output check rejected all three objects; it did not test
free-form paraphrasing. Neither run tests Q1, Q5–Q7, or controls C1–C3
through `/v1/rag`. The current runtime
still uses the prior default-off typed-fact prompt experiment, and this
standalone structured path is not wired into the HTTP answer route. The #240
merge and deployment gate remains unmet.

The specific next boundary is a read-only, generation-pinned source-content
API for Compose (or an equivalent trusted source) and an HTTP candidate that
enforces these result schemas. If an LLM is allowed to verbalize the result,
its claims still need validation against the typed object. A further prompt
instruction alone is not evidence of that property.

For mechanically derivable repository claims, the typed object is the
validation boundary: an LLM may help before or after it, but must not replace
it as the source of repository facts. The next HTTP candidate should select a
claim family, build typed evidence, validate its schema and semantics, and
render only the validated object. The present result does not justify a model
replacement or a claim that structured answers have passed the #240 gate.

Local checks: 298 orchestrator unit tests passed (25 deselected), focused
structured-result tests passed, Ruff passed, and Pyright passed.
