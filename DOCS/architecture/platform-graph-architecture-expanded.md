---
# DOCS\architecture\platform-graph-architecture-expanded.md
# Platform Graph Architecture Design

## Overview

This document outlines the architectural changes for the **shared graph model** that will be promoted from the `ingestion_service` to the `shared/` layer. The primary goal of this change is to establish **graph schema ownership** within the shared platform layer, ensuring all services interact with a common data model, and laying the groundwork for advanced graph traversal, reasoning, and query features across multiple services.
# DOCS\adr\ADR-044-graph-models-in-shared

---

## Problem Statement

The current system has two primary services interacting with the graph data:

* `ingestion_service`: Responsible for ingesting documents, persisting nodes, and relationships into the graph database.
* `rag_orchestrator`: Responsible for query routing, graph-based retrieval, and retrieval-based generation tasks.

These services currently duplicate and import models from each other, creating architectural tension and breaking service boundaries. Furthermore, the graph schema — consisting of **DocumentNode** and **DocumentRelationship** — is an internal concern of `ingestion_service`, but its utility spans across multiple services, including `rag_orchestrator`.

This setup leads to:

1. Tight coupling between services.
2. Data schema drift risks.
3. Increased maintenance complexity due to service interdependencies.

The goal is to refactor this architecture so that **graph schema ownership** is maintained centrally in a shared platform layer, decoupling the services and reducing the risk of schema drift.

---

## Architectural Change

### 1. **Shared Platform Layer**:

The **DocumentNode** and **DocumentRelationship** ORM models will be moved from the `ingestion_service` to the `shared/` layer, which will serve as the **canonical source of truth** for the graph schema.

New directory structure:

```
shared/
 ├── models/
 │    base.py                 # Shared SQLAlchemy base model
 │    document_node.py        # DocumentNode ORM model
 │    document_relationship.py # DocumentRelationship ORM model
 │    vector_chunk.py         # VectorChunk ORM model (if used cross-service)
 │    __init__.py
```

Both `ingestion_service` and `rag_orchestrator` will import from this shared layer:

```python
from shared.models import DocumentNode, DocumentRelationship
```

### 2. **Database Schema**

* The database schema for these models will **remain unchanged**.
* The `ingestion_service` will still be responsible for **writing** to the database.
* The `rag_orchestrator` and any other services will **read** from the database but will no longer need to import `ingestion_service` ORM models.

This decouples the services by placing the graph schema into a **shared contract**, which can be consumed by any service.

---

## Logical Architecture

### Diagram: **Platform Graph Architecture**

```plaintext
      +----------------+                        +-------------------+
      | ingestion      |                        | rag_orchestrator   |
      | service        |                        |                   |
      | (writes graph) | <-- Graph Schema --->  | (reads graph)     |
      +----------------+                        +-------------------+
              ^                                        ^
              |                                        |
              +----------------------------------------+
                          Shared Platform Layer
                             (shared/models)
```

* **Ingestion Service**: Writes `DocumentNode` and `DocumentRelationship` data to the database.
* **RAG Orchestrator**: Uses the same schema to run retrieval and graph-based queries.

The shared models act as a **contract** between services, ensuring no duplication of logic and consistent schema usage.

---

## Data Ownership Boundaries

### **Before Refactor**:

* `ingestion_service` owns the **graph schema** and imports it into other services.
* `rag_orchestrator` was tightly coupled with `ingestion_service`, importing ORM models directly.

### **After Refactor**:

* The **shared layer** owns the schema, and both services import it directly.
* No direct service-to-service imports occur between `ingestion_service` and `rag_orchestrator`.

This change establishes clear **data ownership boundaries**:

* **Shared Layer**: Owns the schema and provides models.
* **Ingestion Service**: Owns the responsibility for writing to the graph.
* **RAG Orchestrator**: Leverages the graph for retrieval tasks.

---

## Graph Schema Lifecycle

### 1. **DocumentNode**:

* **Ingestion**: During the ingestion phase, the `DocumentNode` is created and persisted to the database. It represents the atomic unit of the codebase artifact, such as a class, function, or module.
* **Persistence**: DocumentNodes are stored in the database and are accessible via the shared schema contract.
* **Usage**: The `rag_orchestrator` uses `DocumentNode` to traverse the graph, ask queries, and perform retrieval tasks.

### 2. **DocumentRelationship**:

* **Ingestion**: Relationships are ingested alongside nodes, representing connections between codebase artifacts. These relationships could be of types like `CALL`, `DEFINES`, or `IMPORT`.
* **Persistence**: Like nodes, relationships are persisted in the database and accessible from the shared schema.
* **Usage**: The `rag_orchestrator` utilizes these relationships to expand search queries, run graph traversals, and answer complex queries that require relationship-aware retrieval.

### 3. **VectorChunk** (if applicable):

* The `VectorChunk` model, if used in future scenarios for embedding storage, will also reside in the **shared** model layer, ensuring that both ingestion and retrieval services can work with it consistently.

---

## Query Flow

1. **Ingestion Service**:

   * Ingests documents.
   * Creates and persists `DocumentNode` and `DocumentRelationship` entries.
   * Optionally processes embeddings for storage in external vector stores.

2. **RAG Orchestrator**:

   * Reads the graph schema to perform query routing.
   * Leverages graph traversal (e.g., BFS, DFS) and relationship expansion.
   * Returns relevant artifacts to LLMs for generation or other processing tasks.

---

## Future Expansion: Advanced Graph Features

This refactor sets the stage for future graph-aware retrieval systems, including:

* **Graph-Based Retrieval**: Use of the graph schema to retrieve related documents or artifacts based on defined relationships (CALLs, DEFINES, etc.).
* **Graph Reasoning**: Building AI models that reason over codebase graphs for automated task generation, bug-fixing, etc.
* **Multi-Repo Federation**: Extending the graph model to handle federated graphs across multiple repositories and databases.
* **Context-Aware Retrieval**: Enabling contextual search that factors in graph relationships for more relevant results.

The shared platform layer becomes a key enabler of these future features.

---

## Migration Plan

### Steps to implement the change:

1. **Move Models**:

   * Move `DocumentNode`, `DocumentRelationship`, and related models from `ingestion_service` to `shared/models/`.
   * Ensure no other logic is moved; just the models and any associated SQLAlchemy `Base`.

2. **Update Imports**:

   * In `ingestion_service` and `rag_orchestrator`, update imports to reference `shared/models` instead of the old `ingestion_service` location.

3. **Verify Database Schema**:

   * Ensure that no changes are made to the underlying database schema — the models should map directly to the existing schema.

4. **Run Tests**:

   * Run integration tests to ensure both services can still read and write to the graph without issue.

5. **Deploy**:

   * Deploy the change with minimal downtime, ensuring no disruption to either ingestion or retrieval services.

---

## Conclusion

This refactor establishes a **shared graph model** as a platform-wide contract, reducing schema duplication, improving service boundaries, and positioning the system for future graph-based features. It enforces clear data ownership boundaries, ensuring that each service interacts with a single source of truth, and removes the tight coupling that was previously present between `ingestion_service` and `rag_orchestrator`.

By promoting graph schema to a shared platform layer, we align our architecture for scalability, flexibility, and maintainability as we evolve into more complex graph-based reasoning and retrieval tasks in the future.

---

