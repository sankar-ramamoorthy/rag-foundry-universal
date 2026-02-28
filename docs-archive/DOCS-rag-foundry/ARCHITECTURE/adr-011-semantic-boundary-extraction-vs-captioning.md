# ADR 011: Semantic Boundary Between Extraction and Captioning

## Status
Accepted

## Date
2026-01-11

## Context

The ingestion system supports PDFs, images, and text files.
PDF extraction now yields both text blocks and embedded images as first-class artifacts.

There is a strong architectural risk that semantic interpretation (e.g., image captioning,
alt-text generation, or summarization) could leak into early ingestion stages
(extractors, chunkers, OCR adapters), making the pipeline brittle and hard to evolve.

## Decision

We establish a strict semantic boundary:

### MS4 (Document Linking & Metadata)
MS4 is limited to **structural and deterministic processing**:
- Text extraction
- Image extraction
- OCR text recovery
- Page-level provenance
- Extraction order
- Artifact association
- Chunk lineage

No semantic interpretation is performed.

###  (Semantic Enrichment) Agentic-RAG-Platform (out of scope)
Agentic-RAG-Platform (out of scope) is responsible for **meaning generation**, including:
- Image captioning
- Alt-text generation
- Cross-modal summarization
- Semantic labels
- Retrieval-time semantic expansion

Extractors, chunkers, and OCR adapters must remain semantics-free.

## Consequences

- PDF-extracted images may exist without captions.
- OCR output is treated as raw recovered text, not interpreted meaning.
- Captioning models can be added, replaced, or removed without touching ingestion code.
- Retrieval behavior remains deterministic until MS5 is explicitly applied.

This separation reduces coupling, improves testability, and preserves long-term flexibility.
