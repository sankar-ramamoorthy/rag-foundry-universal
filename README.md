# rag-foundry-universal

**Read-only code intelligence for understanding unfamiliar repositories.**

Combines semantic search with a deterministic code graph to answer questions
about implementation, dependencies, and repository structure. Supports Python,
TypeScript/JavaScript, Rust, and Java, alongside Markdown and uploaded documents.

[![CI](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml/badge.svg)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sankar-ramamoorthy/rag-foundry-universal)

In a **10-question baseline**, graph expansion recovered relevant evidence for
**two questions missed by the top-five vector results**. The project also covers
operational concerns that affect answer reliability: ingestion recovery,
repository generation consistency, bounded context selection, and traceable
source evidence. See [measured results](#measured-results) for scope and limitations.

**Hardware:** plan for GPU-backed embedding and generation, locally or through
remote inference endpoints. The current system is not intended as a CPU-friendly
local setup.

## See it in action

Ask questions such as:

- What calls this function, and which source relationships support the answer?
- Which services, manifests, and entry points exist in this repository?
- Which callers or dependents might be affected by changing a symbol?
- What does the documentation say about this implementation?

The system exposes both generated answers and deterministic structural queries.
It reads indexed source; it does not modify the repositories it analyzes.

![Graph-aware query showing callers of GraphAssembler.assemble and the edges it produces](DOCS/assets/screenshots/graph-aware-rag-query-example.png)

*Recorded against this repository through the Gradio UI, using remote Ollama
with Qwen3:4b, September 14, 2026.*

## Engineering decisions

**Use structure to recover evidence semantic search misses.** Vector search
provides seeds; traversal follows extracted call, import, inheritance,
containment, and documentation relationships. Explicit repository overview,
trace, and impact endpoints use structural evidence without an LLM router.

**Measure before adding retrieval complexity.** The initial evaluation separated
retrieval failures from answer-generation failures. It did not justify enabling
a reranker by default. An optional reranker remains available for controlled
comparisons; adding a component is not treated as evidence of better answers.

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

## Measured results

### Retrieval and answer quality

The August 2026 baseline used **10 known-answer questions: five code questions
and five document questions**.

| Measurement | Result |
| --- | --- |
| Expected source in the top-five raw vector results | 7/10 |
| Expected source recovered by production retrieval with five vector seeds and graph expansion | 9/10 |
| End-to-end answer pass rate | 9/10 |

The expanded retrieval pool can contain more than five artifacts, so the first
two rows are not an equal-sized final-result comparison. This is a small,
project-specific baseline, not a general accuracy guarantee. Retrieval success
and answer correctness are evaluated separately.

[Baseline questions, methodology, and failure analysis](DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md)

A later, separate eight-question evaluation compared improved passage selection
and context delivery against the earlier implementation: **5/8 versus 3/8**.
These are different question sets and should not be read as a longitudinal
accuracy trend. The report includes the regression analysis and budget tradeoff.

[Passage-selection evaluation](DOCS/test_results/2026-09-18-wp-r4-quality-evaluation.md)

### Ingestion and search performance

A synthetic repository with **2,000 files, 56,000 artifacts, and 104,000
relationships**, measured on a laptop with PostgreSQL/pgvector in Docker:

| Stage | Measured result |
| --- | --- |
| Source extraction and graph construction | 42.7 s |
| Atomic graph persistence | 25.7 s |
| Chunking 54,000 artifacts | 1.2 s |
| Filtered vector search, k=10 | 61.7 ms p95 |

These are historical component measurements, not current end-to-end latency
claims. Embedding was the dominant cost: about 2.2 chunks/second on CPU Ollama.
That historical CPU measurement illustrates the bottleneck; it is not a practical
hardware recommendation for the current system. The benchmark does not
demonstrate million-artifact scale.

[Benchmark setup and measurements](DOCS/test_results/Phase-1-Exit-Report.md)

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
  repository inventory; bounded call tracing; candidate impact analysis.
- **Document retrieval:** Markdown, PDF, office documents, CSV, text, and OCR inputs.
- **Repository maintenance:** incremental embedding reuse, source/generation
  lineage, serialized ingestion/deletion, and interrupted-job recovery.
- **Evidence delivery:** query-relevant passages, bounded context, source manifests,
  and visibility into the model and fallback that served an answer.

Static analysis cannot resolve every runtime call or external dependency. Trace
results expose unresolved boundaries and truncation; impact results describe
candidates, not guaranteed breakage. Graph retrieval still loads a repository
into an in-memory cache. Source-authority and subject-aware sufficiency checks
are planned work, not a current guarantee.

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
```

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
