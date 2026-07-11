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

Requires Ollama running on the host at `http://host.docker.internal:11434` with the embedder and LLM models pre-pulled (embedder: `mxbai-embed-large:latest`, 1024-dim vectors *at the API layer* — note `DocumentNode.summary_embedding` is declared as `Vector(768)` in the ORM while the active embedder is 1024-dim; check `migrations/versions/20260301_update_vector_dimensions_1024.py` if you touch vector dimensions).

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

Everything (code entities, Markdown sections, documents) lives in **two tables** — do not add per-artifact-type tables:
- `DocumentNode` (`shared/models/document_node.py`) — one row per artifact, keyed by `document_id` (internal UUID PK) but identified globally by the unique pair **`(repo_id, canonical_id)`**.
- `DocumentRelationship` — edges between nodes (`from_document_id`, `to_document_id`, `relation_type`, `relationship_metadata`).

Key invariants (see `DOCS/adr/` for full ADRs — consult the relevant ADR before changing any of these):

- **Canonical IDs (ADR-031):** file artifacts = `<relative_path>`; symbol artifacts = `<relative_path>#<Class.method>` (dot-separated symbol path). Never fold params, line numbers, AST node IDs, hashes, timestamps, or import-resolution results into `canonical_id`. Renaming a symbol is *expected* to change its ID — there is no lineage tracking.
- **Repo scoping (ADR-030):** every artifact/query/rebuild is scoped by `repo_id`. Re-ingesting a repo deletes all its rows and fully reprocesses; the resulting IDs/relationships must be byte-identical across runs, or ingestion is broken. No LLM calls anywhere in the ingestion path.
- **Call resolution (ADR-032):** `CALL` artifacts carry a `parent_id` (enclosing function/method). Resolution order is local symbol table → file imports → global symbol index → else `EXTERNAL`. `DEFINES` edges are explicit (`MODULE→CLASS`, `MODULE→FUNCTION`, `CLASS→METHOD`). Symbol tables are in-memory only, not persisted.
- **Pipeline construction (ADR-038):** all ingestion entrypoints must build the pipeline via `ingestion_service/src/core/pipeline_factory.py::build_pipeline(...)` — never construct `IngestionPipeline`/embedder/vector_store directly inside API modules. Keep the `API → Core → Infrastructure` layering.
- **Embedding scope (ADR-039/040):** the artifact *is* the embedding unit (1:1 graph-node-to-embedding) — MODULE embeds the full file, CLASS/FUNCTION/METHOD embed the full def block; never embed CALL nodes or synthetic/empty-text artifacts. Don't introduce sub-artifact chunking for code without revisiting ADR-040. Every embeddable artifact needs a populated `"text"` field from `RepoGraphBuilder` (via `ast.get_source_segment`/lineno slicing).
- **Persistence shape (ADR-041):** full artifact text lives directly on `DocumentNode.text` — not a separate text table. Don't refactor to normalized per-snippet storage without a new ADR.
- **Codebase vs. document ingestion are not symmetric (ADR-042):** `codebase_ingest.py` creates `DocumentNode`s via `CodebaseGraphPersistence.upsert_nodes()` using the canonical ID as `document_id` — the ingestion pipeline must reuse that same `document_id` for chunk/embed/persist and must never let `pipeline._persist()` mint a second `DocumentNode` for the same artifact (this duplicated nodes 1:2 for a while; the fix is the invariant). `ingest.py` (file upload) is a different flow: one `DocumentNode` per uploaded file.
- **Hybrid retrieval flow (ADR-045):** vector search filtered to `doc_type="code"` → seed `canonical_id`s → deterministic keyword-based `select_traversal_strategies(query)` (no LLM router) → graph expansion via an **in-memory per-repo graph cache** (`get_cached_graph(repo_id)` — dropped on service restart, no Redis/persistence) → map back to `document_id`s → existing chunk/`RetrievalPlan` pipeline.
- **Docs-to-code linking (ADR-048):** `DOCUMENTS` relation type links `MARKDOWN_SECTION → CLASS|FUNCTION|METHOD|MODULE`, direction is doc→code only, matched by exact normalized (lowercased/stripped) name via the symbol table — no fuzzy/LLM matching, silent skip on no match, ambiguous names resolve to first match by design. Runs as `_link_docs_to_code()`, last step inside `RepoGraphBuilder.build()`. This only happens for repo ingestion — uploaded documents (`ingest.py`) never get `DOCUMENTS` edges; that's by design, not a gap.

## Coding workflow expectations

Per `docs-archive/Rules-to-help-me-coding.md`: this repo follows **Test-Guided Development** — for each issue, define acceptance criteria (observable behavior, not implementation) and write at least a skeletal test before or immediately alongside the first implementation spike, then expand tests as confidence grows. Acceptance criteria should be checkable via HTTP response or DB state.

## Documentation map

- `DOCS/adr/` — architecture decision records (ADR-030 onward are current; read the relevant one before changing graph/identity/embedding/persistence behavior).
- `DOCS/architecture/` — diagrams and deep-dives (e.g. codebase ingestion flow, repo query ASCII flow, extraction hierarchy model).
- `docs-archive/` — superseded design docs from earlier project phases (`rag-foundry`, `docgraph`) — historical context only, not current source of truth.
- `status/` — dated snapshots of project status; useful for recent history but not authoritative for current behavior (check code/ADRs first).
