---
title: "Issue #240 HTTP structured-answer matched comparison"
date: 2026-10-08
type: test-result
status: complete-with-failed-merge-gate
tags: [repository-overview, evaluation, structured-answer, generation]
related:
  - "[Frozen overview protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Standalone structured validation](/DOCS/test_results/2026-10-04-issue-240-structured-answer-validation.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #240 HTTP structured-answer comparison

## Snapshot, arms, and source proof

Both arms completed all 11 frozen requests through `POST /v1/rag` against
selected repository `f7641840-ba13-5f9d-9ae6-87e1f924709d`, ready
generation `f873147c-a1d1-4891-bb98-972672db8e9a`, and source commit
`7a805d5b3cee031c44fbe0d9b8048065ce8ef039`. Every saved before/after
generation read matched, and every successful RAG response reported that
generation. Both arms used the same production vector, LLM, and Ollama
services read-only, `rerank=false`, `top_k=10` except Q5 at `top_k=20`, and
the same 4096-token retrieved-context cap. All generated responses reported
`ollama/Qwen3:4b`; Q2-Q4 in the candidate bypassed generation by design.

The [flag-off baseline JSON](/DOCS/test_results/2026-10-08-issue-240-structured-baseline.json)
uses this worktree with claim selection and structured answers disabled. The
[candidate JSON](/DOCS/test_results/2026-10-08-issue-240-structured-candidate.json)
enables the previously measured claim-specific selector and the new
`REPOSITORY_OVERVIEW_STRUCTURED_ANSWERS_ENABLED` path. The frozen
[capture script](/scripts/issue240_overview_eval.py) saved full response-derived
traces after each case. These are two configuration arms of one local
orchestrator implementation, not a comparison with deployed production code.
The two switches changed together; Q5-Q7 gains are attributable to the
previously measured selector, while Q2-Q4 used the new structured path.

Production ingestion has not deployed the new Compose snapshot API. For this
read-only quality run, an [evaluation adapter](/scripts/issue240_ingestion_snapshot_proxy.py)
forwarded ordinary ingestion reads to production and served only the new
Compose route using its actual FastAPI handler with an in-memory summary.
The summary came from a clean temporary Git checkout of the exact source
commit. The handler returned the two parsed, credential-stripped Compose
projections and SHA-256 digests of their original bytes:

| Source | SHA-256 of source bytes |
| --- | --- |
| `docker-compose.yml` | `7b648b9a74bcfc6e0f0aa8be52f2119614f82a89e9c76453305d39e9e635bc4c` |
| `docker-compose.test.yml` | `5cc9f4410a20631fad7043289bf09982568c39b0a507e49e7edb1bdfa04301e3` |

The checkout HEAD, clean state, and both file digests were checked again
after the run. The adapter rejects ingestion writes. A separate HTTP test
against isolated Postgres verifies the real handler's persisted-summary read,
ready-generation match, and old-generation rejection. The live quality run
does **not** prove an end-to-end ingestion of these new snapshots in a
deployed service. No production corpus or database was changed.

## Per-question judgment

`P` means the frozen answer and evidence check passed; `F` means it failed;
`partial` means the main subject is right but required facts are missing.
Controls show answer and exact-source checks separately. The candidate's
Q2-Q4 `structured_answer.validation_errors` arrays were empty, and their
schemas and facts are saved in the JSON trace. No unsupported Q2-Q4 claim
was identified in the deterministic renderings; graph-derived HTTP links
remain labeled `heuristic`, and Compose startup dependencies are explicitly
separate from request edges.

| Case | Baseline correctness / completeness | Candidate correctness / completeness | Evidence provenance, unsupported claims, regression |
| --- | --- | --- | --- |
| Q1 generic structure | **F**: useful counts, but says all six services have directories and conflates manifests with packages. | **Partial**: correct selected subject, six services, 656 files, primary language counts, tests, and docs; omits the complete language/manifest inventory. | Candidate uses current ORIENT facts without the baseline's false directory claim. Completeness is still below the frozen Q1 check. |
| Q2 actual structure | **F**: infers a Gradio package and says PostgreSQL is handled outside a Docker container. | **P**: six service-keyed rows, nine Compose declarations, directory/source/test/manifest facts, language counts, and explicit `UNKNOWN` package states. | Candidate facts validated against pinned ORIENT plus the 9,068-node graph; Dockerfile/manifest/marker paths remain in the typed result. No unsupported absence claim. |
| Q3 named repository | **F**: treats PostgreSQL as a repository directory and says every service has a Python package. | **P**: selected repository name is bound to repo ID and generation; all Q2 fields plus observed package marker paths and explicit unknowns. | Same pinned ORIENT/graph validation. No `UNKNOWN`-to-absence conversion. |
| Q4 architectural map | **F**: largely repeats a directory table, omits relationship and port types, and makes unsupported package claims. | **P**: six components, configured/heuristic HTTP links, datastore configuration, startup dependencies, and seven published ports are kept distinct. | Pinned ORIENT/graph plus both source-verified Compose projections. PostgreSQL is a datastore, never an HTTP application; main `5434:5432` and test `5433:5432` are exact. Heuristic links are qualified. |
| Q5 purpose, k=10 | **F**: canonical purpose absent from seeds and final context; answer is generic. | **P**: corrected `CLAUDE.md` purpose reaches final context and answer names the read-only graph-aware code/document system and supported languages. | Canonical purpose absent from vector seeds but supplied by selected-evidence path; no stale language claim. |
| Q5 purpose, k=20 | **F**: same canonical evidence miss. | **P**: canonical purpose in final context; accurate answer and source. | Same source and generation as Q5 k=10. |
| Q6 what project does | **P**: canonical purpose in seed and final context; main purpose correct. | **P**: canonical purpose in final context; concise correct answer. | No answer or source regression. |
| Q7 purpose/source kinds | **F**: canonical purpose absent; omits supported code languages and arbitrary documents. | **P**: canonical purpose in final context; identifies Python, TypeScript/JavaScript, Rust, Java, and documents. | Selected-evidence source survives final context. |
| C1 historical note | Answer **P**, source **P**. | Answer **P**, source **P**. | Requested historical note remains accessible and labeled as the source; no regression. |
| C2 smoke repository | Answer **P**, exact fixture README **F**. | Answer **P**, exact fixture README **F**. | A fixture README section entered vector seeds in both arms but did not survive final context. This is an unchanged context-survival miss, not a newly suppressed fixture. |
| C3 assembler method | Answer **partial**, exact method **F**. | Answer **partial**, exact method **F**. | Exact method entered graph expansion in both arms but not final context; class source survived. Both answers describe graph construction but omit some resolution/linking work. No regression. |

The canonical purpose reached final context in **4/4 candidate purpose
requests**, versus **1/4 baseline**. Q2-Q4 were **3/3 schema and semantic
validations** in the candidate. C1 retained its requested source. C2 and C3
retained their baseline source misses; neither candidate answer regressed.
Q1 remains incomplete, so the frozen answer-quality gate is not met.

## Execution note and decision

The first candidate C2 request exceeded the capture client's 270-second
deadline without returning a response. The server and pinned generation
remained healthy. The script resumed from the nine completed cases and
captured C2 and C3 with a 600-second client deadline; the successful C2
repeat took 41.45 seconds. The candidate JSON records the resume event,
while this paragraph records the timeout reason. This is a labeled retry of
one disputed/variable request, not an unreported replacement of a scored
answer. The saved final comparison contains 11 successful responses per arm
and no generation mismatch.

**No-go for a #240 PR, merge, or deployment.** The new path is integrated
behind a default-off flag and Q2-Q4 pass the measured structured check, but
Q1 remains partial, C2/C3 still miss their exact source requirement, and a
new ready generation produced by deployed ingestion code has not been
verified. The next bounded check is an actual new-generation HTTP run without
the evaluation adapter, followed by the same 11-case gate. The C2/C3
context-survival misses remain separate from the Q2-Q4 renderer change.

Local verification: orchestrator unit suite `307 passed, 25 deselected`;
ingestion unit suite `368 passed, 1 skipped, 98 deselected`; focused
snapshot HTTP integration against isolated Postgres passed; Ruff and Pyright
passed for changed Python code. These mechanics checks do not replace the
failed answer-quality and deployment gates.
