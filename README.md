# rag-foundry-universal

**AI-Powered Code & Document Intelligence**
*Query code repositories and documents like a developer assistant. Extracts functions, classes, and dependencies, performs graph-aware semantic search, and answers questions using LLMs.*

---

## 🚀 Overview

`rag-foundry-universal` provides **semantic retrieval and graph-aware querying** across both **codebases** and **documents**.

It enables you to:

- Navigate code repositories and dependencies using AST-extracted graph structure
- Search documents and Markdown files semantically with section-level precision
- Ask natural-language questions about code structure (*"what calls add()"*, *"methods in Calculator"*)
- Query uploaded documents with relationship-aware retrieval planning
- Combine deterministic graph traversal with LLM-powered reasoning

---

## 🧩 Key Features

- **Dual Ingestion Paths**: Git repositories (graph-aware) and regular file uploads (PDF, text, Markdown)
- **Deterministic Artifact Graph**: AST-based extraction for precise code structure (modules, classes, functions, calls, imports)
- **Markdown Section Extraction**: Heading hierarchy extracted as graph nodes with DEFINES relationships (ADR-043)
- **Canonical Artifact Identity**: `(repo_id, canonical_id)` for reproducible, collision-free graph queries (ADR-031)
- **Graph-Aware Code Queries**: BFS multi-hop traversal for function calls, dependencies, and code relationships
- **Document Graph Retrieval**: Uploaded Markdown files get structured section nodes with relationship-aware retrieval (ADR-046)
- **Dual RAG Query Paths**: Separate endpoints for code repo queries and document queries
- **ADR-045 Compliant**: Clean service boundaries — all DB access owned exclusively by `ingestion_service`

---

## 📌 Why It Matters

Traditional RAG systems handle unstructured text but miss structure that matters. This project combines:

- **AST parsing** and canonical IDs for structural code precision
- **Markdown section extraction** for documentation structure
- **Vector embeddings** for semantic similarity
- **BFS graph traversal** for relational queries (callers, callees, definitions, imports)
- **Relationship-aware retrieval planning** fulfilling the ADR-005 docgraph vision

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│  Gradio UI  :7860                                    │
│  ├── Repo ingestion (Git URL or local path)          │
│  ├── Document ingestion (file upload)                │
│  ├── Graph-aware RAG query (repo selector)           │
│  └── Document RAG query (simple path)                │
└─────────────────┬───────────────────────────────────┘
                  │
       ┌──────────▼──────────┐
       │  rag_orchestrator   │  :8004
       │  ├── /v1/rag        │  ← graph-aware (code repo queries)
       │  └── /v1/rag/simple │  ← document graph retrieval
       └──────┬──────┬───────┘
              │      │
   ┌──────────▼─┐  ┌─▼────────────┐
   │ ingestion  │  │ vector_store │  :8002
   │ _service   │  │ _service     │
   │ :8001      │  └──────────────┘
   │            │
   │ /v1/repos  │  ← repo discovery
   │ /v1/graph  │  ← graph API (nodes, relationships, doc relationships)
   └──────┬─────┘
          │
   ┌──────▼──────┐    ┌─────────────┐
   │ ingestion   │    │ llm_service │  :8003
   │ _db (pg)    │    │ /generate   │
   └─────────────┘    └─────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology |
| --- | --- |
| API / Orchestration | Python + FastAPI |
| Database | PostgreSQL with `pgvector` |
| Code Parsing | Python AST extraction |
| Markdown Parsing | `markdown-it-py` |
| Embeddings | Pluggable (Ollama, OpenAI, etc.) |
| Vector Operations | HTTP Vector Store Service |
| Graph Traversal | In-memory BFS + relationship-aware planning |
| UI | Gradio Web App |
| Containerisation | Docker Compose |

---

## 📄 Ingestion Capabilities

| Content Type | Ingestion Path | Embedding | Graph Structure | Query Path |
| --- | --- | --- | --- | --- |
| Python code | AST + canonical graph | ✅ | ✅ CALL, DEFINES, IMPORT | Graph-aware RAG |
| Markdown (repo) | Section extraction | ✅ | ✅ DEFINES hierarchy | Graph-aware RAG |
| Markdown (upload) | Section extraction | ✅ | ✅ DEFINES hierarchy | Document RAG |
| Text files | Chunking + embedding | ✅ | — flat | Document RAG |
| PDFs | PyMuPDF → chunks | ✅ | — flat | Document RAG |

**Canonical ID examples:**

```
math_utils.py                      ← Python module
math_utils.py#Calculator           ← class
math_utils.py#Calculator.add       ← method
README.md#overview                 ← Markdown H1 section
README.md#overview.installation    ← Markdown H2 section
```

---

## 🌐 Service URLs

| Service | Host port | Internal port | Purpose |
| --- | --- | --- | --- |
| `ingestion_service` | 8001 | 8000 | Ingestion API + graph API |
| `vector_store_service` | 8002 | 8002 | Vector search with metadata filtering |
| `llm_service` | 8003 | 8000 | LLM generation |
| `rag_orchestrator` | 8004 | 8000 | RAG pipeline (code + document) |
| `gradio` | 7860 | 7860 | Web UI |

---

## 💡 Getting Started

**1. Clone the repository**

```bash
git clone https://github.com/sankar-ramamoorthy/rag-foundry-universal.git
cd rag-foundry-universal
```

**2. Start services**

```bash
docker compose up --build
```

**3. Run database migrations**

```bash
alembic upgrade head
```

**4. Ingest a Git repository**

```bash
curl -X POST http://localhost:8001/v1/ingest-repo \
     -F git_url=https://github.com/your/repo.git
```

**5. Ingest a document or Markdown file**

```bash
curl -X POST http://localhost:8001/v1/ingest/file \
     -F file=@my_doc.txt

curl -X POST http://localhost:8001/v1/ingest/file \
     -F file=@README.md
```

**6. Query a code repository (graph-aware)**

```bash
curl -X POST http://localhost:8004/v1/rag \
     -H "Content-Type: application/json" \
     -d '{"query": "what calls the add function", "repo_id": "<repo_id>", "top_k": 5}'
```

**7. Query documents (relationship-aware)**

```bash
curl -X POST http://localhost:8004/v1/rag/simple \
     -H "Content-Type: application/json" \
     -d '{"query": "what are the key features", "top_k": 5}'
```

---

## 🔍 Graph Query Examples

| Query pattern | Traversal | Direction |
| --- | --- | --- |
| *"what calls add()"* | CALL edges | Reverse |
| *"what does run_demo call"* | CALL edges | Forward |
| *"methods in Calculator"* | DEFINES edges | Forward |
| *"what imports Calculator"* | IMPORT edges | Reverse |
| *"installation steps"* | DEFINES edges | Document graph |

---

## 🤖 Architectural Decisions (ADRs)

All design decisions documented in `docs/adr/`:

| ADR | Decision |
| --- | --- |
| ADR-030 | Unified Artifact Graph — all artifacts in one graph |
| ADR-031 | Canonical Identity Model `(repo_id, canonical_id)` |
| ADR-043 | Markdown Section Extraction into Unified Artifact Graph |
| ADR-045 | DB access restricted to `ingestion_service` |
| ADR-046 | Document Graph Retrieval for uploaded files (fulfills ADR-005) |

---

## 📘 Portfolio Takeaways

- End-to-end **AI-assisted developer tooling** — ingestion to answer
- **Structured code + document reasoning** with separate optimised query paths
- **Deterministic and reproducible pipelines** via canonical identity (ADR-031)
- **Graph-aware semantic search** — BFS traversal over code and document graphs
- **Relationship-aware retrieval planning** — fulfills docgraph ADR-005 vision
- Clean **microservices architecture** with enforced service boundaries (ADR-045)
- Progressive system design documented through ADR lineage across three projects

---

## 📄 License

MIT License

---

*This project is the second in a series: `rag-foundry-docgraph` → `rag-foundry-universal` → `rag-foundry-universal`*
