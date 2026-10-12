# rag-foundry-universal

[![CI](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml/badge.svg)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sankar-ramamoorthy/rag-foundry-universal)

**Read-only exploration of code repositories and documents, with traceable source evidence.**

Finding a relevant file is only the first step in understanding an unfamiliar
project. You also need to see how components connect and which sources support
an explanation.

RAG-FOUNDRY-UNIVERSAL combines similarity search with relationships extracted
from code to help users locate implementations, find callers and dependencies,
and investigate potential change impact. It provides natural-language answers
and structured queries, and records which source passages were supplied to the
language model. It supports Python, TypeScript/JavaScript, Rust, and Java,
alongside Markdown and uploaded documents.

Structural analysis has limits, and generated explanations can be incomplete
or incorrect. The system analyzes indexed sources without modifying them.

## What you can do

- **Explore a repository:** Find services, startup points, configuration files,
  and where functionality is implemented.
- **Trace relationships:** Find callers, dependencies, and connected symbols
  within the supported structural analysis.
- **Investigate potential change impact:** Identify callers and dependents that
  may be affected by a change.
- **Ask questions and inspect evidence:** Retrieve code and documents with source
  references, and inspect bounded structural checks for supported relationships
  and unresolved gaps. These checks do not certify complete execution-flow evidence.

**Hardware:** plan for GPU-backed embedding and generation, locally or through
remote inference endpoints. The current system is not intended as a CPU-friendly
local setup.

## See it in action

![Graph-aware query showing callers of GraphAssembler.assemble and the edges it produces](DOCS/assets/screenshots/graph-aware-rag-query-example.png)

*Recorded against this repository through the Gradio UI, using remote Ollama
with Qwen3:4b, September 14, 2026.*

## Engineering decisions

**Use structure to recover evidence semantic search misses.** Vector search
provides seeds; traversal follows extracted call, import, inheritance,
containment, and documentation relationships. Explicit repository overview,
trace, and impact endpoints use structural evidence without an LLM router.

**Make reranking optional.** A cross-encoder reranker is available through
configuration and per-request overrides, and is disabled by default. Its
availability does not establish better retrieval or answer quality.

**Track what actually reaches the model.** Context selection returns the exact
selected passages. A final-context manifest records source identities and text
hashes, distinguishing evidence found during retrieval from evidence retained
in the prompt. Context budgets and whole-passage selection make losses visible.

**Make repository lifecycle behavior explicit.** Graph persistence is atomic,
and repository mutations are serialized. Generation-scoped retrieval checks
for rebuilds so a query does not silently combine different indexed generations.
A repository can be unavailable during rebuilding; preserving a continuously
servable previous snapshot is not a current guarantee.

**Avoid redundant embedding work.** Incremental ingestion reuses embeddings for
unchanged files and records generation lineage. Files are still parsed to rebuild
structure; this is not a claim that every ingestion stage scales only with the diff.

## Architecture

Services communicate over HTTP. The diagram shows the main ingestion and query
paths; the orchestrator has no direct database access.

```mermaid
flowchart LR
    UI[Gradio UI] -->|ingest| I[Ingestion service]
    UI -->|query| R[RAG orchestrator]
    R -->|graph, inventory, generation| I
    R -->|passage retrieval| V[Vector store service]
    R -->|answer generation| L[LLM service]
    I -->|store embeddings| V
    I -->|graph and document metadata| DB[(PostgreSQL + pgvector)]
    V -->|vector storage and search| DB
    L --> P[Local or remote model provider]
```

Code extraction uses tree-sitter and a shared graph representation across
languages. Markdown preserves section structure and links to code where resolved.
Uploaded documents use Docling and OCR where needed. Embedding uses Ollama;
generation supports local and remote providers through LiteLLM.

| Service | Responsibility | Local port |
| --- | --- | --- |
| Ingestion | Parsing, artifact graph, ingestion lifecycle, structural inventory | 8001 |
| Vector store | Embedding storage and passage search | 8002 |
| LLM | Generation and provider routing | 8003 |
| Orchestrator | Retrieval, traversal, evidence selection, answer coordination | 8004 |
| Gradio | Ingestion and query interface | 7860 |

**Stack:** Python, FastAPI, PostgreSQL, pgvector, tree-sitter, Docling, Ollama,
LiteLLM, Gradio, Docker Compose, pytest, and GitHub Actions.

## Current capabilities and limits

- **Code intelligence:** Python, TypeScript/JavaScript, Rust, and Java extraction;
  repository inventory; bounded call tracing; candidate impact analysis;
  generation-checked evidence assessment with explicit sufficiency and gaps.
- **Document retrieval:** Markdown, PDF, office documents, CSV, text, and OCR inputs.
- **Repository maintenance:** incremental embedding reuse, source/generation
  lineage, serialized ingestion/deletion, and interrupted-job recovery.
- **Evidence delivery:** query-relevant passages, bounded context, source manifests,
  and visibility into the model and fallback that served an answer.

Static analysis cannot resolve every runtime call or external dependency. Trace
results expose unresolved boundaries and truncation; impact results describe
candidates, not guaranteed breakage. Graph retrieval still loads a repository
into an in-memory cache. Evidence assessment checks bounded structural
obligations; it does not establish source authority or complete behavioral
coverage. Generated explanations can omit transitions or misattribute actions
even when relevant code is retained. Source manifests identify delivered evidence;
they do not certify the correctness of an answer or its citations.

Document retrieval searches the non-code corpus; the simple-query API does not
provide repository isolation. Supported input formats do not establish reliable
OCR, table interpretation, or multi-passage synthesis for every document.

Evaluation results are specific to their recorded corpora, settings and source
generations. Historical measurements, validation scope, milestones and known
issues are maintained in [project status](DOCS/status.md), with links to the
underlying reports; they are not general accuracy or performance guarantees.

[Current status and known limitations](DOCS/status.md) ·
[Roadmap](DOCS/audit/07-Roadmap.md) · [Documentation index](DOCS/index.md)

## Quick start

Requires Docker Compose, Python 3.12 with `uv`, and GPU-backed inference capacity
for embedding and generation. Use a local GPU or configure remote inference
endpoints; a CPU-only laptop is not the intended setup. Memory requirements
depend on model choice and repository size; no universal minimum is claimed here.

The example below uses local Ollama accessible from the containers at
`http://host.docker.internal:11434`. Commands use Bash. Review
[the environment template](.env.example) for local or remote host configuration.

```bash
git clone https://github.com/sankar-ramamoorthy/rag-foundry-universal.git
cd rag-foundry-universal
cp .env.example .env

ollama pull mxbai-embed-large:latest
ollama pull phi4-mini:latest

# Start the database and apply migrations before starting the application.
docker compose up -d postgres
DATABASE_URL=postgresql://ingestion_user:ingestion_pass@localhost:5434/ingestion_db \
    uv run alembic upgrade head

docker compose up --build -d
```

Wait for PostgreSQL to become healthy before running migrations. Once application
services are healthy, open **http://localhost:7860** to ingest and query through
the UI. Local generation needs no cloud account. Optional providers and
per-step model choices are configured in [the model registry](llm_service/models.yaml).

For an API walkthrough, submit a repository and retain the returned `ingestion_id`:

```bash
curl -X POST http://localhost:8001/v1/ingest-repo \
    -F git_url=https://github.com/your/repo.git

# Poll until completed; inspect failure details if ingestion fails.
curl 'http://localhost:8001/v1/ingest-repo/<ingestion_id>'

# Find the ingested repository's repo_id.
curl http://localhost:8001/v1/repos

curl -X POST http://localhost:8004/v1/rag \
    -H "Content-Type: application/json" \
    -d '{"query":"What calls this function?","repo_id":"<repo_id>","top_k":5}'
```

Replace the placeholders with your repository, returned identifiers, and a
question about its source. Structural queries are also available without generation:

```bash
curl 'http://localhost:8004/v1/repos/<repo_id>/orient'
curl --get 'http://localhost:8004/v1/repos/<repo_id>/trace' \
    --data-urlencode 'start=<canonical_id_or_symbol>'
curl --get 'http://localhost:8004/v1/repos/<repo_id>/impact' \
    --data-urlencode 'start=<canonical_id_or_symbol>'

# Assess bounded structural evidence and report unmet obligations.
curl -X POST 'http://localhost:8004/v1/repos/<repo_id>/evidence' \
    -H "Content-Type: application/json" \
    -d '{"mode":"trace","start":"<canonical_id_or_symbol>"}'
```

The evidence endpoint supports `orient`, `trace`, and `impact` modes. It returns
structured evidence and an obligation assessment; optional explanation generation
does not turn a partial assessment into complete evidence.

## Testing and deployment

[CI](.github/workflows/ci.yml) runs lint, service tests, and PostgreSQL-backed
integration checks for graph persistence, ingestion ownership, repository
lifecycle, passage retrieval, and vector indexing. A separate job checks bounded
ingestion memory. Retrieval changes also require measured quality evaluation;
unit-test success alone does not establish answer quality.

Run a service's tests from its directory, for example:

```bash
cd ingestion_service
uv run pytest -m unit
```

Database tests use the isolated [test Compose stack](docker-compose.test.yml).
See [development guidance](CLAUDE.md) for migration, lint, and test commands.

Development Compose bind-mounts source. Long-lived deployments use immutable
application images and recorded source revisions, with health checks and a RAG
smoke test. See the [deployment guide](DOCS/deployment/production-docker-compose.md)
and [release records](DOCS/releases/) for the process and deployed versions.
Shipped code and a verified deployment are tracked separately.

## Project ownership and AI assistance

This is a human-directed, AI-assisted engineering project. Human maintainers
retain project ownership and release responsibility. ChatGPT, Claude, and OpenAI
Codex have contributed to design exploration, architecture reviews, implementation,
tests, and documentation. The repository records decisions and evaluation evidence
so that changes can be reviewed against observable behavior.

## License

[Apache License 2.0](LICENSE).
