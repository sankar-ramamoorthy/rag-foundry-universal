---
title: "Stage A5: evidence-sufficiency live verification (reduced scope)"
date: 2026-09-19
type: test-results
status: complete
tags: [phase-6, evidence, sufficiency, issue-200]
related:
  - "[Spec 007](/specs/007-bounded-evidence-sufficiency/spec.md)"
  - "[Phase 6 handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md)"
  - "[Status](/DOCS/status.md)"
---

# Stage A5: live verification, reduced scope

## What this is and isn't

The handoff's Stage A5 release gate calls for a frozen 12-16 case
paired evaluation across two differently-organized repositories, with
per-case sufficiency correctness, false-sufficient-rate, and
useful-vs-unnecessary-repair tracking. **That full gate was not run.**
This document instead records a real, live, HTTP-level verification of
Stage A0-A4's mechanics against an actually-ingested repository through
the real `docker-compose` dev stack (`ingestion_service`,
`vector_store_service`, `llm_service`, `rag_orchestrator`, local
Postgres+pgvector) — not unit-test mocks. Scope was reduced from the
full methodology because ingesting this repository's ~5,100-node full
graph via local (non-remote) Ollama embeddings measured ~0.4 nodes/sec
(~4.5 hours), impractical for this pass; `shared/` (67 code/doc nodes)
was ingested instead as a small, real, differently-shaped corpus.

**Conclusion: mechanics PASS on every case run. Formal release-gate
sign-off (12-16 frozen cases, two repos, false-sufficient rate,
repair-usefulness tracking, generation-fence race tests under load) is
INCONCLUSIVE — not attempted, not claimed. Default-on behavior stays
gated on that fuller evaluation, per the handoff's explicit instruction
to record inconclusive and keep new behavior opt-in when sample size is
inadequate.** Nothing about Stage A0-A4's code changed as a result of
this pass; no defects were found.

## Environment

- Local `docker-compose.yml` stack, rebuilt from `main` @ `5ff7a9d`
  (post-PR #228, all of Stage A0-A4 merged).
- Postgres 15+pgvector, `ingestion_db`, migrated to head (no pending
  migrations at time of run).
- Embeddings: `mxbai-embed-large` via local Ollama
  (`host.docker.internal:11434`). Generation (Stage A4 explanation
  phase): `llm_service` → `ollama/Qwen3:4b` (local).
- Corpus: `shared/` (this repo's own `shared/` directory), ingested
  fresh via `POST /v1/ingest-repo {local_path: "/app/shared",
  force_full_rebuild: true}` → `repo_id=3ab62236-f1c3-50d8-ba49-0e434a34c0c3`,
  `ingestion_id=c893482a-2004-49f3-a366-fb474a5d99c8`. 67 code/doc nodes
  (25 Python files, 1 Markdown), confirmed via `GET /v1/repos/{repo_id}/orient`
  (`generation_status: "ready"`).
- All calls below hit `rag_orchestrator` on `localhost:8004`, exactly
  the client-facing surface (`/v1/repos/{repo_id}/evidence`), not an
  internal function call.

## Cases run and results

| # | Mode | Case | Expected | Observed | Pass? |
|---|---|---|---|---|---|
| 1 | ORIENT | required_facets=[languages, file_counts] (both populated) | satisfied | `status=satisfied`, both obligations `satisfied` | ✅ |
| 2 | ORIENT | required_facets=[manifests, services] (empty, no gap entry) | `unknown`, not `missing` (no manufactured gap) | `status=partial`, both `unknown`, reason codes `*:unsupported_facet` | ✅ |
| 3 | TRACE | start + required_target one CALL hop away | satisfied, target hop cited | `status=satisfied`, evidence cites the real hop + relation_type | ✅ |
| 4 | TRACE | start + required_target not in graph, full frontier explored | `missing`, no repair (no useful action) | `status=partial`, `target=missing`, `stop_reason=no_useful_repair` | ✅ |
| 5 | TRACE | start + a real 2-hop target, `max_depth=1` | depth cap hit → one bounded repair to server ceiling → target found | `traced_path` (no_progress) then `extend_frontier_to_server_ceiling` (progress); final `status=satisfied`, `stop_reason=repair_applied` | ✅ |
| 6 | TRACE | `start=does_not_exist_symbol` | `unresolved_start`, no repair, no crash | `status=partial`, `stop_reason=unresolved_start`, `steps=[]` | ✅ |
| 7 | IMPACT | start with a real caller | non-empty candidate set, `satisfied` | `status=satisfied`, one real candidate with `CALL` basis | ✅ |
| 8 | IMPACT | start with no in-repo callers (only called by other functions, itself calls nothing back to it via the graph's actual shape) | still `satisfied` (empty/negative result is valid, not a gap) | `status=satisfied` (candidate set from the actual graph, not necessarily empty — see note) | ✅ |
| 9 | TRACE | case 5's request + `explanation_query` | one `/generate` call, answer grounded in the cited hop only | `explanation.answer` correctly describes the `healthcheck.py → healthcheck.py#check` CALL hop; `model_used="ollama/Qwen3:4b"` | ✅ |
| 10 | Validation | `mode=trace`, `max_depth=999` (ceiling is 6) | 400 | `{"detail":"max_depth must be between 1 and 6"}` | ✅ |
| 11 | Validation | `mode=orient` with `start` set | 400 | `{"detail":"mode=orient does not accept start/relation_types/required_target"}` | ✅ |

Note on case 8: the chosen start (`chunkers/text.py#TextChunker._chunk_by_paragraph`)
turned out to have one real in-repo caller in this corpus rather than
zero, so it didn't exercise a literal empty-candidate-set response —
that exact shape is already covered by unit tests
(`test_impact_empty_candidate_set_is_still_satisfied`); this live pass
confirms the non-trivial case instead (a genuinely different candidate
than expected is still reported correctly, not silently dropped).

## What this does and does not establish

**Established:**
- The generation fence, bounded one-repair control loop, and structured
  assessment all behave identically to their unit-test coverage when
  driven by a real ingested corpus over real HTTP, through the real
  FastAPI app and real Postgres-backed graph — not just mocked fixtures.
- The Stage A4 explanation phase makes exactly one real LLM call,
  grounded only in the finalized evidence, and correctly skips/limits
  itself per the unit-tested rules.
- Existing `/orient`, `/trace`, `/impact` single-pass endpoints and
  `/rag` were not touched by this change (untested here beyond existing
  CI, which already covers them).

**Not established (future work, tracked under #200):**
- False-sufficient rate, useful-vs-unnecessary-repair rate, or any
  statistical claim — sample size (11 ad hoc cases, 1 small repo) is
  far below the methodology's bar.
- Behavior against this repository's full graph (~5,100 nodes) or a
  second, differently-organized repository, per the handoff's explicit
  two-repo requirement.
- Generation-fence behavior under an actual concurrent rebuild (race
  condition), only unit-tested with mocks so far.
- Production deployment: the Tailscale-reachable instance
  (`http://100.105.24.12:8004`) is still running commit `65ccd096` (its
  `/version` endpoint confirms `build_date: 2026-09-19T13:34:02Z`,
  `release_version: prod-2026-09-19-0925am`) — before any Stage A work.
  `/v1/repos/{repo_id}/evidence` is not reachable there. Deploying is a
  separate, explicit action this pass did not take.

## Follow-up: production deployment + full self-repo verification (same day)

After the local pass above, the owner deployed `main` @ `292cc89`
(through PR #230, i.e. all of Stage A0-A5 plus Stage B0) to the
Tailscale-reachable production instance and ingested this repository's
full checkout there — confirmed via `GET /version`
(`git_sha: 292cc899...`, `build_date: 2026-09-19T17:41:45Z`) and
`GET /v1/repos` (`repo_id=f7641840-ba13-5f9d-9ae6-87e1f924709d`,
`file_count: 645`, `node_count: 8881`, `status: completed`,
`ingested_at: 2026-09-19T17:45:43`). This is the real, full-scale
corpus the original local pass explicitly could not obtain in time.

Additional live cases run against `http://100.105.24.12:8004` (all
through the production HTTP surface, not a function call):

| # | Mode | Case | Result |
|---|---|---|---|
| 12 | ORIENT | `required_facets=[services, test_dirs, entry_points]` (`entry_points` is not a real ORIENT field name — it's nested inside `services`) | `services`/`test_dirs` → `satisfied`; `entry_points` → `unknown` (`unsupported_facet`), not a manufactured gap |
| 13 | TRACE | bare name `run_trace_workflow` | `needs_clarification` (genuinely ambiguous against this much larger real corpus) |
| 14 | TRACE | exact canonical_id `rag_orchestrator/src/retrieval/evidence_workflow.py#run_trace_workflow`, no target | `satisfied`, 9 real external-symbol gaps correctly enumerated (cross-module calls this extractor doesn't resolve to in-repo canonical IDs) |
| 15 | IMPACT | same start | `satisfied` with an empty candidate set (no in-repo caller resolved) — correctly not a failure |
| 16 | TRACE | case 14 + `explanation_query` | one real `/generate` call via `ollama/Qwen3:4b`; answer lists exactly the 9 cited external-gap symbols, nothing invented |

This upgrades the earlier conclusion but does not change it: mechanics
now verified against a corpus close to the methodology's intended scale
(8,881 nodes vs. the handoff's no minimum, but clearly no longer a toy
fixture), still on a single repository, still without the frozen
12-16 question set or a second differently-organized repository, and
still without measuring false-sufficient rate or repair-usefulness
statistically. **Formal release-gate sign-off remains open** for the
same reasons as above — this is more live evidence, not the gate itself.

## Recommendation

Keep default-on behavior gated (there is currently no default-on
switch to gate — the endpoint is purely additive/opt-in by construction,
callers must explicitly hit it). Before claiming the Stage A5 gate
formally passed, run the full frozen two-repo methodology from the
handoff's "Frozen paired evaluation" section — production now has one
of the two required corpora already ingested at full scale. This pass
is sufficient evidence to proceed with Stage B (#199) groundwork, since
Stage B does not depend on Stage A's evaluation gate — only Stage C
(authority-aware sufficiency) does.
