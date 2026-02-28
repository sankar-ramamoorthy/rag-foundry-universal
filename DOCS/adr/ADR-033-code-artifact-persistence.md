# ADR-033: Code Artifact Persistence in Postgres

## Status
Proposed / Accepted

## Context
Currently, the project stores code artifacts entirely in-memory (RepoGraph). For MS4, we need persistent storage to support retrieval, embeddings, reproducible ingestion, and multi-pass analysis.

## Decision
- Persist code artifacts in Postgres using the existing `document_nodes` and `document_relationships` tables.
- Each artifact node will store:
  - `document_id` (UUID PK)
  - `repo_id` (UUID string)
  - `canonical_id` (deterministic, from `identity.py`)
  - `artifact_type` (function, class, module)
  - `title`, `summary`, `source`, `doc_type`
- Relationships between artifacts will be stored in `document_relationships`.
- Vector embeddings will link to `document_nodes` via `document_id`.
- Persistence layer (`CodebaseGraphPersistence`) will **upsert nodes and relationships** deterministically.

## Alternatives Considered
1. Keep memory-only storage  
   - Pros: Simple, no DB dependency  
   - Cons: Non-persistent, cannot support vector-based RAG, non-reproducible ingestion
2. Use external NoSQL store (MongoDB, etc.)  
   - Pros: Flexible schema  
   - Cons: Misaligned with current migration strategy and SQL-based pipelines

## Consequences
- DB schema aligns with migrations already created (`document_nodes` + `document_relationships`)  
- Supports deterministic ingestion, vector embedding, and future RAG queries
