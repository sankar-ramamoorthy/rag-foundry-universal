---
title: "Production Release Record Template"
date: 2026-09-09
type: release-template
status: accepted
tags: [release, production, rollback, provenance]
related:
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
---

# Production Release Record Template

## Identity

- Release:
- Approved runtime SHA:
- Approved tag/ref:
- Previous runtime SHA:
- Previous release record:
- Deployment timestamp:
- Operator:

## Pre-deploy state

- Production checkout clean: yes/no
- Previous running image IDs:
- Previous runtime revision labels:
- Postgres volume preserved: yes/no

## Release classification

- DB migration: yes/no
- DB backup: required/not required
- Repo re-ingestion: yes/no
- Graph rebuild: yes/no
- Vector re-embedding: yes/no
- Config change: yes/no

## Deployment validation

- Rendered Compose config checked: pass/fail
- Application source bind mounts absent in prod config: pass/fail
- Postgres persistent storage present: pass/fail
- Build completed: pass/fail
- Health checks: pass/fail
- RAG smoke query: pass/fail

## Runtime provenance

For each app container, record the running image ID and OCI revision label.

| Container | Running image ID | OCI revision label | Matches approved SHA |
| --- | --- | --- | --- |
| ingestion-service |  |  |  |
| vector-store-service |  |  |  |
| llm-service |  |  |  |
| rag-orchestrator |  |  |  |
| gradio-ui |  |  |  |

## RAG smoke query

- Repo ID:
- Query:
- Expected behavior:
- Result:
- Sources:

## Rollback point

- Rollback SHA/tag:
- Rollback command tested: yes/no
- DB restore required for rollback: yes/no
- Notes:

## Evaluation provenance

- Runtime SHA:
- Ingested source snapshot:
- Ingestion ID:
- Model/config:
