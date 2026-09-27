---
title: "Issue #240 orientation failure-localization run"
date: 2026-09-20
type: test-results
status: complete
tags: [evaluation, orientation, retrieval, graph, inventory, provenance, generation]
related:
  - "[[../evaluations/2026-09-20-issue-240-orientation-failure-localization]]"
  - "[[../notes/20260906-repository-understanding-trace-and-structural-artifacts]]"
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
| “Give me an architectural map of this repository.” | `authority_evidence` | Eight final-context chunks led the answer to assert `docs/architectural-diagram.md` and an agent-loop diagram. That evidence belongs to the separately ingested `py-coding-agent` repository, not the pinned self-repo. Diagnostics were empty; the selected repository subject was not enforced. Trace `6d3aa56e7fda43ee8d0d82539500426f`. |
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
