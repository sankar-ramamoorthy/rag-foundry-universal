---
title: "Issue #240 per-request controls production frozen verification"
date: 2026-10-10
type: test-result
status: complete-with-inventory-gap
tags: [repository-overview, evaluation, production, generation]
related:
  - "[Frozen overview protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Per-request controls](/DOCS/notes/20261010-issue240-per-request-overview-controls.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #240 per-request controls production frozen verification

## Run identity

The deployed orchestrator and ingestion `/version` endpoints reported
`f344bd58ffde5d98f4993bc0a27192b50c8decc3`. Ingestion reported ready
generation `854e8484-7144-45c4-951b-ad8bc647c4bf`, an incremental child
of `efd94377-679d-494d-84af-53b00c83f487`, with the same recorded source
commit `f344bd58ffde5d98f4993bc0a27192b50c8decc3`. Repository ID was
`f7641840-ba13-5f9d-9ae6-87e1f924709d`. Every case had matching ready
generation and source-commit reads before and after the RAG request, and a
matching response generation. Both arms used the same deployed runtime and
generation; the only policy difference was the three explicit request
overrides.

The [candidate JSON](/DOCS/test_results/2026-10-10-issue-240-per-request-controls-production-candidate.json)
sent `claim_selection=true`, `structured_answers=true`, and
`canonical_selection=false`. The [flag-off baseline JSON](/DOCS/test_results/2026-10-10-issue-240-per-request-controls-production-baseline.json)
sent all three as `false`. The recorded effective controls matched each
request, including the baseline after the candidate run; no cross-request
setting persisted. Both arms used `claim_type=repository_overview`,
`rerank=false`, `top_k=10` except Q5k20 at 20, and a 4096-byte retrieved
context cap. Model-generated answers reported `ollama/Qwen3:4b`; candidate
Q1-Q4 used deterministic structured rendering and thus have no generation
model result. All four structured results had zero validation errors.

Gradio `/config` served Query mode defaulting to `normal`, plus Overview
claim selection, Structured repository answers, and Canonical source
selection, each defaulting to `false`. This checks deployed UI configuration;
the scored cases were direct public `/v1/rag` HTTP calls.

## Frozen case judgment

| Case | Baseline | Candidate | Evidence and answer judgment |
| --- | --- | --- | --- |
| Q1 | F | P | Candidate reports the complete ORIENT counts, languages, six Compose identities, manifests, test/docs directories, and unresolved facets. Baseline omits required inventory facets. |
| Q2 | F | P | Candidate reports observed directories and six service rows, and does not treat a missing `pyproject.toml` as proof that a service lacks a Python package. Baseline does. |
| Q3 | F | P | Candidate binds the observed structure to the selected repository and generation. Baseline's directory tree includes historical or misplaced paths. |
| Q4 | F | P | Candidate distinguishes application HTTP, datastore, and Compose dependency edges and qualifies heuristic links. Current Compose snapshots and `shared/config/service_urls.py` provide relationship evidence. Baseline substitutes a narrower ingestion diagram. |
| Q5, k=10 | F | P | Candidate retains and cites `CLAUDE.md#claude_md.what_this_project_is` and correctly states the read-only graph-aware RAG purpose; baseline lacks the target. |
| Q5, k=20 | F | P | Same canonical purpose-source and answer checks pass in the candidate, fail in baseline. |
| Q6 | P | P | Canonical purpose source survives and is cited in both arms; both answers are correct. |
| Q7 | F | P | Candidate cites canonical purpose and identifies code repositories in Python, TypeScript/JavaScript, Rust, and Java, plus documents; baseline lacks that source and describes a narrower subsystem. |
| C1 | P | P | Both cite the requested September 6 note and explain the `my_test_repo` fixture contamination. Both label the incident historical. Candidate trace records `historical_source_qualification.status=added`. |
| C2 | Source F | P | Candidate retains and cites `shared/smoke_repo/README.md#smoke_repo_live_smoke_test_fixture` and correctly identifies a smoke-test fixture. Baseline answer is broadly correct but lacks the required exact source. |
| C3 | Source F | P | Candidate retains and cites the `GraphAssembler.assemble` method chunk and accurately describes graph construction and resolution. Baseline lacks the exact method source. |

Candidate answer/source acceptance is **11/11**; baseline is **2/11** under
the frozen acceptance criteria. Candidate canonical purpose-source survival
and citation are 4/4, versus baseline 1/4. Candidate C1-C3 requested-source
survival and citation are 3/3, versus baseline C1 only (1/3). The candidate
answers for C1-C3 are correct separately from those source checks. The
candidate's Q4 architecture source `CLAUDE.md` was not retrieved, but the
protocol permits equivalent current implementation/configuration evidence;
the structured answer used generation-matched Compose snapshots and current
service URL configuration.

## Observed inventory limit

The new source snapshot contains `docker-compose.prod.yml` with a YAML
`!override` tag. ORIENT reports a `compose_parse` gap for that file because
its loader cannot construct the tag. Q1 exposes this gap rather than silently
claiming complete coverage; Q4 explicitly scopes its relationship map to
`docker-compose.yml` and `docker-compose.test.yml`. The frozen cases still
pass under their required evidence and answer checks, but this run does not
establish a complete map of the active production Compose profile. That gap
deserves a separate ingestion/ORIENT follow-up if production-profile
inventory is required.
