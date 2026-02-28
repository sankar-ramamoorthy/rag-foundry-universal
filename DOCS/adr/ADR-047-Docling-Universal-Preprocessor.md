# ADR-047: Docling as Universal Document Pre-processor

**Status:** Accepted
**Date:** 2026-02-27
**Relates to:** ADR-030 (Unified Artifact Graph), ADR-043 (Markdown Section Extraction), ADR-046 (Document Graph Retrieval)
**Implemented by:** MS6-IS4

---

## Context

The current file ingestion pipeline handles three document types with three separate
code paths:

| Type | Current path | Quality |
|---|---|---|
| PDF | PyMuPDF (`pdf.py`) → `PDFChunkAssembler` | Text blocks only, no table structure, no reading order |
| Text / Markdown | `extract_text_from_bytes()` → flat chunking or `MarkdownSectionExtractor` | Good for plain text and .md |
| Other (DOCX, PPTX, XLSX) | Not supported — ingestion fails silently | None |

Word documents, PowerPoint presentations, Excel spreadsheets, HTML, and other
common formats cannot be ingested. This limits the system's utility as a general
document intelligence platform.

PyMuPDF (`fitz`) was adopted in an earlier project iteration. At that time Docling
was evaluated but not chosen due to concerns about complexity and resource usage.
Those concerns are revisited here with updated information.

---

## Decision

Adopt **Docling** as the universal document pre-processor for all non-Markdown,
non-image file types ingested via `POST /v1/ingest/file`.

### Docling replaces PyMuPDF as the primary PDF path

Docling's PDF understanding is structurally superior to PyMuPDF for RAG purposes:
- Detects reading order (PyMuPDF does not)
- Preserves table structure as Markdown tables
- Understands multi-column layouts
- Outputs clean, RAG-ready Markdown

PyMuPDF is retained as an explicit fallback controlled by a config flag
`DOCLING_ENABLED` (default: `True`). Setting `DOCLING_ENABLED=False` in the
environment reverts all PDF processing to the existing PyMuPDF path with zero
code changes required.

### Docling output routes to existing extractors

Docling converts all supported formats to Markdown. That Markdown output is then
routed to existing pipeline stages — no new extraction logic needed:

```
Docling → Markdown text
    ├── has headings → MarkdownSectionExtractor → section nodes + DEFINES relationships
    └── no headings  → flat chunking via pipeline.run()
```

### CPU-only operation

Docling is installed with CPU-only PyTorch to avoid CUDA dependencies:

```
pip install docling --extra-index-url https://download.pytorch.org/whl/cpu
```

This is suitable for development laptops and CPU-only Docker environments.
GPU acceleration is not required and not configured.

---

## Supported File Types After This ADR

| Extension | Docling support | Post-processing | Result |
|---|---|---|---|
| `.pdf` | ✅ Primary | → `MarkdownSectionExtractor` | Section nodes + DEFINES |
| `.docx` | ✅ | → `MarkdownSectionExtractor` | Section nodes + DEFINES |
| `.pptx` | ✅ | → `MarkdownSectionExtractor` | Section nodes + DEFINES |
| `.html` | ✅ | → `MarkdownSectionExtractor` | Section nodes + DEFINES |
| `.epub` | ✅ | → `MarkdownSectionExtractor` | Section nodes + DEFINES |
| `.xlsx` | ✅ | → flat chunking | Flat text chunks |
| `.csv` | ✅ | → flat chunking | Flat text chunks |
| `.md` | — (handled by MS6-IS3) | → `MarkdownSectionExtractor` | Section nodes + DEFINES |
| `.txt` | — (existing path) | → flat chunking | Flat text chunks |
| images | — (existing OCR path) | → flat chunking | Flat text chunks |

---

## Architecture

### New component: `DoclingConverter`

```
ingestion_service/src/core/converters/docling_converter.py
```

Single responsibility: convert file bytes → Markdown string.
Stateless, no DB access, no side effects. Consistent with existing extractor design.

```python
class DoclingConverter:
    def convert(self, file_bytes: bytes, filename: str) -> str:
        """Convert any supported file to Markdown text."""
        ...
```

### Routing in `ingest.py`

```
background_ingest_file()
    │
    ├── is_image        → existing OCR path (unchanged)
    ├── is_markdown     → existing MS6-IS3 path (unchanged)
    ├── is_tabular      → DoclingConverter → flat chunking
    │   (.xlsx, .csv)
    ├── is_pdf          → DoclingConverter (if DOCLING_ENABLED)
    │                   → PyMuPDF fallback (if not DOCLING_ENABLED)
    │                   → MarkdownSectionExtractor
    ├── is_rich_doc     → DoclingConverter
    │   (.docx, .pptx,  → MarkdownSectionExtractor
    │    .html, .epub)
    └── else            → existing flat text path (unchanged)
```

### Config flag

```python
# ingestion_service/src/core/config.py
DOCLING_ENABLED: bool = True
```

Override in `docker-compose.yml` or `.env`:
```
DOCLING_ENABLED=false   # revert to PyMuPDF for PDF
```

---

## Docling Model Downloads

Docling downloads AI models on first use (layout detection, table structure).
These are cached at `~/.cache/docling/` inside the container.

Options:
1. **Accept slow first run** — models download on first ingestion request
2. **Pre-download in Dockerfile** — `RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"` during build

Option 1 is acceptable for development. Option 2 is recommended for production.

---

## Files to Create / Modify

| File | Action |
|---|---|
| `ingestion_service/src/core/converters/__init__.py` | Create (new package) |
| `ingestion_service/src/core/converters/docling_converter.py` | Create new |
| `ingestion_service/src/core/config.py` | Add `DOCLING_ENABLED: bool = True` |
| `ingestion_service/src/api/v1/ingest.py` | Add routing for new file types |
| `ingestion_service/pyproject.toml` | Add `docling` with CPU-only PyTorch |
| `ingestion_service/Dockerfile` | Add `--extra-index-url` for CPU PyTorch |

---

## What Does Not Change

- `ingestion_service/src/core/extractors/pdf.py` (PyMuPDF) — untouched, fallback only
- `ingestion_service/src/core/extractors/markdown_extractor.py` — untouched
- `ingestion_service/src/core/pipeline.py` — no new methods needed
- `rag_orchestrator/` — no changes
- `vector_store_service/` — no changes
- Database schema — no migrations needed

---

## Alternatives Considered

### MarkItDown (Microsoft)

Evaluated as an alternative. Rejected because:
- Weaker table structure preservation than Docling
- No reading order detection for PDFs
- No built-in RAG-oriented chunking
- Docling's unified `DoclingDocument` representation is more robust

MarkItDown remains a valid lightweight alternative if Docling proves too heavy
for the deployment environment.

### Keep PyMuPDF for PDF

Rejected as primary path because:
- PyMuPDF extracts text blocks without reading order
- Table structure is lost — cells become unrelated text fragments
- Multi-column layouts are mangled
- Docling produces significantly better RAG context for structured PDFs

PyMuPDF retained as fallback via `DOCLING_ENABLED=False`.

### Separate extractors per file type

Rejected because:
- Increases codebase surface area
- Each extractor needs separate maintenance
- Docling handles all formats uniformly with consistent output quality

---

## Consequences

### Positive

- DOCX, PPTX, HTML, EPUB, XLSX, CSV ingestion now supported
- PDF quality significantly improved for structured documents
- Single converter component replaces multiple format-specific extractors
- PyMuPDF fallback preserves rollback safety
- CPU-only operation confirmed — no GPU required

### Negative

- Docling adds Docker image size (~2-3GB for CPU-only PyTorch)
- First-run model download adds latency (mitigated by Dockerfile pre-download)
- Docling is a heavier dependency than PyMuPDF

These tradeoffs are acceptable given the significant capability gain.

---

## Future Work

- ADR-048: Cross-artifact linking (Markdown documentation → code symbols)
- Pre-download Docling models in Dockerfile for production deployments
- Evaluate Docling VLM path for image-heavy PDFs if GPU becomes available

---
