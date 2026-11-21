---
title: "#412 live verification and Mealie span-coverage baseline"
date: 2026-11-21
type: test-results
status: current
summary: "Development measurement after deploying #412 (SHA d7710d6, migration 20261121_node_source_span) and a full Mealie rebuild at commit 1624c22. Verified ranges resolve correctly where present, but only 25.8% of passages carry one. This is the baseline for the two follow-ups: per-window ranges (#416) and same-line-prefix support (#417)."
tags: [evaluation, results, citations, source-spans, issue-412, issue-416, issue-417, development-diagnostic]
related:
  - "[Issue #412](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/412)"
  - "[Issue #416, per-window ranges](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/416)"
  - "[Issue #417, same-line prefix](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/417)"
  - "[Spec 014](/specs/014-persisted-source-spans/spec.md)"
---

# #412 live verification and Mealie span-coverage baseline

**Evidence class: development measurement.** One repository, one generation.
No held-out claim. Read-only: HTTP GETs, one `/v1/rag` query, and SELECT-only
SQL on the dev host. No host addresses or credentials are recorded here.

## Setup

- Deployed SHA `d7710d6130425ffa6b79b919ad69ba0185a01500` on all four services
  (release `prod-2026-11-21-1002am`), equal to `main` after PR #415.
- Database migration head `20261121_node_source_span`.
- Repository `sankar-ramamoorthy/mealie` at commit `1624c22`, full rebuild
  (`force_full_rebuild=true`), generation
  `1f1a7949-e37a-4d13-abb9-21015c49d5f2`, 7,758 embedded nodes, 17,676 passages.

## Results

| Measure | Result |
| --- | --- |
| Non-empty source-type nodes with a verified range | 6,696 of 7,400 (90.5%) |
| Python nodes with text | 100% verified |
| Unverified TypeScript / JavaScript nodes | 703 / 1 |
| Passages with a range | 4,556 of 17,676 (25.8%) |
| Passages with no range: `artifact split into several passages` | 11,063 (62.6%) |
| Passages with no range: `range not verified at ingestion` | 2,057 (11.6%) |

## What was verified live

- `locate` on `password_reset_service.py` returned 6 verified definitions with
  line ranges, the generation, and the commit.
- `source/read` of lines 22-40 began at `def generate_reset_token` and ended at
  its `return`; the returned-text digest matched.
- A `/v1/rag` answer returned 5 citations, 1 with a range (lines 77-84 of
  `admin_management_users.py`); reading those lines through `source/read`
  returned exactly that method.
- The deleted repository `rag-foundry-universal` left 0 nodes, relationships,
  vector chunks and ingestion requests, and no orphan vector chunks exist.

## Why coverage is low

- **Passages (62.6%).** Code artifacts are chunked into overlapping exact line
  windows, so even small methods are several passages. #412 gives a range only
  to single-passage artifacts. Tracked by #416 (priority).
- **TypeScript nodes (11.6% of passages).** For `export interface X {...}` the
  stored text omits `export` while the extractor span covers the whole line;
  the verifier requires whitespace before the text, so it rejects it. The lines
  do contain the text exactly. Tracked by #417.

## Reproduction

SELECT-only queries over schema `ingestion_service` (session set read-only):

```sql
-- nodes by type: total vs with a range
select doc_type, count(*), count(start_line)
from ingestion_service.document_nodes where repo_id = :repo group by 1;

-- passages by range outcome
select (source_metadata->>'start_line') is not null as has_range,
       source_metadata->>'range_reason' as reason, count(*)
from ingestion_service.vector_chunks where repo_id = :repo group by 1, 2;
```

## Limits

Single repository, single generation, author-chosen query. The 25.8% is a
baseline, not a target. Reuse (an incremental ingest with no changes keeping its
ranges) was not exercised.
