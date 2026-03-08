
## **1. `README.md`**

```
# rag-foundry-universal

**AI-Powered Code & Document Intelligence**  
*Semantic RAG over Python code and documents for entire repositories*

---

## 🚀 Overview

`rag-foundry-universal` provides **graph-aware retrieval-augmented generation (RAG)** across both **codebases** and **documents**, enabling precise developer-style queries across entire repositories — something standard RAG systems cannot handle.

It enables you to:

- Navigate Python code repositories using AST-extracted graph structures
- Search Markdown and documents with section-level semantic precision
- Ask natural-language questions about code relationships (*"what calls add()"*, *"methods in Calculator"*)
- Perform structured document retrieval for uploaded files (PDF, DOCX, PPTX, HTML, CSV, XLSX)
- Combine deterministic graph traversal with LLM-powered reasoning

---

## 🧩 Key Features

- **Dual Ingestion Paths**: Git repositories (graph-aware) and regular file uploads (PDF, DOCX, Markdown, etc.)
- **Universal Document Preprocessing with Docling**: Handles PDFs, Office files, and HTML → Markdown; preserves tables, reading order, and sections
- **OCR Support with Tesseract**: Extract text from scanned PDFs or images
- **1024-Dimensional Embeddings**: Using Ollama embedder (`mxbai-embed-large`) for high-quality vector search
- **Deterministic Artifact Graph**: AST-based extraction for Python code (modules, classes, functions, calls, imports)
- **Markdown Section Extraction**: Heading hierarchy extracted as graph nodes with DEFINES relationships (ADR-043)
- **Relationship-Aware Document Retrieval**: Sections and artifacts linked deterministically for precise semantic RAG (ADR-046)
- **Cross-Artifact Linking**: Repo Markdown sections linked to code symbols (ADR-048)
- **Dual RAG Query Paths**: Separate endpoints for code repo queries and uploaded document queries
- **Pluggable Embeddings & LLMs**: Tested with Ollama on host, works on CPU-only Windows laptops, can be adapted to external cloud LLMs

---

## 📌 Why It Matters

Traditional RAG systems handle unstructured text but miss structure that matters. This project combines:

- **AST parsing** and canonical IDs for structural code precision
- **Markdown section extraction** for documentation structure
- **Vector embeddings** for semantic similarity
- **BFS graph traversal** for relational queries (callers, callees, definitions, imports)
- **Relationship-aware retrieval planning** fulfilling the ADR-005 docgraph vision

This allows semantic queries that span the entire repository and linked documents — a scenario where simpler RAG systems fail.

---

## 🏗️ Architecture



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



---

## 🛠️ Tech Stack

| Layer | Technology |
| --- | --- |
| API / Orchestration | Python + FastAPI |
| Database | PostgreSQL with `pgvector` |
| Code Parsing | Python AST extraction |
| Markdown & Document Parsing | `markdown-it-py`, Docling |
| OCR | Tesseract |
| Embeddings | Ollama, Mock (pluggable) |
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
| PDFs / Scanned PDFs | Docling + Tesseract | ✅ | — flat | Document RAG |
| Office files (DOCX, PPTX, XLSX, CSV) | Docling → Markdown / flat chunking | ✅ | — flat | Document RAG |

---

## 💡 Getting Started

**1. Clone the repository**

```
git clone https://github.com/sankar-ramamoorthy/rag-foundry-universal.git
cd rag-foundry-universal
````

**2. Make sure Ollama is installed on the host**

* The containers expect Ollama served at `http://host.docker.internal:11434`.
* Ensure the embedder `mxbai-embed-large` and the LLM `granite4:350m` are already downloaded.

**3. Start services**

```
docker compose up --build
```

**4. Run database migrations**

```
alembic upgrade head
```

**5. Ingest a Git repository**

```
curl -X POST http://localhost:8001/v1/ingest-repo \
     -F git_url=https://github.com/your/repo.git
```

**6. Ingest a document or Markdown file**

```
curl -X POST http://localhost:8001/v1/ingest/file \
     -F file=@my_doc.txt
```

**7. Query a code repository (graph-aware)**

```
curl -X POST http://localhost:8004/v1/rag \
     -H "Content-Type: application/json" \
     -d '{"query": "what calls the add function", "repo_id": "<repo_id>", "top_k": 5}'
```

**8. Query documents (relationship-aware)**

```
curl -X POST http://localhost:8004/v1/rag/simple \
     -H "Content-Type: application/json" \
     -d '{"query": "what are the key features", "top_k": 5}'
```

---

## 🔍 Architectural Decisions (ADRs)

* ADR-030: Unified Artifact Graph — all artifacts in one graph
* ADR-031: Canonical Identity Model `(repo_id, canonical_id)`
* ADR-043: Markdown Section Extraction into Unified Artifact Graph
* ADR-045: DB access restricted to `ingestion_service`
* ADR-046: Document Graph Retrieval for uploaded files (fulfills ADR-005)
* ADR-047: Docling Universal Document Pre-processor
* ADR-048: Cross-Artifact Linking — Markdown documentation → code symbols

---

## ⚡ Notes

* The system does **not** include an inbuilt LLM; tested with Ollama on host CPU.
* Can be adapted to external cloud LLMs with minimal changes.
* Tested on Windows laptops without GPU.
* Acknowledgement: ChatGPT, Claude, and other chatbot LLMs were used as coding and documentation assistants.
* Future vision: evolving towards an agentic RAG orchestrator capable of forming intermediate goals, choosing actions conditionally, observing results, and adapting strategies dynamically. This includes reranking results and improving observability.

---

## 📄 License

MIT License

