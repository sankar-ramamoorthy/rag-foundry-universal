---
title: "Issue #240 new-generation frozen HTTP comparison"
date: 2026-10-10
type: test-result
status: complete-with-failed-merge-gate
tags: [repository-overview, evaluation, generation, source-authority]
related:
  - "[Frozen overview protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Prior HTTP comparison](/DOCS/test_results/2026-10-08-issue-240-http-structured-comparison.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #240 new-generation frozen HTTP comparison

## Run identity and limits

The deployed ingestion and orchestrator `/version` endpoints both reported
runtime commit `1b8f4f510a6627689b2f48979e43feaf0595a7af`. Ingestion
reported ready generation `efd94377-679d-494d-84af-53b00c83f487`, an
incremental child of `f873147c-a1d1-4891-bb98-972672db8e9a`. Its recorded
repository source commit remained `7a805d5b3cee031c44fbe0d9b8048065ce8ef039`.
The new `/v1/repos/{repo_id}/compose-snapshot` endpoint served both Compose
projections for this ready generation directly from deployed ingestion code;
no evaluation adapter was used.

Both arms completed the same 11 frozen requests against repository
`f7641840-ba13-5f9d-9ae6-87e1f924709d` and the same new generation.
Every case had matching ready-generation reads before and after and a matching
RAG response generation. Both used `top_k=10` except Q5k20, `rerank=false`,
and the same 4096-byte retrieved-context cap. Generated responses reported
`ollama/Qwen3:4b`; Q1–Q4 in the candidate used the deterministic structured
path and therefore have no model generation result.

The [flag-off baseline JSON](/DOCS/test_results/2026-10-10-issue-240-new-generation-http.json)
came from the deployed orchestrator with its #240 flags off. Q1 and Q2 were
captured before pausing that arm to confirm its configuration; the same script
resumed with Q3–C3, without replacing either completed response. The
[candidate JSON](/DOCS/test_results/2026-10-10-issue-240-new-generation-candidate.json)
came from the clean local branch at `1b8f4f5` using the deployed ingestion,
vector, LLM, and Ollama services. Claim selection and structured answers were
enabled; canonical selection remained disabled. The local `/version` reports
`dev` and `unknown` because it is not a stamped image, so its Git commit is
recorded from the clean worktree rather than inferred from `/version`.

The persisted Compose SHA-256 digests were
`a574e85155c3aa6a6d7b90e6de3f56bf500f7ecbcf66dcebe6f0002c2daaa447`
for `docker-compose.yml` and
`5f6eb00e7dbb48bc2fefef3a7f3f0c4bb13519015a5a72b644f874719dbc1e4f`
for `docker-compose.test.yml`. Both differ from the source-byte digests
recorded in the October 8 adapter comparison, despite the same recorded
corpus source commit. The cause is not established. This run is matched
between its own two arms, but it does not prove that the latest branch commit
was the ingested repository source or that the October 8 source bytes were
reproduced.

## Frozen-case judgment

| Case | Baseline | Candidate | Source and answer judgment |
| --- | --- | --- | --- |
| Q1 | F | P | Baseline equates `pyproject.toml` with a Python package and omits the complete inventory. Candidate renders all observed file counts, 11 language counts, six services, all manifests, test/docs directories, and explicit gaps from generation-matched ORIENT. Validation errors: none. |
| Q2 | F | P | Baseline again uses manifests as package evidence and asserts absence from incomplete inventory. Candidate gives six service rows, nine Compose declarations, directory/source/test/manifest facts, language counts, and `UNKNOWN` package states without inferring absence. Validation errors: none. |
| Q3 | F | P | Baseline calls the repo ID a commit SHA, says the repository name is unavailable, and omits the observed `shared` directory. Candidate binds the Q2 structural facts to selected repository ID and generation. Validation errors: none. |
| Q4 | F | P | Baseline substitutes an old ingestion diagram for a service architecture map. Candidate distinguishes application HTTP relationships, datastore configuration, Compose startup dependencies, published ports, and heuristic links. It used the new generation's persisted Compose snapshots. Validation errors: none. |
| Q5, k=10 | F | P | Canonical purpose source absent from baseline final context; present in candidate final context and citations. Candidate answer correctly states read-only graph-aware code/document RAG purpose. |
| Q5, k=20 | F | P | Same source and answer checks pass for candidate. |
| Q6 | P | P | Canonical purpose source survives and is cited in both arms; candidate answer remains correct. |
| Q7 | F | P | Candidate cites canonical purpose and names Python, TypeScript/JavaScript, Rust, Java, and documents. |
| C1 | P | **F** | Requested note survives and the central fixture-contamination explanation is correct. The candidate answer omits the frozen requirement to label that note *historical*; the baseline answer explicitly says “historical test results material.” This is a control regression. |
| C2 | Source F | P | Exact `shared/smoke_repo/README.md#smoke_repo_live_smoke_test_fixture` reaches candidate final context and citations. Answer identifies the fixture and its smoke-test use. Baseline lacks the exact source. |
| C3 | Source F; answer partial | P | Exact `ingestion_service/src/core/codebase/graph_assembler.py#GraphAssembler.assemble` reaches candidate final context and citations. Answer includes symbol table, defines, import/inheritance/call resolution, and documentation linking. Baseline lacks the method source. |

The candidate passes Q1–Q7, C2, and C3 on the frozen checks. It fails C1's
historical-source labeling requirement. Purpose-source final-context survival
is 4/4 candidate versus 1/4 baseline. C2/C3 exact-source final-context
survival and citation are 2/2 candidate versus 0/2 baseline. C1 source
survival passes in both arms, but answer labeling regresses. The four
structured answers have empty validation-error arrays.

**Decision: no-go for the #240 PR or merge.** Correct C1's answer labeling
without suppressing its requested historical source, then rerun the affected
control and the frozen gate as required by the protocol. Separately establish
why the new ingestion generation retains the old corpus source commit while
its Compose byte digests differ from the earlier capture before claiming the
latest branch was ingested as the evaluation subject.
