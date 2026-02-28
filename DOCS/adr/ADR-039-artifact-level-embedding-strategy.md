# 📘 ADR-039

## **ADR-039: Code Artifact Embedding Strategy for Repository Ingestion**

### Status

Proposed

### Date

2026-02-15

### Decision Owner

Code Intelligence Architecture

---

## 1. Context

Repository ingestion builds a structural graph of code artifacts using `RepoGraphBuilder`.

Artifacts include:

* MODULE
* CLASS
* FUNCTION
* METHOD
* CALL

These artifacts are persisted via `CodebaseGraphPersistence`.

However, embedding requires textual content.
The structural graph alone does not contain source code text.

Without textual content:

* Vector store remains empty
* Semantic search fails
* Code RAG becomes non-functional

---

## 2. Problem

There is a conceptual mismatch between:

* Structural graph persistence
* Semantic embedding requirements

Current artifact entities contain:

* Metadata
* Identifiers
* Relationships

They do not contain:

* Source code text (`text` field)

Embedding pipeline expects:

```python
text = node.get("text", "")
```

But no such field exists.

---

## 3. Decision

Repository ingestion will embed **source code snippets per artifact**.

### 3.1 Each artifact must include:

```python
"text": "<source code snippet>"
```

This field will be added during graph construction inside `RepoGraphBuilder`.

---

## 4. Embedding Granularity

Embedding will occur at artifact level:

| Artifact Type | Embedded Content               |
| ------------- | ------------------------------ |
| MODULE        | Entire file contents           |
| CLASS         | Full class definition block    |
| FUNCTION      | Full function definition block |
| METHOD        | Full method definition block   |
| CALL          | Not embedded (structural only) |

---

## 5. Text Extraction Strategy

During AST traversal:

* Use `ast.get_source_segment(source_code, node)`
* Or use `lineno` / `end_lineno` slicing

`RepoGraphBuilder` must retain access to original file contents while parsing.

---

## 6. Rationale

### 6.1 Structural + Semantic Separation

Graph provides:

* Call relationships
* Definitions
* Ownership hierarchy

Embeddings provide:

* Semantic similarity
* Conceptual search
* RAG retrieval

Both layers serve different purposes.

---

### 6.2 Artifact-Level Granularity

Embedding at artifact level provides:

* Fine-grained retrieval
* Smaller embedding units
* More precise semantic matching
* Better RAG chunking behavior

Embedding entire files would:

* Reduce retrieval precision
* Increase noise
* Increase embedding size variance

---

## 7. What Will NOT Be Embedded

* Pure metadata
* CALL nodes
* Empty artifacts
* Synthetic nodes

Only artifacts with meaningful source code text will be embedded.

---

## 8. Future Extensions

This decision enables:

* Code summarization per artifact
* Semantic clustering
* Function similarity search
* Cross-repository semantic analysis
* Hybrid graph + embedding retrieval

---

## 9. Consequences

### Positive

* Enables functional Code RAG
* Maintains structural graph integrity
* Preserves architectural separation
* Supports fine-grained semantic search

### Negative

* Slight increase in graph memory footprint
* Additional CPU cost during ingestion
* Increased vector store size

---

## 10. Implementation Plan

1. Modify `RepoGraphBuilder`
2. Add `"text"` field to artifact dict
3. Ensure persistence supports text field
4. Verify embedding loop processes only non-empty text
5. Add logging for skipped nodes

---

## 11. Future ADR (Planned)

A future ADR will define:

* Chunking strategy for very large functions
* Hybrid retrieval scoring (graph + vector)
* Code summarization layer

---

# Summary

ADR-038 stabilizes pipeline construction architecture.
ADR-039 formalizes semantic embedding strategy for code artifacts.

Together they move the system from:

> Structural ingestion

To:

> Structured + Semantic Code Intelligence Platform

---

