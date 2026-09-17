---
title: "WP-R6 healthchecks and runtime provenance — local verification"
date: 2026-09-16
type: test-result
status: partial
tags: [production, healthchecks, provenance, issue-169]
related:
  - "[WP-R6 specification](/specs/005-production-correctness/issues/health.md)"
  - "[Production deployment](/DOCS/deployment/production-docker-compose.md)"
  - "[Architecture audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md)"
---

# Scope and revision

Issue #169, branch fix/169-healthchecks-provenance, based on planning merge
853b0e3814a228337028929109a44ed837f5fd2d. Results below are local Windows
checks of the implementation on this branch, not Linux deployment evidence.
No database schema, embedding, retrieval or model-routing behavior changed.

## Results

Root locked Python 3.12 environment (`uv sync --frozen`):

| Check | Result |
| --- | --- |
| Root `python -m pytest tests/ -q` | 18 passed |
| ingestion `python -m pytest tests/ -m unit -q` | 252 passed, 1 skipped, 37 deselected |
| vector store `python -m pytest tests/ -m unit -q` | 22 passed, 12 deselected |
| LLM `python -m pytest tests/ -q` | 79 passed |
| RAG `python -m pytest tests/ -q` | 148 passed, 1 skipped (live A/B harness) |
| Root `ruff check .` | Passed |
| Focused pyright on shared healthcheck/provenance and new tests | 0 errors/warnings |
| Base + production `docker compose config --format json` | Rendered all five correct exec-form probes |

Run service commands from their directories with the root interpreter
`../.venv/Scripts/python.exe`. LLM tests initially picked up personal dotenv
provider aliases (two failures); rerun with PYTHON_DOTENV_DISABLED=1 and empty
LLM_DEFAULT_ALIAS, REMOTE_OLLAMA_BASE_URL, WINDOWS_OLLAMA_BASE_URL passed.
User environment files were not modified.

New regression tests execute actual Compose argument vectors against real
temporary loopback HTTP servers. Healthy responses succeed; HTTP 503, invalid
JSON, wrong status, missing routes, unreachable endpoints and an accepted TCP
connection that never responds fail. They also test provenance defaults/build
values and Dockerfile wiring. Probe timeout is finite; Docker enforces a hard
outer deadline. This is not a full image build or Docker health-state test.

## Remaining Linux release gates

Local Docker daemon is unavailable; only config rendering ran. No Linux
container has been deployed by this change. Keep #169 open until:

- Build all five images at approved SHA, verify running image IDs and OCI labels.
- Confirm all five Docker health states become healthy; deliberately unavailable
  endpoints on an isolated test stack must become unhealthy.
- Confirm startup ordering and effective config on target Linux.
- Match all four `/version` responses to approved SHA and image labels.
- Run #171 current-revision ingestion/query/delete/redeploy and model checks.

HTTP liveness is not deep dependency or corpus readiness. Tailscale HTTP access
does not expose Docker image identity/health state; an operator must capture
host-side evidence when no authorized host execution channel exists.
