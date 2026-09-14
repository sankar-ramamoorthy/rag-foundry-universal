# rag-foundry-universal

**Graph-aware retrieval, measured: 70% → 90% Recall@5** over raw vector
search alone, by combining vector similarity with deterministic graph
traversal (BFS over CALL/DEFINES/IMPORTS/INHERITS/OVERRIDES/DOCUMENTS edges).
*Query Python, TypeScript/JavaScript, Rust, and Java codebases, plus
documents, like a developer assistant.*

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sankar-ramamoorthy/rag-foundry-universal)
[![CI](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml/badge.svg)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml)

**Status:** see [`DOCS/status.md`](/DOCS/status.md) for current language
support, shipped work, and known issues.

---

**Graph-Aware RAG Query in action** — real run against this repo
(`sankar-ramamoorthy/rag-foundry-universal`), Gradio UI, remote Ollama
(`Qwen3:4b`) over Tailscale, 2026-09-14:

![Graph-Aware RAG Query example: "What calls GraphAssembler.assemble() and what edges does it produce?"](DOCS/assets/screenshots/graph-aware-rag-query-example.png)

---

## 🚀 Overview

`rag-foundry-universal` provides **graph-aware RAG querying** across **Python, TypeScript/JavaScript, Rust, and Java codebases** and **documents**, enabling semantic search at both the code and document level. Unlike a simple RAG system, it preserves structure in code and Markdown across an entire repository, giving precise answers that respect relationships like function calls, imports, and documentation links.

It enables you to:

* Query code repositories with graph relationships extracted from source
* Query Markdown and other documents semantically with section-level context
* Combine deterministic graph traversal with LLM reasoning
* Ingest PDFs, DOCX, PPTX, XLSX, CSV, Markdown, and text using a universal preprocessor (Docling)
* OCR scanned documents with Tesseract

---

## 🧩 Key Features

* **Dual Ingestion Paths**: Git repositories (graph-aware) and uploaded files (Docling + chunking)
* **Deterministic Artifact Graph**: tree-sitter-based extraction across supported languages (modules, classes, interfaces, functions, calls, imports, inheritance) — five edge types: `CALL`, `DEFINES`, `IMPORTS`, `INHERITS`, `OVERRIDES`. A `language` filter is available on graph-aware queries. Python's move to tree-sitter was parity-gated against the legacy AST extractor across a fixture repo and six real service codebases before becoming the default; the AST extractor remains available as an automatic + manual rollback path.
* **Cross-linking of Markdown to Code**: DOCUMENTS relationships connect Markdown headings to the code they describe
* **Vector Embeddings**: Ollama embedder, 1024 dimensions (mxbai-embed-large:latest), batched end-to-end (embedder batches + bulk vector writes)
* **Indexed Vector Search**: HNSW (cosine) ANN index plus filter indexes on pgvector — p95 ≈ 62 ms measured at Phase 1 benchmark scale (56k artifacts, see below). The "latency independent of corpus size" goal (<100 ms p95 at 1M+ chunk rows) is a target tracked in `DOCS/audit/04-Scalability-Plan.md` — not yet measured at that scale.
* **Atomic Repo Rebuilds**: re-ingesting a repo replaces its whole graph in one transaction under a per-repo advisory lock — a failed or concurrent ingest can never corrupt or lose the previous graph
* **RAG Query Paths**: Separate endpoints for code repo queries and document queries, combining vector similarity seeding with deterministic BFS graph expansion (empirically shown to matter — see RAG Quality below)
* **OCR Support**: Tesseract for scanned PDFs/images
* **Multi-Provider LLM Routing (LiteLLM)**: local Ollama by default, switchable per-machine (Tailscale-reachable Ollama, Anthropic/OpenAI, or a free-tier endpoint) via a gitignored `.env` — no code changes; see `llm_service/models.yaml`, the live provider-verification notes in `DOCS/notes/20260913-free-provider-live-verification.md`, and the dynamic model catalog/admin-policy endpoints documented in [Service URLs](#-service-urls).

---

## 💡 Getting Started

**Prerequisites**

* Ensure **Ollama** is installed on the host
* The containers expect Ollama served at `http://host.docker.internal:11434`
* Pre-download the embedder (`mxbai-embed-large:latest`), the default
  generation model (`phi4-mini:latest`), and the summarization-step model
  (`granite4:350m`) — all three are used by the default local-Ollama
  configuration
* Optional: route generation through a different endpoint (a Tailscale-reachable remote Ollama box, or a cloud provider like Anthropic/OpenAI) by setting `LLM_DEFAULT_ALIAS` and the matching env vars in a gitignored `.env` — see `llm_service/models.yaml`. The committed default stays local-Ollama-only so a fresh clone works without any provider account.

**Steps**

```
git clone https://github.com/sankar-ramamoorthy/rag-foundry-universal.git
cd rag-foundry-universal

docker compose up --build
DATABASE_URL=postgresql://ingestion_user:ingestion_pass@localhost:5434/ingestion_db \
    uv run alembic upgrade head

# File ingestion
curl -X POST http://localhost:8001/v1/ingest/file -F file=@my_doc.txt

# Repo ingestion
curl -X POST http://localhost:8001/v1/ingest-repo -F git_url=https://github.com/your/repo.git

# Code repo query
curl -X POST http://localhost:8004/v1/rag -H "Content-Type: application/json" \
     -d '{"query": "what calls add()", "repo_id": "<repo_id>", "top_k": 5}'

# Document query
curl -X POST http://localhost:8004/v1/rag/simple -H "Content-Type: application/json" \
     -d '{"query": "what are the key features", "top_k": 5}'
```

---

## 🏗️ Architecture

```
┌─────────────────────────────┐
│ Gradio UI :7860             │
│ ├── Repo ingestion          │
│ ├── Document ingestion      │
│ ├── Graph-aware RAG query   │
│ └── Document RAG query      │
└─────────────┬───────────────┘
              │
      ┌───────▼─────────┐
      │ rag_orchestrator │ :8004
      │ ├── /v1/rag      │ graph-aware queries
      │ └── /v1/rag/simple │ document RAG
      └───────┬─────────┘
              │
   ┌──────────▼───────────┐
   │ ingestion_service     │ :8001
   │ ├── /v1/ingest/file  │ file ingestion
   │ ├── /v1/ingest-repo  │ repo ingestion
   │ ├── /v1/summary      │ save summaries
   │ ├── /v1/repos        │ list repos
   │ ├── /v1/graph/repos  │ get repo graph
   │ ├── /v1/graph/docs   │ document relationships
   │ └── /v1/chunks       │ chunk queries
   └──────────┬───────────┘
              │
   ┌──────────▼───────────┐
   │ vector_store_service  │ :8002
   │ ├── /v1/vectors/batch │ add vectors
   │ ├── /v1/vectors/search │ similarity search
   │ ├── /v1/vectors/search-by-doc │ search by document
   │ ├── /v1/vectors/by-ingestion/{id} │ delete vectors
   │ └── /v1/ingestions     │ create ingestion
   └──────────┬───────────┘
              │
   ┌──────────▼───────────┐
   │ llm_service           │ :8003
   │ ├── /generate         │ generate text
   │ ├── /v1/summarize/{id} │ generate summary
   │ └── /health           │ health check
   └───────────────────────┘
```

---

## 🌐 Service URLs

| Service                | Port | Endpoint Examples                                                      |
| ----------------------- | ---- | ------------------------------------------------------------------------ |
| `ingestion_service`    | 8001 | `/v1/ingest/file`, `/v1/ingest-repo`, `/v1/graph/repos/{repo_id}`      |
| `vector_store_service` | 8002 | `/v1/vectors/batch`, `/v1/vectors/search`, `/v1/vectors/search-by-doc` |
| `llm_service`          | 8003 | `/generate`, `/v1/summarize/{ingestion_id}`, `GET /v1/models`, `PUT /v1/admin/policy/{slot}` |
| `rag_orchestrator`     | 8004 | `/v1/rag`, `/v1/rag/simple`                                            |
| `gradio`               | 7860 | Web UI                                                                 |

---

## 🛠️ Tech Stack

| Layer               | Technology                        |
| ------------------- | --------------------------------- |
| API / Orchestration | Python + FastAPI                  |
| Database            | PostgreSQL + `pgvector`           |
| Code Parsing        | tree-sitter (Python, TypeScript/JavaScript, Rust, Java) |
| Markdown Parsing    | `markdown-it-py`                  |
| OCR                 | Tesseract                         |
| Embeddings          | Ollama (1024d)                    |
| Vector Operations   | HTTP vector store                 |
| Graph Traversal     | BFS + relationship-aware planning |
| UI                  | Gradio                            |
| Containers          | Docker Compose                    |

---

## 📄 Ingestion Capabilities

| Content Type             | Path                        | Embeddings | Graph                   | Query           |
| ------------------------ | --------------------------- | ---------- | ----------------------- | --------------- |
| Python code              | tree-sitter + canonical graph | ✅        | ✅ CALL, DEFINES, IMPORTS, INHERITS, OVERRIDES | Graph-aware RAG |
| TypeScript / JavaScript  | tree-sitter + canonical graph | ✅        | ✅ CALL, DEFINES, IMPORTS, INHERITS | Graph-aware RAG |
| Rust                     | tree-sitter + canonical graph | ✅        | ✅ CALL, DEFINES, IMPORTS, INHERITS | Graph-aware RAG |
| Java                     | tree-sitter + canonical graph | ✅        | ✅ CALL, DEFINES, IMPORTS, INHERITS, OVERRIDES | Graph-aware RAG |
| Markdown (repo)          | Section extraction          | ✅          | ✅ DEFINES               | Graph-aware RAG |
| Markdown (upload)        | Section extraction          | ✅          | ✅ DEFINES               | Document RAG    |
| PDFs                     | Docling → Markdown → chunks | ✅          | — flat                  | Document RAG    |
| DOCX / PPTX / XLSX / CSV | Docling → chunks            | ✅          | — flat                  | Document RAG    |
| Text files               | Chunking + embedding        | ✅          | — flat                  | Document RAG    |
| Images                   | OCR via Tesseract → chunks  | ✅          | — flat                  | Document RAG    |

---

## Production deployments

The default Compose file is optimized for development and bind-mounts source
directories into the containers. For production or long-lived deployments, use
the production Compose override documented in
[`DOCS/deployment/production-docker-compose.md`](/DOCS/deployment/production-docker-compose.md)
so containers execute immutable image contents labeled with the exact Git SHA.
Do not treat `latest` as a production release identifier; pin an exact Git SHA,
tag, or image digest.

Every release follows an audited process — CI-green main SHA, self-contained
application images, no production source bind mounts, preserved Postgres
storage, running-image OCI provenance checks, health checks, and a known RAG
smoke test — recorded per-release under `DOCS/releases/`. See the most recent
release doc there for the current pinned SHA and deployment date.

---

## 🧪 Tests & CI

CI (`.github/workflows/ci.yml`) runs on every PR and on pushes to `main`:
repo-wide ruff lint, per-service unit tests, and an integration job that
brings up a pgvector service container, applies all Alembic migrations,
and runs the atomic-graph-persistence and ANN-index suites.

Locally, an isolated test stack lives in `docker-compose.test.yml`
(its own compose project, Postgres on port 5433):

```
docker compose -f docker-compose.test.yml up -d postgres
DATABASE_URL=postgresql://ingestion_user:ingestion_pass@localhost:5433/ingestion_test \
    uv run alembic upgrade head

# unit tests (per service, e.g.)
cd ingestion_service && uv run pytest -m unit

# integration tests need DATABASE_URL pointing at the test DB
```

---

## 📊 Performance (Phase 1 baseline)

Measured on a 2,000-file / 56k-artifact synthetic repo (laptop, CPU-only
Ollama) — full details in `DOCS/test_results/Phase-1-Exit-Report.md`:

| Stage | Result |
| --- | --- |
| Graph build (source extraction → artifact graph) | 42.7 s |
| Atomic persist (56k nodes + 104k edges) | 25.7 s |
| Chunking (54k artifacts) | 1.2 s |
| Vector search p95 (HNSW, filtered, k=10) | 61.7 ms |

Embedding throughput is bound by the embedder hardware (~2.2 chunks/s on
CPU Ollama); use a GPU or hosted embedder for large corpora.

The audit findings, remediation plans, and roadmap driving this work are
in `DOCS/audit/`.

---

## 🎯 RAG Quality

Retrieval and answer quality are evaluated empirically, not assumed. The
baseline (full evidence in
`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`) ran 10
known-answer questions (5 code, 5 document) end-to-end through production
`/v1/rag` and `/v1/rag/simple`:

| Metric | Result |
| --- | --- |
| End-to-end pass rate | 9/10 (90%) |
| Recall@5 — raw vector search only | 70% |
| Recall@5 — production path (incl. graph expansion) | 90% |
| Reranker decision | **NO-GO** |

The 70%→90% gap is graph expansion recovering questions raw vector search
alone missed — direct measured evidence for the graph-aware architecture,
not just an architectural claim. The reranker decision is
**evaluation-gated**: that baseline found zero failures in the rank 8–20
band a reranker could address, so a reranker stays explicitly out of
scope unless a future evaluation finds a non-trivial fraction of
failures landing there and not already explained by a chunking or
generation defect (full reversal criterion in
`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §4).

Retrieval-quality fixes and a follow-up evaluation round are tracked in
`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md` and
`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`,
including a live-verified graph-expansion ranking fix and one still-open
limitation around same-relation-type candidate overload — see
[`DOCS/status.md`](/DOCS/status.md) for the current ticket-level detail.
See `DOCS/audit/00-Audit-Overview.md` for how these results gate further
retrieval work.

---

## 🤖 Future Vision

* Agentic RAG orchestrator with intermediate goals, conditional actions, observations, and feedback
* Retrieval quality improvements driven by evidence, not speculation — see [RAG Quality](#-rag-quality) for the current evaluation-gated reranker decision
* Language-aware UI (a Gradio `language` filter dropdown) and coverage beyond today's Python, TypeScript/JavaScript, Rust, and Java support; see [`DOCS/status.md`](/DOCS/status.md) for current language support and `DOCS/audit/03-Multi-Language-Graph-Plan.md` for the full plan
* Enhanced observability across ingestion and query pipelines
* Free-tier LLM provider reliability — see [`DOCS/status.md`](/DOCS/status.md) for current provider status

---

## 📘 Acknowledgements

* Used ChatGPT, Claude, and other publicly accessible LLMs to help with code, design, and documentation

---

## 📄 License

Apache License 2.0 — see [`LICENSE`](/LICENSE).

---
