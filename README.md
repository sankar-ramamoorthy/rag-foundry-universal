## README.md
---

# rag-foundry-universal

**AI-Powered Code & Document Intelligence**
*Query code repositories and documents like a developer assistant.*
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sankar-ramamoorthy/rag-foundry-universal)
[![CI](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml/badge.svg)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/workflows/ci.yml)

---

## 🚀 Overview

`rag-foundry-universal` provides **graph-aware RAG querying** across **Python codebases** and **documents**, enabling semantic search at both the code and document level. Unlike a simple RAG system, it preserves structure in code and Markdown across an entire repository, giving precise answers that respect relationships like function calls, imports, and documentation links.

It enables you to:

* Query code repositories with AST-extracted graph relationships
* Query Markdown and other documents semantically with section-level context
* Combine deterministic graph traversal with LLM reasoning
* Ingest PDFs, DOCX, PPTX, XLSX, CSV, Markdown, and text using a universal preprocessor (Docling)
* OCR scanned documents with Tesseract

---

## 🧩 Key Features

* **Dual Ingestion Paths**: Git repositories (graph-aware) and uploaded files (Docling + chunking)
* **Deterministic Artifact Graph**: AST-based extraction for code (modules, classes, functions, calls, imports, inheritance) — five edge types: `CALL`, `DEFINES`, `IMPORT`, `INHERITS`, `OVERRIDES`
* **Cross-linking of Markdown to Code**: DOCUMENTS relationships connect Markdown headings to the code they describe (ADR-048)
* **Vector Embeddings**: Ollama embedder, 1024 dimensions (mxbai-embed-large:latest), batched end-to-end (embedder batches + bulk vector writes)
* **Indexed Vector Search**: HNSW (cosine) ANN index plus filter indexes on pgvector — p95 ≈ 62 ms measured at Phase 1 benchmark scale (56k artifacts, see below). The "latency independent of corpus size" goal is a target for `DOCS/audit/04-Scalability-Plan.md`'s WP-S4 (<100 ms p95 at 1M+ chunk rows) — not yet measured at that scale.
* **Atomic Repo Rebuilds**: re-ingesting a repo replaces its whole graph in one transaction under a per-repo advisory lock — a failed or concurrent ingest can never corrupt or lose the previous graph
* **RAG Query Paths**: Separate endpoints for code repo queries and document queries, combining vector similarity seeding with deterministic BFS graph expansion (empirically shown to matter — see RAG Quality below)
* **OCR Support**: Tesseract for scanned PDFs/images
* **Multi-Provider LLM Routing (LiteLLM)**: local Ollama by default; a Tailscale-reachable remote Ollama box or a cloud provider (Anthropic, OpenAI) can be made the default per-machine via a gitignored `.env` — no code changes (see `llm_service/models.yaml`). Groq/NVIDIA NIM first-class support is tracked separately (issue #46). Windows & CPU-friendly: tested on laptops without a GPU.

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


---

## 🌐 Service URLs

| Service                | Port | Endpoint Examples                                                      |
| ---------------------- | ---- | ---------------------------------------------------------------------- |
| `ingestion_service`    | 8001 | `/v1/ingest/file`, `/v1/ingest-repo`, `/v1/graph/repos/{repo_id}`      |
| `vector_store_service` | 8002 | `/v1/vectors/batch`, `/v1/vectors/search`, `/v1/vectors/search-by-doc` |
| `llm_service`          | 8003 | `/generate`, `/v1/summarize/{ingestion_id}`                            |
| `rag_orchestrator`     | 8004 | `/v1/rag`, `/v1/rag/simple`                                            |
| `gradio`               | 7860 | Web UI                                                                 |

---

## 🛠️ Tech Stack

| Layer               | Technology                        |
| ------------------- | --------------------------------- |
| API / Orchestration | Python + FastAPI                  |
| Database            | PostgreSQL + `pgvector`           |
| Code Parsing        | Python AST                        |
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
| Python code              | AST + canonical graph       | ✅          | ✅ CALL, DEFINES, IMPORT, INHERITS, OVERRIDES | Graph-aware RAG |
| Markdown (repo)          | Section extraction          | ✅          | ✅ DEFINES               | Graph-aware RAG |
| Markdown (upload)        | Section extraction          | ✅          | ✅ DEFINES               | Document RAG    |
| PDFs                     | Docling → Markdown → chunks | ✅          | — flat                  | Document RAG    |
| DOCX / PPTX / XLSX / CSV | Docling → chunks            | ✅          | — flat                  | Document RAG    |
| Text files               | Chunking + embedding        | ✅          | — flat                  | Document RAG    |
| Images                   | OCR via Tesseract → chunks  | ✅          | — flat                  | Document RAG    |

```
---

## 💡 Getting Started

**Prerequisites**

* Ensure **Ollama** is installed on the host
* The containers expect Ollama served at `http://host.docker.internal:11434`
* Required embedder and at least the `granite4:350m` LLM should be pre-downloaded
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
| Graph build (AST → artifact graph) | 42.7 s |
| Atomic persist (56k nodes + 104k edges) | 25.7 s |
| Chunking (54k artifacts) | 1.2 s |
| Vector search p95 (HNSW, filtered, k=10) | 61.7 ms |

Embedding throughput is bound by the embedder hardware (~2.2 chunks/s on
CPU Ollama); use a GPU or hosted embedder for large corpora.

The audit findings, remediation plans, and roadmap driving this work are
in `DOCS/audit/`.

---

## 🎯 RAG Quality (WP-Q0 baseline — 2026-08-27)

Retrieval and answer quality were empirically evaluated before any further
retrieval work (issue #49; full evidence in
`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`): 10
known-answer questions (5 code, 5 document) run end-to-end through
production `/v1/rag` and `/v1/rag/simple`.

| Metric | Result |
| --- | --- |
| End-to-end pass rate | 9/10 (90%) |
| Recall@5 — raw vector search only | 70% |
| Recall@5 — production path (incl. graph expansion) | 90% |
| Reranker decision | **NO-GO** — no failures fell in the rank 8–20 band a reranker could address |

The 70%→90% gap is graph expansion recovering questions raw vector search
alone missed — direct measured evidence for the graph-aware architecture,
not just an architectural claim. The one failure had its correct evidence
already ranked in the top 3; a clean-context test confirmed it as a
prompting/context-assembly issue (the model conflated two similarly-worded
latency figures from different documents), not a retrieval or generation
capability problem. Two related findings were filed during the
evaluation, out of scope to fix as part of it, and have since been fixed:
[issue #64](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/64)
(the code-query seed filter's `doc_type` match never fired, silently
falling back to repo-scoped search on every code query — fixed in
[#72](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/72)
by filtering on `source_type` instead) and
[issue #65](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/65)
(near-duplicate chunk crowding from module/sole-child artifacts — fixed in
[#73](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/73)
by deduplicating near-identical seed chunks at retrieval time). See
`DOCS/audit/00-Audit-Overview.md` and `DOCS/audit/04-Scalability-Plan.md`
for how this gated further retrieval work.

---

## 🤖 Future Vision

* Agentic RAG orchestrator with intermediate goals, conditional actions, observations, and feedback
* Retrieval quality improvements driven by evidence, not speculation: a reranker is **explicitly not planned** unless a future evaluation shows failures landing in the rank 8–20 band — WP-Q0 (2026-08-27) found none. Issues #64 and #65 (the code-query filter bug and near-duplicate chunk crowding WP-Q0 surfaced) are fixed; the remaining identified lever is prompting/context assembly for chunks that share surface phrasing but describe different referents — not yet filed as its own issue, see `DOCS/audit/00-Audit-Overview.md`
* Enhanced observability across ingestion and query pipelines
* First-class Groq/NVIDIA NIM cloud endpoints (issue #46) — LiteLLM routing to a remote Ollama box and cloud-provider aliases (Anthropic, OpenAI) already ships today

---

## 📘 Acknowledgements

* Used ChatGPT, Claude, and other publicly accessible LLMs to help with code, design, and documentation

---

## 📄 License

MIT License

---
