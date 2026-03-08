## README.md
---

# rag-foundry-universal

**AI-Powered Code & Document Intelligence**
*Query code repositories and documents like a developer assistant.*

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
* **Deterministic Artifact Graph**: AST-based extraction for code (modules, classes, functions, calls, imports)
* **Cross-linking of Markdown to Code**: DOCUMENTS relationships connect Markdown headings to the code they describe (ADR-048)
* **Vector Embeddings**: Ollama embedder, 1024 dimensions (mxbai-embed-large:latest)
* **RAG Query Paths**: Separate endpoints for code repo queries and document queries
* **OCR Support**: Tesseract for scanned PDFs/images
* **Windows & CPU-friendly**: Tested on laptops without GPU; external LLM support possible

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
| Python code              | AST + canonical graph       | ✅          | ✅ CALL, DEFINES, IMPORT | Graph-aware RAG |
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

**Steps**

```
git clone https://github.com/sankar-ramamoorthy/rag-foundry-universal.git
cd rag-foundry-universal

docker compose up --build
alembic upgrade head

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

## 🤖 Future Vision

* Agentic RAG orchestrator with intermediate goals, conditional actions, observations, and feedback
* Reranking of vectors to improve relevance
* Enhanced observability across ingestion and query pipelines
* External cloud LLM support (currently tested with Ollama on host, CPU-only)

---

## 📘 Acknowledgements

* Used ChatGPT, Claude, and other publicly accessible LLMs to help with code, design, and documentation

---

## 📄 License

MIT License

---

