---
title: "#416 live verification on Mealie: yield, audit, incremental reuse, citations"
date: 2026-11-22
type: test-results
status: current
summary: "Development measurement on the deployed stack (SHA f2e3f2a). Per-window source ranges: 15,619 of 17,676 passages (88.4%) carry a range, 100% of passages whose artifact range is verified. The audit found zero wrong ranges among readable sources; 33 of 1,000 sampled ranges are Markdown that the source reader cannot serve (HTTP 422). The no-change incremental ingest completed in under nine minutes with zero re-embedding and 17,676 of 17,676 passages patched; /v1/rag citations with a range rose from 1 of 5 to 18 of 19."
tags: [evaluation, results, citations, source-spans, incremental-ingestion, issue-416, development-diagnostic]
related:
  - "[Issue #416](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/416)"
  - "[Baseline](/DOCS/test_results/2026-11-21-412-mealie-span-baseline.md)"
  - "[Retag timeout and generation promotion](/DOCS/notes/20261122-retag-timeout-and-generation-promotion.md)"
  - "[Spec 015](/specs/015-per-window-source-ranges/spec.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #416 live verification on Mealie

**Evidence class: development measurement (ADR-054).** One repository, one pinned
commit, author-chosen questions. Not a held-out claim. Read-only apart from the
ingestions the owner authorized. No host addresses or credentials are recorded.

## Setup

- Repository `sankar-ramamoorthy/mealie`, repo id `7da95a1b-11dc-5f74-8d3b-fabe24489ad7`,
  commit `1624c22bf70988c7fe404ad586e2f9689f77748d`.
- Deployed SHA `f2e3f2a94817d94828b616967cc4cb2283e2798c` on all four services
  (release `prod-2026-11-21-2108pm`); migration head `20261121_node_source_span`.
- Generations: baseline `1f1a7949…` (before #416); full rebuild `d269df5b…`;
  recovery rebuild `a7db229b…` (after a failed first incremental run, see the
  timeout note); no-change incremental `eb171cd9-2c25-4d86-a7f9-96664435c740`.

## 1. Yield (full rebuild, matches the offline projection exactly)

| Measure | Baseline | After |
| --- | --- | --- |
| Passages with a range | 4,556 of 17,676 (25.8%) | 15,619 (88.4%) |
| Share of passages whose artifact range is verified | n/a | 100% |
| Null, `artifact range not verified` | n/a | 2,057 (TypeScript `export` and Markdown sections; #417) |
| Null with no reason or an unknown reason | n/a | 0 |

## 2. Audit (`scripts/audit_source_ranges.py`, seed 416, 1,000 passages, pinned generation)

| Outcome | Full rebuild | Incremental |
| --- | --- | --- |
| Range resolves to the exact passage through `/source/read` | 967 | 967 |
| `read_error` (HTTP 422, `SOURCE_UNAVAILABLE`) | 33 | 33 |
| Wrong range (mismatch, out of bounds, generation changed) | 0 | 0 |

All 33 are Markdown files; the failing set is identical in both runs. The source
reader does not serve Markdown (open decision A), so those 576 ranged passages (3.7%
of ranged passages; whole-file Markdown modules) cannot be resolved through the
reader. They are reported as unverifiable, not as verified. The run exits 1 for that
reason, correctly.

## 3. Incremental ingest with no file changes

Ingestion `eb171cd9…`: `completed` in under nine minutes, `is_incremental: true`, parent
`a7db229b…`. Final result in `embed_progress`:

| Field | Value |
| --- | --- |
| `chunks_persisted` (re-embedded) | 0 |
| `ranges_outcome` | `patched` |
| `ranges_requested` / `ranges_patched` / `ranges_skipped` | 17,676 / 17,676 / 0 |
| `ranges_retried_batches`, `ranges_unsupported` | 0, false |

After the run: all 17,676 vector rows and all 21,621 nodes belong to the new
generation; 15,619 rows carry a range and the only null reason is
`artifact range not verified` (2,057), identical to before; the audit result above is
unchanged. The earlier failure (13,721 moved, 3,955 not; read timeout) did not recur.

## 4. `/v1/rag` citations

| Question | Citations | With a range |
| --- | --- | --- |
| How does password reset token generation work? | 5 | 5 |
| How are recipes imported from a URL? | 7 | 6 |
| How does a user log in and get an access token? | 7 | 7 |
| Total | 19 | 18 (95%) |

Before #416 the same first question returned 5 citations with 1 range. Four of the
ranged citations in the second question are Markdown (`bulk-url-import.md`) and so
cannot be resolved through the reader; the one null citation is a Markdown section
(`artifact range not verified`).

## Remaining gaps

1. Markdown readability (decision A): 576 ranged passages cannot be verified through
   the reader.
2. #417: 2,057 passages (11.6%) have no range until same-line prefixes and Markdown
   sections are handled.
3. A failed incremental run still leaves no servable generation until the next full run
   completes (availability, issue #286).
4. One repository, one commit: no generalization claim.

## Reproduction

```text
python scripts/audit_source_ranges.py --repo-id <uuid> --generation-id <uuid> \
    --seed 416 --sample-size 1000 --acceptance --out audit.json
```

with `FOUNDRY_ORCHESTRATOR_URL` and a read-only `FOUNDRY_AUDIT_DSN` in the environment.
Raw results are under `DOCS/test_results/_raw/416/` and listed in the raw index.
