---
title: "Production verification: incremental provenance regression fix (issue #199, PR #237)"
date: 2026-09-20
type: test-results
status: complete
tags: [phase-6, provenance, issue-199, issue-200, production-verification]
related:
  - "[Stage C test results](/DOCS/test_results/2026-09-19-stage-c-authority-aware-sufficiency.md)"
  - "[ADR-053](/DOCS/adr/ADR-053-source-authority-provenance-model.md)"
  - "[Status](/DOCS/status.md)"
---

# Production verification: incremental provenance regression fix

## Why this record exists

PR #237 fixed a real gap found via production use (see the
[Stage C test results follow-up](/DOCS/test_results/2026-09-19-stage-c-authority-aware-sufficiency.md#follow-up-finding-incremental-ingestion-silently-dropped-vector-level-provenance)):
an incremental ingestion that reused an unchanged file's vectors never
refreshed that vector's `source_metadata.provenance`, so `/v1/rag`
silently served `unknown_provenance` for most of an incrementally
reused corpus while the graph path (TRACE/IMPACT/Stage C) stayed
correct. The fix was verified locally (unit + integration tests,
local docker-compose reproduction) before this pass. This document
records the follow-up: reproducing the *exact* failure condition in
production itself, after deployment, and confirming the fix holds.

## Sequence

1. **Prod cleared**: the repository was deleted from production first
   (`DELETE /v1/repos/{repo_id}`), confirmed empty via direct Postgres
   query (`scripts/verify_prod_empty.py`) — 0 rows in `document_nodes`,
   `document_relationships`, `vector_chunks`; only 9 unrelated,
   pre-migration (`repo_id IS NULL`, dated 2026-09-06 through
   2026-09-15) `ingestion_requests` rows remained, confirmed unrelated
   to this repository by direct inspection.
2. **Deployed** `main` @ `d7fbf874` (includes Stage A0-A5 `#200`,
   Stage B0-B3 `#199`, the `smoke_repo` classifier fix, Stage C, and
   PR #237's incremental-provenance fix) — confirmed via
   `GET /version`.
3. **Fresh full ingest**: `POST /v1/ingest-repo` against the now-empty
   database. `GET /v1/repos/{repo_id}/generation` confirmed
   `parent_generation_id: null`, `is_incremental: false` — a genuine
   full build, not a reuse of anything (there was nothing to reuse).
   `655` files, `9053` nodes.
4. **Provenance check on the fresh build**: `POST /v1/rag` with
   `claim_type=implemented_behavior` against a real query. Real
   implementation content (`rag_orchestrator/src/retrieval/
   evidence_sufficiency.py` and its symbols) read `concerns: []`; a
   documentation note correctly read
   `non_implementation_role_offered_as_implementation`. No
   `unknown_provenance` anywhere in the sample.
5. **Incremental re-ingest — the exact regression condition**:
   `POST /v1/ingest-repo` again immediately after, no source changes.
   `embed_progress` reported `chunks_persisted: 0` across `5281`
   processed nodes — **100% vector reuse, zero re-embedding**.
   `GET /v1/repos/{repo_id}/generation` confirmed
   `is_incremental: true`, `parent_generation_id` set to the prior
   generation. This is precisely the condition PR #237's bug required
   to reproduce (a reused, not re-embedded, vector).
6. **Provenance check after 100% reuse**: the same `/v1/rag` query
   repeated, identical results to step 4 — no `unknown_provenance`.
7. **Full-corpus database confirmation** (not just the sampled query):

   ```sql
   SELECT
     count(*) AS total,
     count(*) FILTER (WHERE source_metadata ? 'provenance') AS with_provenance,
     count(*) FILTER (WHERE NOT (source_metadata ? 'provenance')) AS missing_provenance
   FROM ingestion_service.vector_chunks
   WHERE repo_id = 'f7641840-ba13-5f9d-9ae6-87e1f924709d'
   ```

   **Result: `total=19490`, `with_provenance=19490`, `missing_provenance=0`.**

   Role distribution across the same 19,490 chunks:

   | role | count |
   |---|---|
   | documentation | 5637 |
   | implementation | 3389 |
   | unknown_mixed | 3050 |
   | test | 2888 |
   | historical | 2859 |
   | design | 1565 |
   | example_fixture | 102 |

   The non-zero `example_fixture` count confirms the `smoke_repo`/
   `role-subject-v2` classifier fix (PR #235) is not just present in
   code but is actively producing the expected classification on a
   real, fully-reused production corpus.

## What this establishes

PR #237 fixed the architectural gap, not merely "fresh ingestion looks
correct." The failure mode required a reused (not re-embedded) vector;
this pass reproduced exactly that condition in production — real
incremental reuse, `chunks_persisted: 0` — and found zero missing
provenance across the entire corpus, not a sample.

**Stage A (`#200`), Stage B (`#199`), Stage C (`#200` follow-up), and
the incremental-provenance regression fix (PR #237) are now
production-verified**, not only locally/unit-tested. This is
independent of, and does not substitute for, Stage A's still-open
formal frozen-evaluation gate (12-16 case, two-repo, statistical
false-sufficient-rate tracking) — that remains a separate, not-yet-run
piece of work.

## What comes next

With provenance itself no longer a suspect, the earlier orientation
finding — a `repository_overview` query answering "what is this
repository about?" without clearly stating it — becomes a genuine
*retrieval-policy* question (selection/ranking/prompting), not a
data-correctness one. That is explicitly out of Stage B/C's scope
(both are transport/diagnostics-only, by design) and belongs to
whatever future work addresses retrieval quality for repository-
overview-shaped questions.
