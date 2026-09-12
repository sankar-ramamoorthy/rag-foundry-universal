---
title: "Production Release Record — prod-2026-09-12"
date: 2026-09-12
type: release-record
status: accepted
tags: [release, production, rollback, provenance]
related:
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
---

# Production Release Record — prod-2026-09-12

## Identity

- Release: `prod-2026-09-12`
- Approved runtime SHA: `202d91b34ee18e21c1dbb625d72acf9b82bce16d`
- Approved tag/ref: `prod-2026-09-12`
- Previous runtime SHA: `827c9cdc182073966f0b794968f90a7dc4388d18` — failed promotion attempt, not a successful production release
- Previous successful production runtime SHA: unknown / not recorded with project provenance
- Previous release record: none
- Deployment timestamp: `2026-09-12T18:13:49Z`
- Operator: Sankar Ramamoorthy
- Main-branch CI run: `34709033842`
- CI result: passed — lint, unit-tests, integration-tests

## Pre-deploy state

- Production checkout clean: yes
- Production checkout before promotion: detached at `827c9cdc182073966f0b794968f90a7dc4388d18`
- Previous running image IDs:

| Container | Previous image ID |
| --- | --- |
| ingestion-service | `sha256:4220df107fa8b1153eca4cc3f5be363fbf73fa6e0a9275d59802fd2c8921d752` |
| vector-store-service | `sha256:77496713ca17a00ac41705b9626c5171a738a1146c0e22075be9c1bff7f5c236` |
| llm-service | `sha256:3e2760923ac53c100d48fadb4a2b607e4bcd50b6de03e8cfe40aa9ed522c1a86` |
| rag-orchestrator | `sha256:0bbb4f7432b08bf2087ba5fb233363a7a32d2ad18294d3c86399f8f018e1857a` |
| gradio-ui | `sha256:00b18c422d94ff0bc6c7caa681c62de835b822283674204b063bd4dcf4785f8c` |

- Previous runtime revision labels: all five application images reported `827c9cdc182073966f0b794968f90a7dc4388d18`
- Previous release label: `prod-2026-09-10`
- Previous `rag-orchestrator` state: exited with code 1 due to missing `shared` runtime package in the production image
- Postgres volume preserved: yes
- Postgres host path: `/media/sankar/llm/rag/rag-foundry-universal/volumes/ingestion-db`
- Postgres container path: `/var/lib/postgresql/data`

## Release classification

- DB migration: no
- DB backup: not required
- Repo re-ingestion: no
- Graph rebuild: no
- Vector re-embedding: no
- Config change: yes
- Production image packaging change: yes
- Corpus mutation during deployment: no

## Deployment validation

- Approved Git SHA checked out exactly: pass
- Main-branch CI on approved SHA: pass
- Rendered Compose config checked: pass
- Application source bind mounts absent in prod config: pass
- Postgres persistent storage present: pass
- Build completed: pass
- OCI image revision labels checked before deploy: pass
- Running container image provenance checked after deploy: pass
- Running application containers have no host source mounts: pass
- Postgres persistent mount preserved after deploy: pass
- Health checks: pass
- Gradio HTTP check: pass
- Existing corpus preservation check: pass
- RAG smoke query: pass

## Runtime provenance

| Container | Running image ID | OCI revision label | Matches approved SHA |
| --- | --- | --- | --- |
| ingestion-service | `sha256:b2e0771a7318241dc7d74d855d28a85b3a284d95444788ca67abad0e38c43572` | `202d91b34ee18e21c1dbb625d72acf9b82bce16d` | yes |
| vector-store-service | `sha256:6bdce6bae2c0fcb069f357f7559a0c92845607410c629a39f04d1d811a418c13` | `202d91b34ee18e21c1dbb625d72acf9b82bce16d` | yes |
| llm-service | `sha256:9ff2b064b99c183c049d6c662947e27ccb94abe5724f7020397c65c00c62cec8` | `202d91b34ee18e21c1dbb625d72acf9b82bce16d` | yes |
| rag-orchestrator | `sha256:b89cbd23ab9ec7e26d23495b92c7f34c37721cdf3d4a341c297263c47f4c5f2f` | `202d91b34ee18e21c1dbb625d72acf9b82bce16d` | yes |
| gradio-ui | `sha256:8d533fe0ead65e130a5090ea8337bf2bdfc4c168928c74aaaf8294a12e030674` | `202d91b34ee18e21c1dbb625d72acf9b82bce16d` | yes |

## Health validation

The following production endpoints returned HTTP 200:

- `http://localhost:8001/health` — ingestion service
- `http://localhost:8002/health` — vector store service
- `http://localhost:8003/health` — LLM service
- `http://localhost:8004/health` — RAG orchestrator
- `http://localhost:7860` — Gradio UI

The LLM service health endpoint reported:

- provider: `ollama`
- configured Ollama model: `phi4-mini:latest`

## Corpus preservation

The existing `rag-foundry-universal` repository remained available after deployment without re-ingestion.

- Repo ID: `f7641840-ba13-5f9d-9ae6-87e1f924709d`
- Repository: `sankar-ramamoorthy/rag-foundry-universal`
- Status: `completed`
- Ingestion ID: `da95ea67-79e8-408a-b433-a31e3e06b8e6`
- Ingested at: `2026-09-09T12:48:13.710653`
- File count: `393`
- Node count: `5311`
- Source type: `git`

No repository re-ingestion, graph rebuild, or vector re-embedding was performed as part of this release.

## RAG smoke query

- Repo ID: `f7641840-ba13-5f9d-9ae6-87e1f924709d`
- Query: `What service handles RAG queries, and what downstream services does it call?`
- Expected behavior: production RAG request completes through retrieval and generation and returns an answer, sources, and retrieval-plan evidence.
- Result: pass
- Model used: `ollama/Qwen3:4b`
- Model alias: `default`
- Fallback used: none

Returned sources included:

- `DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md#rag_retrieval_quality_diagnostic_linux_tailscale_baseline.4_initial_manual_rag_tests.test_orchestrator_responsibilities`
- `rag_orchestrator/src/api/v1/routes.py#rag_endpoint`
- `docs-archive/DOCS-rag-foundry/ARCHITECTURE/adr-022-ingestion-service-responsibilities.md#adr_022_responsibilities_of_the_ingestion_service.context`
- `rag_orchestrator/src/api/v1/routes.py#simple_rag_endpoint`

Retrieval-plan summary:

- seed docs: `4`
- expanded docs considered: `6`
- expanded docs used: `6`

The smoke test establishes end-to-end production functionality. Retrieval-quality evaluation is tracked separately and was not a release gate for this deployment.

## Failed promotion history

The earlier production candidate:

`827c9cdc182073966f0b794968f90a7dc4388d18`

successfully established OCI provenance and production Compose source-mount removal, but failed production startup because the `rag-orchestrator` image did not contain the repo-level `shared` runtime package.

That attempt:

- did not modify the database schema
- did not trigger repository re-ingestion
- did not rebuild the graph
- did not re-embed vectors
- did not mutate the existing corpus

Issue `#96` captured the packaging defect. PR `#97` fixed it by making the production image self-contained and adding regression coverage.

The merged and CI-green replacement candidate was:

`202d91b34ee18e21c1dbb625d72acf9b82bce16d`

## Rollback point

- Legacy rollback image tags exist locally as `legacy-pre-827c9c`
- Legacy application source Git SHA: unknown / not recorded
- Rollback command tested: no
- DB restore required for rollback: no, assuming application/schema compatibility remains unchanged
- Notes: the legacy images predate reliable project OCI revision provenance. They are retained only as an emergency image-level rollback point and should not be interpreted as a provenance-complete release.

## Evaluation provenance

- Runtime SHA: `202d91b34ee18e21c1dbb625d72acf9b82bce16d`
- Runtime release tag: `prod-2026-09-12`
- Ingested source snapshot: unknown / not recorded for this existing ingestion
- Ingestion ID: `da95ea67-79e8-408a-b433-a31e3e06b8e6`
- Model/config for smoke query: `ollama/Qwen3:4b`, alias `default`, no fallback

The missing ingested-source snapshot is retained explicitly rather than inferred. Future evaluation records should capture both the deployed runtime SHA and the exact ingested source snapshot together with the ingestion ID.

## Release outcome

**SUCCESS**

`prod-2026-09-12` is the first production release in this process with:

- an exact CI-green main SHA
- immutable application code inside production images
- project-owned OCI revision provenance
- no application source bind mounts
- preserved persistent database storage
- verified running-image provenance
- successful service health checks
- preserved existing corpus
- successful end-to-end RAG smoke validation
