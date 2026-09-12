---
title: "Failed Promotion - 827c9cdc"
date: 2026-09-12
type: release-record
status: failed
tags: [release, production, docker-compose, provenance, failed-promotion]
related:
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
  - "[Production Release Record Template](/DOCS/releases/prod-release-template.md)"
---

# Failed Promotion - 827c9cdc

## Identity

- Release candidate: `827c9cdc182073966f0b794968f90a7dc4388d18`
- Approved runtime SHA: `827c9cdc182073966f0b794968f90a7dc4388d18`
- Result: failed promotion / validation attempt
- Previous runtime SHA: legacy production baseline, actual image source SHA unknown

## Validation Outcome

- Build provenance: pass
- Production Compose source bind mounts removed: pass
- Postgres persistent volume preserved: pass
- Gradio HTTP response: pass
- Production deployment: fail
- Failure reason: `rag_orchestrator` image did not include `shared/`, causing
  `ModuleNotFoundError: No module named 'shared'` when production stopped
  bind-mounting `./shared:/app/shared`.

## Release Classification

- DB migration: no
- DB backup: not required
- Repo re-ingestion: no
- Graph rebuild: no
- Vector re-embedding: no
- Corpus change: no

## Follow-Up

Do not record `827c9cdc182073966f0b794968f90a7dc4388d18` as a successful
production release. Issue #96 and PR #97 fixed the packaging defect, and
`prod-2026-09-12` subsequently deployed
`202d91b34ee18e21c1dbb625d72acf9b82bce16d` successfully. See
[the successful release record](/DOCS/releases/2026-09-12-prod-release.md).
