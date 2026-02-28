# Ingestion Service – Design Overview

## Purpose

The ingestion service is a standalone, black-box component responsible
for converting documents and images into structured, retrievable artifacts.

## Scope

- Document and image ingestion
- Text extraction and OCR
- Chunking and metadata extraction
- Artifact persistence

## Non-Goals

- Retrieval
- Query-time reasoning
- User authentication
- Long-term memory

## Integration Model

Downstream systems interact with ingestion exclusively via
versioned HTTP APIs (and later MCP tools).

The ingestion service does not depend on downstream services.
