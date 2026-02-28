## ADR-041-code-artifact-persistence-embedding-strategy.md

### ADR-041: **Document Node and Relationship Persistence - Embedding Text and Managing Code Artifacts**

---

# 📘 **ADR-041: Code Artifact Persistence Strategy — Embedding Text and Handling Relationships**

### Status

Accepted

### Date

2026-02-16

### Decision Owner

Code Intelligence Architecture

---

## 1. Context

The system currently ingests codebase artifacts and processes them for semantic retrieval. As part of the **MS4-IS6** effort, we need to enhance the `DocumentNode` model and its persistence strategy to store:

* The full or chunked text of code artifacts
* Relationships between code artifacts (via `DocumentRelationship`)
* Embeddings and vector chunks for semantic search

These changes are necessary to support more granular semantic search across code artifacts (functions, classes, methods, etc.) while tracking relationships between them for enhanced retrieval.

---

## 2. Architectural Options Considered

### Option A — Store Full Artifact Text in `DocumentNode`

#### Model

* **Artifact Node = Embedding Unit**
* The `DocumentNode` will store full or chunked text for each artifact (e.g., class, method).
* Each artifact node contains:

  * Structural metadata
  * Relationships
  * Source code snippet (`text`)
* This avoids the need for a separate text storage layer for artifacts.

#### Flow

```
AST → Artifact (with text)
       ↓
Persist Graph with text in DocumentNode
       ↓
Embed artifact.text
```

### Option B — Store Code Text Separately (Normalized Design)

#### Model

* `DocumentNode` stores artifact metadata but not the text.
* A separate table or storage location holds the full code text (e.g., `ArtifactText` table).
* This design normalizes the text data and reduces duplication across artifacts.

#### Flow

```
AST → Artifact (with metadata)
       ↓
Persist Graph with metadata in DocumentNode
       ↓
Store full artifact text in ArtifactText
       ↓
Embed artifact text
```

### Option C — Store Snippets for Each Artifact (Granular)

#### Model

* Each artifact (e.g., function body, class body) is split into granular snippets.
* Store the individual snippet text in `DocumentNode` or a separate table.
* This is ideal for more granular semantic search (e.g., searching for a specific function call).

#### Flow

```
AST → Artifact Snippets (e.g., function body, method)
       ↓
Persist Snippet Graph
       ↓
Embed Snippet Text
```

---

## 3. Evaluation

| Criteria                  | Option A            | Option B         | Option C                    |
| ------------------------- | ------------------- | ---------------- | --------------------------- |
| Simplicity                | High                | Medium           | Medium to High              |
| Implementation Cost       | Low                 | Medium           | High                        |
| Retrieval Precision       | Good                | Excellent        | Excellent                   |
| Granularity of Search     | Limited to Artifact | Full text access | Very granular (per-snippet) |
| Multi-language readiness  | Limited             | Strong           | Strong                      |
| Cognitive Load            | Low                 | Medium           | High                        |
| Premature Complexity Risk | Low                 | Medium           | High                        |

---

## 4. Decision

After evaluating the options, **Option A (Store Full Artifact Text in DocumentNode)** is chosen for the following reasons:

* **Simplicity**: This approach maintains a 1:1 mapping between artifacts and their embeddings, reducing complexity while ensuring text is stored alongside the metadata.
* **Efficiency**: Storing the text directly in `DocumentNode` simplifies the architecture and avoids introducing a separate text storage layer.
* **Immediate Use Case**: For semantic search and embeddings, having the full artifact text available within the same node simplifies the ingestion and retrieval process.

### **Deferred**:

* Option B (Normalized Design) and Option C (Granular Snippets) will be deferred, as they introduce additional complexity that is not needed for the current use case. These options will be reconsidered in the future if:

  1. **Granularity** of search becomes critical (e.g., for searching within function or class bodies).
  2. **Text overlap** in large code files becomes an issue for retrieval precision.
  3. **Advanced RAG Ranking** is required for fine-tuned search across large codebases.

---

## 5. Rationale

### 5.1 Current System Maturity

The ingestion system is in a phase of stabilization. Introducing the complexity of chunk-based storage or a separate text storage layer would hinder progress and potentially introduce bugs.

### 5.2 Immediate Objective

The goal is to get stable, artifact-level embeddings that support semantic search across entire code artifacts (e.g., methods, classes, functions). This approach will allow for:

* Easy integration of embeddings with a `DocumentNode` for each artifact.
* The ability to track relationships between artifacts using the `DocumentRelationship` model.

### 5.3 Risk Management

By deferring options that would introduce higher complexity, we reduce the chance of premature over-engineering. The risk of introducing unnecessary abstraction and complexity is avoided by sticking with the simplest solution for Phase 1.

---

## 6. Implementation Requirements

### 6.1 **DocumentNode Changes**

The `DocumentNode` ORM model should be updated to store the following fields:

* `text`: The code artifact text (full artifact or chunked, depending on decisions made later).
* `relationships`: The relationships with other nodes (via `DocumentRelationship`).

```python
class DocumentNode(Base):
    ...
    text: str = Column(String, nullable=False)
    relationships: list["DocumentRelationship"] = relationship("DocumentRelationship", back_populates="from_node")
```

### 6.2 **VectorChunks Persistence**

Update the persistence logic for `VectorChunks` to properly reference the `DocumentNode` and its text. Ensure that embedding is linked to the correct artifact (function, method, class).

### 6.3 **DocumentRelationship Model**

Track the relationships between different artifacts (e.g., one method depends on another, or one class calls another function). The `DocumentRelationship` model should persist:

* `from_document_id`: Source document node (e.g., calling method).
* `to_document_id`: Target document node (e.g., called method).
* `relation_type`: Type of relationship (e.g., "calls", "inherits").
* `relationship_metadata`: Optional metadata about the relationship.

---

## 7. Deferred Features

* **Option B and C** (Normalized Design and Granular Snippets) are deferred until further evaluation.
* **Sub-artifact chunking** will not be implemented in Phase 1.

---

## 8. Future Conditions for Option B and C

These options will be reconsidered when:

1. Large code artifacts start affecting retrieval precision.
2. Multi-language ingestion becomes necessary.
3. More granular code search is needed for specific code elements (e.g., function bodies, variable names).
4. Retrieval logic needs to be optimized with chunk-level scoring or re-ranking.

---

## 9. Guardrails

To preserve future flexibility and ensure future-proof architecture:

* **Artifact text** will remain part of the `DocumentNode` for Phase 1.
* **Embedding logic** should not tightly couple to the graph layer but remain separate.
* Relationships will be tracked independently using the `DocumentRelationship` table.
* **Text storage** should be optimized for retrieval, but not over-engineered for now.

---

## 10. Long-Term Target Architecture

```
API Layer
    ↓
Application Services
    ↓
Code Artifact Graph (Domain Layer)
    ↓
[Future] Chunk Assembly Layer
    ↓
Embedding Pipeline
    ↓
Vector Store
```

---

## 11. Consequences

### Positive

* Fast implementation
* Simpler architecture with clear artifact-level embeddings
* Easier future evolution path

### Negative

* Retrieval is limited to full artifact boundaries.
* The granularity of search is coarser, as only whole artifacts are embedded.

---

## 12. Strategic Position

The phased approach allows for:

* **Phase 1**: Implement artifact-level embeddings with full-text persistence.
* **Phase 2**: Evaluate retrieval quality and consider hybrid chunk layers if needed.
* **Phase 3**: Evolve chunking and relationship complexity based on empirical results.

This ensures stability and avoids prematurely over-engineering the system.

---

# Final Positioning

This ADR formalizes the **Phase 1** decision to implement artifact-level embeddings and persistence for code artifacts, while deferring chunk-based approaches and related complexities for later evaluation. We will continue to iterate based on real-world usage and retrieval metrics.

---


