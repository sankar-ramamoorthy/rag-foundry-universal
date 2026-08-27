# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`rag-foundry-universal` is a **read-only, graph-aware RAG system** for Python codebases and documents. It is not a coding agent — it never writes or edits the code it ingests. It ingests a Git repo (AST-based code graph) or arbitrary documents (Docling/OCR chunking), stores everything in Postgres+pgvector, and answers natural-language queries by combining vector similarity search with deterministic graph traversal (BFS over CALL/DEFINES/IMPORT/DOCUMENTS edges). See `README.md` and `README_VISION.md` for the full design rationale before making architectural changes.

## Architecture: independent services over HTTP

```
Gradio UI :7860 → rag_orchestrator :8004 → ingestion_service :8001 → Postgres+pgvector
                                          → vector_store_service :8002
                                          → llm_service :8003
```

- **`ingestion_service`** — owns *all* database access exclusively (hard invariant). Ingests repos (AST graph) and documents (Docling/OCR), builds the artifact graph, exposes `/v1/ingest/file`, `/v1/ingest-repo`, `/v1/graph/repos`, `/v1/graph/docs`, `/v1/chunks`, `/v1/repos`, `/v1/summary`.
- **`vector_store_service`** — pgvector operations only (`/v1/vectors/batch`, `/v1/vectors/search`, `/v1/vectors/search-by-doc`, `/v1/ingestions`). Does not talk to `ingestion_service`.
- **`llm_service`** — thin wrapper around Ollama/OpenAI for generation and summarization (`/generate`, `/v1/summarize/{id}`).
- **`rag_orchestrator`** — coordinates retrieval + generation for two distinct query paths: `/v1/rag` (graph-aware code queries, requires `repo_id`) and `/v1/rag/simple` (flat document RAG).
- **`shared/`** — cross-service code (SQLAlchemy models, chunkers, embedders, retrieval plan types, `config/service_urls.py`). Changes here affect every service; each service also has a `.dockerignore`-scoped Docker build context of `context: .` (repo root) so it can `COPY shared`.
- Services communicate over plain HTTP using Docker network hostnames (`http://ingestion_service:8000`, etc.), configured via env vars in `shared/config/service_urls.py` — never hardcode a service URL.

## Running the stack

```
docker compose up --build
alembic upgrade head
```

Requires Ollama running on the host at `http://host.docker.internal:11434` with the embedder and LLM models pre-pulled (embedder: `mxbai-embed-large:latest`, 1024-dim vectors; check `migrations/versions/20260301_update_vector_dimensions_1024.py` if you touch vector dimensions).

`docker-compose.test.yml` spins up an isolated Postgres (`ingestion_test` db, port 5433) plus `vector_store_service`/`ingestion_service` for integration testing; `.env.test` holds the corresponding env vars.

## Dependency management & tooling

Each service (`ingestion_service`, `llm_service`, `rag_orchestrator`, `vector_store_service`, `gradio`) has its **own** `pyproject.toml`/`uv.lock` and is managed independently with `uv`. There is also a root `pyproject.toml`/`uv.lock`. When adding a dependency, add it to the specific service's `pyproject.toml`, not just root.

```
uv sync                          # from within a service directory
uv run ruff check .              # lint (root ruff.toml: line-length 88, py312, E/F/W/C)
uv run pyright .                 # type check (pyrightconfig.json: standard mode)
uv run pre-commit run --all-files
```

Pre-commit runs ruff, pyright, trailing-whitespace, and end-of-file-fixer (`.pre-commit-config.yaml`).

## Tests

Tests live per-service under `<service>/tests/` and run with `uv run pytest` from inside that service directory (each has its own `pytest.ini`). Markers: `unit` (no DB/Docker), `docker` (needs dockerized Postgres/pgvector), `integration` (needs Postgres+pgvector, sometimes Ollama too).

```
cd ingestion_service && uv run pytest                          # all tests
cd ingestion_service && uv run pytest -m unit                  # unit only, no DB needed
cd ingestion_service && uv run pytest tests/codebase/test_x.py -k test_name  # single test
```

Integration tests assume migrations are already applied against the test DB (`docker compose -f docker-compose.test.yml up`, then `alembic upgrade head`).

## Core data model — read before touching ingestion or the graph

Everything (code entities, Markdown sections, documents) lives in **two tables** — do not add per-artifact-type tables: `DocumentNode` (`shared/models/document_node.py`, keyed by `(repo_id, canonical_id)`) and `DocumentRelationship` (typed edges).

Before changing ingestion/identity/embedding/persistence behavior, read the relevant ADR — do not assume the list below is complete or a substitute:

- **Canonical IDs** — `DOCS/adr/ADR-031-canonical-identity-model.md`
- **Repo scoping & rebuild determinism** — `DOCS/adr/ADR-030-unified-artifact-graph.md`
- **Call resolution & DEFINES edges** — `DOCS/adr/ADR-032-symbol-resolution-call-graph.md`
- **Pipeline construction (must go through `pipeline_factory.py`)** — `DOCS/adr/ADR-038-pipeline-construction-ownership.md`
- **Embedding unit = artifact, not sub-chunk** — `DOCS/adr/ADR-039-artifact-level-embedding-strategy.md`, `ADR-040-code-intelligence-embedding-strategy.md`
- **Text persisted on `DocumentNode.text` directly** — `DOCS/adr/ADR-041-code-artifact-persistence-embedding-strategy.md`
- **Codebase vs. document ingestion `document_id` ownership (not symmetric)** — `DOCS/adr/ADR-042-double-creation-of-documentnodes-in-codebase-ingestion.md`
- **Hybrid retrieval flow (vector seed → graph expansion, no LLM router)** — `DOCS/adr/ADR-045-hybrid-vector-graph-rag.md`
- **Docs→code linking (`DOCUMENTS` edges, doc→code only)** — `DOCS/adr/ADR-048-Cross-Artifact-Linking.md`

See `DOCS/index.md` for the full documentation map.

## Coding workflow expectations

Per `docs-archive/Rules-to-help-me-coding.md`: this repo follows **Test-Guided Development** — for each issue, define acceptance criteria (observable behavior, not implementation) and write at least a skeletal test before or immediately alongside the first implementation spike, then expand tests as confidence grows. Acceptance criteria should be checkable via HTTP response or DB state.

## Documentation map

Start at `DOCS/index.md` for the full map. Summary:

- `DOCS/adr/` — architecture decision records; check each ADR's status before relying on it, and read the relevant one before changing graph/identity/embedding/persistence behavior.
- `DOCS/audit/` — codebase audit findings, scalability/platform/LLM-provider plans, and the roadmap; start at `DOCS/audit/00-Audit-Overview.md`.
- `DOCS/architecture/` — diagrams and deep-dives (e.g. codebase ingestion flow, repo query ASCII flow, extraction hierarchy model).
- `DOCS/proposals/` — process/tooling proposals under discussion (not yet binding).
- `DOCS/test_results/` — benchmark/verification evidence tied to specific audit findings.
- `DOCS/notes/` — ad hoc working notes.
- `docs-archive/` — superseded design docs from earlier project phases (`rag-foundry`, `docgraph`) — historical context only, not current source of truth.
- `status/` — dated snapshots of project status; useful for recent history but not authoritative for current behavior (check code/ADRs first).
