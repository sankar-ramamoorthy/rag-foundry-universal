---
title: "Issue #240 orientation failure-localization run"
date: 2026-09-20
type: test-results
status: complete
tags: [evaluation, orientation, retrieval, graph, inventory, provenance, generation]
related:
  - "[Failure-localization protocol](/DOCS/evaluations/2026-09-20-issue-240-orientation-failure-localization.md)"
  - "[Repository-understanding note](/DOCS/notes/20260906-repository-understanding-trace-and-structural-artifacts.md)"
---

# Issue #240 orientation failure-localization run

## Scope and snapshot pin

No service, retrieval, generation, or corpus behavior was changed. The run
first applied the protocol to recorded historical cases, then queried the
Linux/Tailscale deployment at `http://100.105.24.12`.

Live runtime pin:

| Field | Value |
| --- | --- |
| `ingestion_service` revision | `d7fbf8748458d979a87cfbf233d357958198f233` |
| `rag_orchestrator` revision | `d7fbf8748458d979a87cfbf233d357958198f233` |
| release | `prod-2026-09-19-2013pm` |
| repository | `f7641840-ba13-5f9d-9ae6-87e1f924709d` (`rag-foundry-universal`) |
| ingestion generation | `907ebcbc-0a15-41a8-9315-8cc2b8896208` |
| source snapshot | `d7fbf8748458d979a87cfbf233d357958198f233` |
| generation | `ready`, incremental; parent `73cf6fb7-4fc9-49f1-8631-509a2feadd0e` |
| corpus size | 655 files, 9,053 nodes; ORIENT inventory 654 files (587 indexed, 67 non-indexed) |
| ORIENT computed at | `2026-09-20T02:08:44.344357Z` |
| live model | `ollama/Qwen3:4b` |

The live queries used `POST /v1/rag` with `repo_id` pinned above,
`top_k=10`, and `claim_type=repository_overview`. The inventory control used
`POST /v1/repos/{repo_id}/evidence` with all six available facets:
`languages`, `file_counts`, `manifests`, `services`, `test_dirs`, and
`docs_dirs`. It returned `satisfied` for every facet.

## Historical cases

| Case | Classification | Supporting stage evidence |
| --- | --- | --- |
| Generic “repo structure” | `missing_structural_inventory` | The historical note records retrieval of graph-schema material (`MODULE/CLASS/METHOD`, `DEFINES/CALL`) instead of a filesystem/service/package inventory. No canonical target trace was recorded. The missing authoritative structural view is the first demonstrated boundary. |
| Explicit actual-directory query | `authority_evidence` | The historical answer described `my_test_repo`, a fixture embedded in evaluation material, while the selected repository was different. This is subject/authority substitution, not a generation-only miss. |
| Explicit `rag-foundry-universal` query | `missing_structural_inventory` | The note records that the answer fabricated a conventional Python microservice layout from ADR concepts and general practice; it explicitly identifies insufficient authoritative structural evidence. |
| `py-coding-agent`: “architectural map” | `seed_retrieval` | The recorded evidence trace for `docs/architectural-diagram.md` is `found_by_vector=false`, `found_by_graph=false`, `drop_reason=not_found_by_vector_or_graph`, with no final-context survival. This is the one historical case with direct stage evidence for a seed miss. |

These are classifications of the recorded failures, not reconstructed claims
about stages that the historical material did not measure.

## Live cases

The live ORIENT inventory was complete and satisfied all six requested facets
before the RAG queries. Every RAG response also returned a non-empty final
context manifest. The public RAG request model does not expose the internal
`trace_canonical_ids` diagnostic hook, so seed-vs-graph resolution is
**not observable for these live cases**. No live case is assigned to either
bucket without that stage evidence.

| Query | Classification | Supporting stage evidence |
| --- | --- | --- |
| “I need information about the repo structure.” | `missing_structural_inventory` | ORIENT itself was `satisfied`, but the RAG final context contained eight chunks from the historical orientation note and related design material, not the pinned inventory facts. The answer correctly reported that the requested filesystem/service/package details were absent. Provenance diagnostics returned no concerns. Trace `ab5f436d7ea64354a1e697744763cc2a`. |
| “Describe the actual directory, service, and package structure of this repository.” | `authority_evidence` | Ten final-context chunks were historical note material describing the fixture-subject failure and the absence of actual structure. The answer did not claim a structure, but the selected evidence remained the wrong subject/evidence class for the request. Diagnostics were empty. Trace `351beb5370224eabb4adcf356fea3b16`. |
| “Describe the actual directory, service, and package structure of rag-foundry-universal.” | `authority_evidence` | Nine final-context chunks included `docs-archive/DOCS-docgraph/PROJECT_PLAN.md`; the answer promoted that historical/intended layout as the current structure and added unsupported “standard practice” claims. Diagnostics were empty, exposing a policy gap rather than a clean authority pass. Trace `7eefa62bdb9844c2ba228dcb785063d9`. |
| “Give me an architectural map of this repository.” | `authority_evidence` | Eight final-context chunks led the answer to assert `docs/architectural-diagram.md` and an agent-loop diagram. A note *in the selected repository* discusses that file in the separately ingested `py-coding-agent` repository; the answer promoted that discussion into a claim about the selected repository. Diagnostics were empty. Trace `6d3aa56e7fda43ee8d0d82539500426f`. |
| “What is this repository about?” | `missing_structural_inventory` | Nine final-context chunks did not contain a repository-purpose description, and the answer explicitly said the context was insufficient. ORIENT has no purpose facet, so this is an evidence-coverage gap, not a generation failure. Diagnostics were empty. Trace `79ad8b638ced4018b69aea69453f99c6`. |

## Distribution

Counting the four historical cases and five live cases:

| Classification | Historical | Live | Total |
| --- | ---: | ---: | ---: |
| seed retrieval | 1 | 0 measured | 1 |
| graph resolution | 0 | 0 measured | 0 |
| missing structural inventory | 2 | 2 | 4 |
| authority/evidence | 1 | 3 | 4 |
| generation | 0 | 0 | 0 |
| unobservable seed-vs-graph live cases | — | 5 | — |

The live run therefore does not support a claim about graph-resolution or
seed-retrieval frequency. It does support a repeated pattern of absent or
non-authoritative structural evidence reaching the generation boundary, plus
subject/authority substitution that the current shadow diagnostics did not
flag for historical documentation.

**Later correction (2026-10-03):** The distribution above preserves the
original classification as recorded, but its `missing_structural_inventory`
label should not be read literally for Q1 or Q5: ORIENT's structural facets
were available. Q1 was a delivery/answer failure despite available inventory;
Q5's indexed purpose artifact was absent from seeds, expansion, and final
context in the later traced k=20 run. The original live run had no canonical
target trace, so it cannot itself prove that Q5 seed boundary. The historical
counts are not current failure frequencies.

## Next issue recommendation

The next issue should target **authority/evidence handling for repository
overview retrieval**, specifically enforcing the selected `repo_id` as the
subject and distinguishing current structural facts from historical plans,
fixtures, and other-repository references. This category ties the largest
live concentration (3/5) to the most consequential error: confident claims
about the wrong repository or wrong snapshot.

The issue should include a separate diagnostic prerequisite: expose or capture
canonical-target evidence traces for the controlled live set, so seed retrieval
and graph resolution can be measured rather than inferred. A structural
inventory join/projection should be evaluated alongside authority handling;
the distribution does not justify a broad reranker or a generation-only fix.

## Production follow-up (2026-10-03)

This follow-up checked whether the #240 fix is live and whether its five
overview questions could be rerun against the same pinned repository
generation. No application or corpus changes were made.

| Field | Observed value |
| --- | --- |
| production URL | `http://100.105.24.12:7860/` (service APIs reachable on `:8004` and `:8001`) |
| `rag_orchestrator` revision | `d7fbf8748458d979a87cfbf233d357958198f233` |
| `ingestion_service` revision | `d7fbf8748458d979a87cfbf233d357958198f233` |
| release | `prod-2026-09-19-2013pm` |
| #240 fix | **Not deployed**; repository checkout is `e00ddb2879d9e55361e2ffc3a70f84aeb441c442` (`e00ddb2`) |
| repository | `f7641840-ba13-5f9d-9ae6-87e1f924709d` (`rag-foundry-universal`) |
| ready generation | `907ebcbc-0a15-41a8-9315-8cc2b8896208` |
| generation source | `d7fbf8748458d979a87cfbf233d357958198f233` |
| ORIENT | returned for the selected repo and generation; computed at `2026-09-20T02:08:44.344357Z` |

The generation endpoint was read before and after the attempted RAG run; both
reads reported the same ready generation and source revision. The RAG API
contract on this deployment has no generation-id request field, so the run
was fenced by the selected `repo_id` and pre/post generation checks. The
persisted ORIENT response contains languages, file counts, manifests,
services, test directories, documentation directories, and explicit parser /
entry-point gaps.

The five queries from the original live set were submitted with
`repo_id=f7641840-ba13-5f9d-9ae6-87e1f924709d`, `top_k=10`, and
`claim_type=repository_overview`:

1. “I need information about the repo structure.”
2. “Describe the actual directory, service, and package structure of this repository.”
3. “Describe the actual directory, service, and package structure of rag-foundry-universal.”
4. “Give me an architectural map of this repository.”
5. “What is this repository about?”

All five responses completed on the pre-#240 production runtime. Every
response returned the selected `repo_id` and generation
`907ebcbc-0a15-41a8-9315-8cc2b8896208`, confirming repository/generation
binding at the response level. None of the answers used current ORIENT facts,
despite the persisted inventory being available. The response includes
`retrieval_plan.final_context_manifest` and
`retrieval_plan.provenance_diagnostics`. The initial top-level inspection
missed those nested fields; this is a correction to the inspection record.

| Query | Answer behavior | Current ORIENT facts used? | Selected repo respected? | Missing evidence acknowledged? | Trace |
| --- | --- | --- | --- | --- | --- |
| “I need information about the repo structure.” | Said context lacked actual filesystem structure; sources were historical orientation notes and design material. | No | Yes; returned selected repo/generation. | Yes, but did not surface the available inventory. | `c0f1dbfa04a84724898304a4930acebf` |
| “Describe the actual directory, service, and package structure of this repository.” | Said context lacked actual directories/services/packages; sources were historical notes and the audit. | No | Yes | Yes, but inventory facts were available. | `708016ff8f28444e94e710c4420801c9` |
| “Describe the actual directory, service, and package structure of rag-foundry-universal.” | Declined to describe structure; cited a historical fixture failure and archived `rag-foundry-docgraph` plan. | No | Yes at response/repository scope; answer exposed the wrong-project plan as context, but did not assert it as current structure. | Yes, though not grounded in ORIENT's known facts. | `87e23643e0344502887659dfecbb7edc` |
| “Give me an architectural map of this repository.” | Produced a map from this repo's older persistence design, then asserted `docs/architectural-diagram.md` for the agent-loop diagram discussed in this repo's note about `py-coding-agent`. | No | **No, in answer content**; response metadata and retrieved evidence remained scoped, but the answer imported another repository's file claim. | No; confidently presented the cross-subject claim. | `b80bdff1f0344899b65756f4d025812c` |
| “What is this repository about?” | Said context did not specify the repo's purpose. | No; ORIENT has no purpose facet. | Yes | Yes for the selected context; the indexed purpose source was available upstream and later traced as a retrieval miss. | `71ccf44f63ef4c35b527e31d9f825e0a` |

The live failures are the repeated failure to use available current structural
inventory for questions 1–3, plus the cross-repository architectural claim in
question 4. Question 5 accurately reports what was missing from its selected
context, but indexed canonical purpose evidence was missed by retrieval;
ORIENT's lack of a purpose facet is not the whole failure. These observations
are from the old
runtime and do not demonstrate the behavior of `e00ddb2`; the prior
2026-09-20 outcomes likewise must not be treated as verification of that
commit.

### Remaining issue and next step

Production is still running the pre-#240 revision, so the issue remains
unverified in production. Deploy a release containing `e00ddb2`, confirm both
service `/version` endpoints report that revision, then rerun the same five
queries against a recorded ready generation. Capture final-context entries
and provenance diagnostics as well as answer/source IDs; check whether each
answer cites current ORIENT facts, stays within the selected repository, and
states when purpose or another requested fact is missing. Do not infer
retrieval or generation failure labels if the runtime does not expose the
needed stage evidence.

## Production follow-up after re-ingest (2026-10-04)

After the owner reported deployment and started ingestion, production was
checked after a 10-minute wait. The repository ingest had completed, but the
runtime code revision still did not contain #240:

| Field | Observed value |
| --- | --- |
| `rag_orchestrator` revision | `d7fbf8748458d979a87cfbf233d357958198f233` |
| `ingestion_service` revision | `d7fbf8748458d979a87cfbf233d357958198f233` |
| release label | `prod-2026-10-03-2014pm` |
| repository | `f7641840-ba13-5f9d-9ae6-87e1f924709d` (`rag-foundry-universal`) |
| ready generation | `d3ecfaea-23a1-4067-8f1a-0010c3158004` |
| generation source | `00e0cc9bf268a90ac85ed3b78ff7a8ba0afaf4bb` |
| generation status | `ready`, incremental; parent `907ebcbc-0a15-41a8-9315-8cc2b8896208` |
| corpus size | 657 files, 9,068 nodes |

All five questions were rerun with `repo_id=f7641840-ba13-5f9d-9ae6-87e1f924709d`,
`top_k=10`, and `claim_type=repository_overview`. Every response included the
selected repository ID and generation `d3ecfaea-23a1-4067-8f1a-0010c3158004`.
The response includes `retrieval_plan.final_context_manifest` and
`retrieval_plan.provenance_diagnostics`. The initial top-level inspection
missed those nested fields; final-context selection is observable.

| Query | Answer behavior | Current ORIENT facts used? | Selected repo respected? | Missing evidence acknowledged? | Trace |
| --- | --- | --- | --- | --- | --- |
| “I need information about the repo structure.” | Said context lacked filesystem/service/package organization and described graph structure retrieval instead. | No | Yes in response metadata | Yes, despite ORIENT inventory being available. | `deccc0a32f3d4ed5945dc40df0506388` |
| “Describe the actual directory, service, and package structure of this repository.” | Repeated the historical `my_test_repo` subject-contamination story; supplied no current structure. | No | Yes in response metadata; answer described a historical fixture case. | Yes, despite available ORIENT facts. | `d2d0df8606fe403093744c6fb3592992` |
| “Describe the actual directory, service, and package structure of rag-foundry-universal.” | Said the actual structure was missing and identified `rag-foundry-docgraph` as a distinct project. | No | Yes; did not present the other project's structure as this repo's. | Yes, despite available ORIENT facts. | `187afec41d794886ac6efa4f948d69c9` |
| “Give me an architectural map of this repository.” | Presented an older persistence-ingestion design as the map and asserted `docs/architectural-diagram.md` as a fully ingested agent-loop diagram; the selected repo's note discusses that file in `py-coding-agent`. | No | **No in answer content**; response metadata and retrieved evidence remained pinned, but the answer made a cross-subject claim. | No; it made a confident wrong-project claim. | `5423ba1086df40edaf664c12b235d919` |
| “What is this repository about?” | Said the context did not specify the repository's purpose. | No; ORIENT has no purpose facet. | Yes in response metadata | Yes for selected context; indexed purpose evidence was missed upstream. | `254673b3ae51423db403660669bb68f5` |

The rerun reproduces the earlier pattern: the old runtime does not use
available ORIENT inventory for structural questions, and the architectural
map answer still imports a cross-repository claim. The purpose answer
accurately reports its context gap, while retrieval failed to supply the
indexed purpose section. These are results for generation
`d3ecfaea…` served by runtime `d7fbf874…`; they are **not a verification of
`e00ddb2`**, regardless of the newer release label or corpus source SHA.

### Remaining issue and next step

The ingest is complete, but the two production service `/version` endpoints
still report the pre-#240 runtime SHA. Redeploy/restart the service images
that contain `e00ddb2` and confirm both `/version` endpoints report that
commit. Then rerun the same five questions against a ready generation and
capture the nested final-context manifest and diagnostics.

### Corrected diagnostic inspection (2026-10-03)

The five overview questions were queried again against the same ready
generation `d3ecfaea-23a1-4067-8f1a-0010c3158004`, with `top_k=10` and
`claim_type=repository_overview`. This was a read-only exploratory rerun, not
verification of `e00ddb2`. Each response had 8–10 entries under
`retrieval_plan.final_context_manifest` and the same number under
`retrieval_plan.provenance_diagnostics`; none reported concerns. Empty
concerns do not establish authority correctness: the deployed overview rule
does not detect every historical or cross-subject claim in a document from
the selected repository.

| Question | Trace | Corrected stage finding |
| --- | --- | --- |
| 1. Generic structure | `25bd81cee2224896b54c2ea330f66935` | Eight final-context entries; no current ORIENT facts in the answer. |
| 2. Actual structure | `36e31c5cde2640238d0f8ac5d733605e` | Ten final-context entries; historical discussion displaced current structure. |
| 3. Named repository structure | `bc2c76c7bbd149c5bf0068f23cebe8c1` | Nine final-context entries, including an archived plan; diagnostics reported no concerns. |
| 4. Architectural map | `ac93c24425f646e687aed227671594b8` | Eight final-context entries from the selected repository, including a note discussing `py-coding-agent`; the answer promoted that embedded discussion into a wrong-project file claim. This is answer-subject contamination, not evidence that retrieval crossed `repo_id`. |
| 5. Purpose | `b5b54b54821641af8e5bdc962a77172a` | Nine final-context entries; none supplied the canonical `CLAUDE.md` purpose section. The lack-of-evidence statement describes selected context, not index availability. |

The exact issue repro was also rerun at `top_k=20` (trace
`4e28b92a43214878989015c48489cf0d`). It had 16 seeds, 52 expanded
candidates, and nine final-context entries. The indexed
`CLAUDE.md#claude_md.what_this_project_is` target was absent at all three
stages. The answer remained generic. This directly supports a candidate-entry
failure; it does not establish which repair is appropriate.
