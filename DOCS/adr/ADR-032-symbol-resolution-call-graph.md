## DOCS\adr\ADR-032-symbol-resolution-call-graph.md

# ADR-032 — Layered Symbol Resolution & Deterministic Call Graph Model

**Status:** Proposed
**Date:** 2026-02-13
**Related ADRs:** ADR-030 (Unified Artifact Graph), ADR-031 (Canonical Identity Model)

---

## Context

The `rag-foundry-coderag` ingestion service currently produces a unified artifact graph (ADR-030) with deterministic canonical IDs (ADR-031). All artifacts are identified, but there is no semantic resolution between them.

To enable downstream capabilities such as:

* Function-level call graph traversal
* Dependency analysis
* Deterministic symbol resolution
* Accurate DEFINES relationships

we need a **layered symbol resolution model**. This will transform raw artifacts into a semantically linked graph, maintaining correctness, determinism, and future extensibility.

---

## Problem Statement

Currently:

1. CALL artifacts exist as strings (e.g., `"ast.parse"`), not linked to enclosing functions.
2. IMPORT artifacts capture names and modules but are not resolved into a symbol table.
3. There is no explicit DEFINES relationship linking modules, classes, and functions.
4. Multi-pass semantic resolution is not supported, limiting:

   * Reverse lookups
   * Call graph analysis
   * Accurate RAG-based queries

Without layered resolution, downstream analysis will be flat, imprecise, and difficult to extend.

---

## Goals

1. Build **Function → Function** call relationships.
2. Maintain deterministic resolution using canonical IDs.
3. Support phased growth: start constrained, expand to nested scopes later.
4. Enhance `PythonASTExtractor` minimally to support parent context.
5. Ensure all resolution is reproducible, deterministic, and debuggable.
6. Document all relationships explicitly.

---

## Proposed Solution

We introduce a **Layered Resolution Model** with three layers:

### Layer 1 — Raw Extraction

* Existing AST extraction remains unchanged.
* Artifacts produced include: MODULE, IMPORT, CLASS, FUNCTION/METHOD, CALL.
* CALL artifacts are enhanced to include:

```python
"parent_id": "<enclosing function or method canonical ID>"
```

### Layer 2 — Symbol Table Construction

* Build **file-local symbol tables**:

```python
class FileSymbolTable:
    definitions: Dict[str, str]   # name -> canonical ID
    imports: Dict[str, str]       # local name -> source module/entity
```

* Build a **global symbol index** mapping names to entity IDs across the repo.

* Symbol tables are **in-memory only** (Option A) for MS3.

### Layer 3 — Resolution

* For each CALL:

1. Look in enclosing function’s file symbol table.
2. Resolve through file imports.
3. Fallback to global symbol index.
4. If unresolved → mark as `EXTERNAL`.

* Deterministic CALL relationships established:

```
Function → Function
```

* DEFINE relationships:

```
MODULE DEFINES CLASS
MODULE DEFINES FUNCTION
CLASS  DEFINES METHOD
```

---

## Extractor Modifications

`PythonASTExtractor` will:

1. Track a **current function stack** while visiting AST nodes.
2. Attach `parent_id` to all CALL artifacts.
3. Preserve full attribute chains in CALL names (e.g., `utils.helper`).

No other changes are needed for MS3.

---

## Trade-offs

* **Constrained scope**: Nested functions, decorators, and dynamic attributes are deferred to future phases.
* **Stdlib calls**: Resolved if possible, otherwise marked EXTERNAL.
* **Symbol tables**: In-memory only in MS3, persistence deferred to MS4.

This phased approach balances correctness, simplicity, and incremental growth.

---

## Future Considerations (MS4+)

* Persist symbol tables as artifacts for cross-repo resolution.
* Support nested scopes, decorators, and runtime dynamic resolution.
* Integrate multi-language extractors using the same resolution model.
* Improve ambiguous resolution handling for multiple matches.

---

## Implementation Impact

* **RepoGraphBuilder** (MS3-IS1) enhanced with layered symbol table creation.
* **Symbol Table Builder** (MS3-IS2) populates file and global tables.
* **CALL Resolution Algorithm** (MS3-IS3) links CALL artifacts to resolved targets.
* **DEFINES Relationships** (MS3-IS4) explicitly recorded.
* **Integration Test** (MS3-IS5) verifies small repo with deterministic graph.

---

## References

* [ADR-030 — Unified Artifact Graph](https://github.com/sankar-ramamoorthy/rag-foundry-coderag/blob/main/DOCS/adr/ADR-030-unified-artifact-graph.md)
* [ADR-031 — Canonical Identity Model](https://github.com/sankar-ramamoorthy/rag-foundry-coderag/blob/main/DOCS/adr/ADR-031-canonical-identity-model.md)

also see
## DOCS\architecture\extraction-hierarchy-model.md
---

**Decision:** Approve layered resolution model, parent_id enhancement, in-memory symbol tables, and phased implementation.

---

                    ┌─────────────────────────┐
                    │   Layer 1: Extraction   │
                    │   (PythonASTExtractor)  │
                    └─────────────┬──────────┘
                                  │ emits
                                  ▼
                    ┌─────────────────────────┐
                    │  Artifacts (Unified)    │
                    │ ┌───────────────┐       │
                    │ │ MODULE        │       │
                    │ │ CLASS         │       │
                    │ │ FUNCTION/METHOD │     │
                    │ │ IMPORT        │       │
                    │ │ CALL          │       │
                    │ └───────────────┘       │
                    └─────────────┬──────────┘
                                  │ input
                                  ▼
                    ┌─────────────────────────┐
                    │ Layer 2: Symbol Tables  │
                    │ (File-local & Global)   │
                    └─────────────┬──────────┘
                                  │ used for
                                  ▼
                    ┌─────────────────────────┐
                    │ Layer 3: Resolution     │
                    │  - CALL → Function      │
                    │  - IMPORT → Symbol      │
                    │  - MODULE/CLASS/FUNC    │
                    │    DEFINES relationships│
                    │  - EXTERNAL markers     │
                    └─────────────┬──────────┘
                                  │ produces
                                  ▼
                    ┌─────────────────────────┐
                    │ Repo Graph (Semantic)   │
                    │                         │
                    │ MODULE ──DEFINES──> CLASS
                    │ MODULE ──DEFINES──> FUNC
                    │ CLASS  ──DEFINES──> METHOD
                    │ FUNC   ──CALLS───> FUNC/EXTERNAL
                    │ ...                     │
                    └─────────────────────────┘
