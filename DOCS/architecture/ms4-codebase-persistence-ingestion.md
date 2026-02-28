
# **MS4 Design Document – Persistence & Ingestion Integration**

## DOCS/ms4-codebase-persistence-ingestion.md

# MS4 Design Document: Persistence & Ingestion Integration

## Overview
MS4 introduces a **persistent backend for the repository graph** and **integrates it with the ingestion pipeline**. This supports structured RAG queries over Python code, multi-pass ingestion, deterministic rebuilds, and vector embeddings.

This document builds on ADRs 030–037.

## Architecture Diagram
```

Repository (Git URL / Local Path)
│
▼
RepoGraphBuilder (MS3) ──> CodebaseGraphPersistence (MS4)
│                     │
▼                     ▼
SymbolTable / Call Graph    Postgres DB
│                     │
▼                     ▼
DocumentNodes & Relationships
│
▼
IngestionPipeline
│
▼
Vector Store

```

## Entities / DB Schema
- `document_nodes`  
  - `document_id` (PK UUID)  
  - `repo_id` (UUID)  
  - `canonical_id` (string)  
  - `artifact_type` (function/class/module)  
  - `title`, `summary`, `doc_type`, `source`  
  - Relationships: `vector_chunks`, `incoming_relationships`, `outgoing_relationships`

- `document_relationships`  
  - `id` (PK)  
  - `from_document_id` → `document_nodes.document_id`  
  - `to_document_id` → `document_nodes.document_id`  
  - `relation_type`  
  - `relationship_metadata`  

- `vectors`  
  - Embedding chunks linked to `document_nodes`  

## Persistence Layer
**Service:** `CodebaseGraphPersistence`  
Responsibilities:
1. Upsert `document_nodes` and `document_relationships` deterministically using `repo_id + canonical_id`.
2. Ensure multi-pass ingestion does not duplicate nodes.
3. Optionally track file hashes/timestamps for changes.
4. Batch insert/update embeddings if required.

**Methods:**
- `save_nodes(nodes: list[RepoGraphNode], repo_id: str)`  
- `save_relationships(relationships: list[RepoGraphRelationship], repo_id: str)`  
- `get_node_by_canonical_id(repo_id: str, canonical_id: str) -> DocumentNode`

## API Endpoint
**Endpoint:** `/v1/codebase/ingest-repo`  
- Accepts:
  - `git_url: str` (optional)  
  - `local_path: str` (optional)  
- Validates input. Must have at least one of `git_url` or `local_path`.
- Creates a background `IngestionRequest` in DB.
- Spawns **background ingestion worker**:
  1. Clone repo (if Git URL)  
  2. Build RepoGraph via `RepoGraphBuilder`  
  3. Persist nodes & relationships via `CodebaseGraphPersistence`  
  4. Run `IngestionPipeline` for embeddings  
  5. Update ingestion status (`running` → `completed` / `failed`)  
  6. Trigger optional summary generation

## Background Worker Flow
- Input: `repo_id`, `git_url` / `local_path`  
- Steps:
  1. Determine repo path (clone if necessary)
  2. Build repo graph (MS3 code)  
  3. Persist nodes and relationships (MS4 persistence layer)  
  4. Embed code artifacts (IngestionPipeline)  
  5. Update `IngestionRequest` status  
  6. Optional: summary dispatch to LLM service

## Deterministic Rebuild
- Use `repo_id + canonical_id` for upserts  
- Optional file hash / timestamp to detect changes  
- Idempotent ingestion ensures consistent graph

## Logging & Observability
- Structured logging for each ingestion step
- Include:
  - Ingestion ID  
  - Repository path / URL  
  - Status updates (`accepted`, `running`, `completed`, `failed`)  
  - Errors / exceptions  
- Support for metrics / Prometheus / tracing in future

## Testing Strategy
- Unit Tests:
  - `CodebaseGraphPersistence` node/relationship upsert  
  - Canonical ID correctness (identity.py)  
  - Deterministic rebuild behavior
- Integration Tests:
  - `/v1/codebase/ingest-repo` end-to-end ingestion  
  - Vector embedding persistence  
  - Multi-pass graph rebuild  

## References
- ADR-030 → ADR-037
- MS3 RepoGraphBuilder & SymbolTable  
- Existing ingestion_service structure  
