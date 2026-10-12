---
title: "Issues #257/#254 (normal-mode): production verification"
date: 2026-10-11
type: test-result
status: verified
tags: [retrieval, graph-expansion, context-allocation, issue-254, issue-257, production]
related:
  - "[Issue #254](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/254)"
  - "[Issue #257](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/257)"
  - "[PR #258 (structural discovery)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/258)"
  - "[PR #259 (context-allocation priority)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/259)"
  - "[Seed-ranking and graph-expansion checkpoint](/DOCS/test_results/2026-10-11-issue-254-seed-ranking-and-graph-expansion-checkpoint.md)"
  - "[Pinned R1/R2 replay](/DOCS/test_results/2026-10-11-issue-254-pinned-replay.md)"
---

# Issues #257/#254 (normal-mode): production verification

First complete, production-verified correction of the original #254
normal-mode symptom: the authoritative `py_mono/agent/agent.py#Agent.run`
method, named explicitly in the query, is now discovered, fetched,
prioritized into final context, and cited directly in the generated
answer — none of which happened before PRs #258/#259.

No `top_k` increase, context-budget increase, embedding-model change, or
re-ingestion was used to achieve this. Two targeted, independently tested
retrieval-pipeline corrections were made and verified in isolation before
being confirmed together in production.

## Deployment identity

- Deployed git SHA (all three services): `f34078c6d8863270da5df751e54f371647243c72`
  — `origin/main` tip, containing PR #258 (`f2e9080`) and PR #259
  (`7de18c6`), merged via `c36975a`/`f34078c`.
- Release label: `prod-2026-10-11-1741pm`.
- Repository: `863e770d-651e-5bc5-83d1-a1409693e707`.
- Generation: `24f827d7-a33b-45f7-93f4-ff6e5eaf3856`, `commit_sha`
  `f854303e6e44ff95d94792d24868442a28080ba2`, unchanged throughout — no
  re-ingestion was performed or needed; both fixes are orchestrator-only
  (`rag_orchestrator/src/retrieval/traversal_selector.py`,
  `rag_orchestrator/src/core/service.py`), with no `ingestion_service` or
  schema change.

## Request

```json
{
  "query": "Using `py_mono/main.py#main`, `py_mono/ui/cli.py#start_cli`, and `py_mono/agent/agent.py#Agent.run`, trace a normal user prompt through a tool call and the tool result returning to the LLM.",
  "repo_id": "863e770d-651e-5bc5-83d1-a1409693e707",
  "top_k": 10,
  "rerank": false,
  "trace_canonical_ids": [
    "py_mono/main.py#main",
    "py_mono/ui/cli.py#start_cli",
    "py_mono/agent/agent.py#Agent.run"
  ]
}
```

Issued as a direct, read-only `POST /v1/rag` to the deployed orchestrator
(`http://100.105.24.12:8004/v1/rag`), HTTP 200 in 29.8s.

## Pipeline-stage result

| Stage | Before #258/#259 | Production now |
| --- | --- | --- |
| Vector seeds | `agent_backupv1.py` outranks `agent.py` (confirmed, [seed-ranking checkpoint](/DOCS/test_results/2026-10-11-issue-254-seed-ranking-and-graph-expansion-checkpoint.md)) | Same underlying index/ranking — unchanged, not in scope for #257/#254 |
| Structural discovery | `agent.py#Agent.run` never a candidate (DEFINES edge existed, never traversed) | **Pass** — admitted via `expand_mentioned_methods` (#257) |
| Graph expansion | Correct method unreachable from a non-seed class node | **Pass** |
| Evidence fetching | Correct chunks never fetched | **Pass** — confirmed via `expansion_metadata`/`chunks_returned_by_document` |
| Context allocation | Seed-first `document_order` exhausted the 4096-byte budget before reaching it (measured: position 21-23, ~180-210 bytes remaining, needs 261+) | **Pass** — `explicit_mention_document_ids` promotes it ahead of seeds (#254/#259) |
| Final context | Absent from `final_context_manifest` | **2 chunks present** (415, 216 bytes), `selection_reason: "expanded via DEFINES from agent.py#Agent"` |
| `sources` | Did not include `agent.py#Agent.run` | **First entry**: `["py_mono/agent/agent.py#Agent.run", ...]` |
| Generated answer | No direct authoritative citation | **Directly cites it**: *"`py_mono/agent/agent.py#Agent.run` receives the i[nput]..."* |

`retrieval_plan.explicit_mention_document_ids` in the live response:
`["1df63689-0e14-4c9f-b976-a6395e9d633b"]` — confirms both corrections
active in the deployed build, not just discoverable locally.

## What this does not resolve

- **`repository_overview` mode.** A separate smoke check (same repo/
  generation, overview-mode request variants) confirmed the method's
  chunks are promoted all the way to position 0-7 in chunk-selection
  order (no longer excluded by the byte budget), but are still excluded
  — now at a distinct `overview_policy` stage, unrelated to context
  allocation. Whether excluding method-level evidence for an explicit
  query like this is correct or a defect depends on that policy's
  intended semantics for method-level questions; not evaluated here, and
  not changed by #258/#259. Tracked as a separate, narrowly scoped
  question under #254.
- **The historical seed-set discrepancy.** The original deployed-control
  capture (5 minutes before the first local replay, same day) returned a
  different seed set than every capture since. Embedding model/digest,
  orchestrator code path, and ANN determinism were each individually
  ruled out as causes (see the [seed-ranking checkpoint](/DOCS/test_results/2026-10-11-issue-254-seed-ranking-and-graph-expansion-checkpoint.md)).
  The remaining candidate — index-state drift during incremental-
  generation retag settling — was never proven. This stays an
  **unresolved diagnostic observation**, not a claimed root cause, and
  does not block the verification above (the vector-seed stage was
  already outside #257/#254's scope).

## Status

- **#257** (structural discovery): merged (#258), acceptance criteria
  met, production-verified above. Candidate for closing.
- **#254** (evidence delivery), normal-mode sub-case: production-
  verified fixed above.
- **#254**, repository-overview-mode sub-case: open, separate
  investigation needed before any policy change.
- **#254**, historical seed-set discrepancy: open, unresolved diagnostic
  observation.

No further retrieval-pipeline changes made or proposed at this
checkpoint. Next step is deciding whether overview-mode's exclusion of
method-level evidence violates its intended policy — not changing that
policy merely to make every query mode produce the same answer.
