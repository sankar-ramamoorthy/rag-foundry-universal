# Codebase Ingestion Architecture

**Status:** Draft  
**Date:** 2026-02-12  
**Depends on:** ADR-030, ADR-031  

---

## Overview

The codebase ingestion pipeline transforms raw repositories into a unified artifact graph stored in PostgreSQL.  

It enforces deterministic canonical identities, repository isolation, and rebuild-safe indexing.  

Ingestion is structured into three distinct phases:

1. **Extraction Phase** — parse source files, documents, ADRs.  
2. **Resolution Phase** — resolve symbol paths, relationships, and references.  
3. **Persistence Phase** — store artifacts and relationships in the database.  

All phases preserve the invariants defined in ADR-030 and ADR-031.

---

## 1. Extraction Phase

### Purpose

Convert raw repository content into structured, intermediate representations.

### Inputs

* Repository root
* Source files (`*.py`, `*.md`, `*.adoc`, etc.)
* Pre-existing `DocumentNode` graph (optional for incremental rebuild)

### Process

* **File discovery**  
  * Walk the repository tree
  * Identify supported artifact types (Documents, ADRs, Code files)
* **Parsing**
  * Documents: extract metadata, headings, text
  * ADRs: extract title, context, decisions, rationale
  * Code: parse ASTs for modules, classes, functions, methods, tests
* **Canonical ID generation**  
  * Generate `(repo_id, canonical_id)` for every artifact
  * Apply ADR-031 rules for structural stability

### Outputs

* In-memory collection of artifact nodes with:
  * `canonical_id`
  * `artifact_type`
  * Metadata dictionary
  * Source path and optional content snippet

---

## 2. Resolution Phase

### Purpose

Compute relationships between artifacts and validate cross-references.

### Processes

* **Symbol resolution**
  * Map class/method/function calls to their canonical IDs
  * Support intra-file and inter-file references
* **Relationship derivation**
  * Build edges for:
    * `CALLS`
    * `IMPORTS`
    * `EXTENDS`
    * `TESTS`
    * `DOCUMENTATION` (docs ↔ code)
    * `DECISION` (ADR ↔ code/document)
* **Validation**
  * Ensure all references point to existing canonical IDs
  * Detect orphaned artifacts or unresolved relationships
* **Metadata enrichment**
  * Record line numbers, code snippets, or textual highlights as optional metadata
  * No enrichment may alter canonical IDs

### Outputs

* Fully resolved in-memory graph of nodes and relationships

---

## 3. Persistence Phase

### Purpose

Persist the resolved graph in PostgreSQL in a deterministic, rebuild-safe manner.

### Database Schema

* **document_nodes**
  * `repo_id` UUID — repository boundary
  * `canonical_id` TEXT — primary artifact identity
  * `artifact_type` TEXT — type from `artifact_types.py`
  * `metadata` JSONB — flexible metadata per artifact
* **document_relationships**
  * `repo_id` UUID
  * `source_id` TEXT
  * `target_id` TEXT
  * `relationship_type` TEXT
  * `metadata` JSONB (optional)

### Persistence Rules

* Delete prior entries for `repo_id` before rebuild (full ingestion)
* Insert nodes and relationships in deterministic order (e.g., sorted by canonical_id)
* Apply uniqueness constraints:
  * `UNIQUE(repo_id, canonical_id)` for nodes
  * `UNIQUE(repo_id, source_id, target_id, relationship_type)` for relationships
* Apply indexes on `(repo_id, canonical_id)` and `(repo_id, artifact_type)` for performance

---

## Rebuild Model

* Ingestion is **idempotent**:
  * Running the pipeline multiple times produces the same canonical IDs and relationships.
  * Deletion of `repo_id` prior to full rebuild guarantees no residual artifacts.
* Incremental ingestion (future scope) may track modified files and only update affected nodes.
* Versioned or multi-repo ingestion may introduce `version_id` or `repo_alias` later.

---

## Tradeoffs

* Single unified graph simplifies traversal, but table sizes may grow with large codebases.
* Deterministic IDs are longer than UUIDs but support traceability and debugging.
* Static analysis may not capture runtime behavior — CALLS/EXTENDS edges are best-effort approximations.

---

## Future Considerations

* Materialized traversal views for high-density graphs
* Incremental ingestion for large repos
* Optional commit-level lineage tracking
* Cross-repo linking for multi-repo knowledge graphs

---

## References

* ADR-030: Unified Artifact Graph with Repository Isolation  
* ADR-031: Canonical Identity Model for Artifacts  
* `artifact_types.py` — defines canonical artifact types  

---

# Deliverables

* `document_nodes` and `document_relationships` tables populated from ingestion pipeline
* Deterministic canonical IDs
* Relationships fully resolved and persisted
* Rebuild-safe ingestion for entire repository
