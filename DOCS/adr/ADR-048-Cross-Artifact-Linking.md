# ADR-048: Cross-Artifact Linking — Markdown Documentation to Code Symbols

**Status:** Accepted
**Date:** 2026-02-28
**Relates to:** ADR-030 (Unified Artifact Graph), ADR-031 (Canonical Identity),
               ADR-043 (Markdown Section Extraction), ADR-046 (Document Graph Retrieval),
               ADR-047 (Docling Universal Pre-processor)
**Implemented by:**  IS8 — ADR-048 cross-artifact linking

---

## Context

ADR-030 defines the Unified Artifact Graph as covering:

> Code → Document linking
> Code → ADR linking
> Document → Code traceability

ADR-043 introduced `MARKDOWN_SECTION` nodes into the graph for `.md` files
in repositories. ADR-046 activated document graph retrieval for uploaded files.
ADR-047 extended document ingestion to Office formats via Docling.

However, no relationship exists between Markdown documentation nodes and the
code symbols they describe. A repository containing both `README.md` and
`math_utils.py` produces two disconnected subgraphs:

```
README.md#math_utils.calculator.add   (MARKDOWN_SECTION)
math_utils.py#Calculator.add          (METHOD)
```

These describe the same symbol but have no graph edge connecting them. This
means:

- A query about `add()` retrieves either the code node OR the documentation
  section — not both
- Graph traversal cannot cross from documentation to implementation or vice versa
- The "Document → Code traceability" goal of ADR-030 is unfulfilled

---

## Decision

Introduce a `DOCUMENTS` relationship type connecting `MARKDOWN_SECTION` nodes
to the code symbols they document, within the same repository ingestion.

### Relationship type

```
MARKDOWN_SECTION  →  DOCUMENTS  →  CLASS | FUNCTION | METHOD | MODULE
```

Direction: documentation points to code. A section documents a symbol.
Inverse traversal (code → documentation) is supported by querying incoming
DOCUMENTS edges.

### Matching strategy

Matching is **deterministic, structural, and exact** — no LLM, no fuzzy
matching, no semantic similarity.

**Algorithm:**

1. After all artifacts are extracted and the symbol table is built for a repo,
   collect all `MARKDOWN_SECTION` nodes
2. For each section, take its `name` field (raw heading text)
3. Normalise: lowercase, strip whitespace
4. Look up the normalised name in the symbol table
5. If an exact match is found → create `DOCUMENTS` relationship
6. If no match → skip silently (not all sections document code symbols)

**Symbol table lookup:**

The existing `build_symbol_table()` already maps `name → canonical_id` for all
code artifacts. No new infrastructure required.

**Example:**

| Section name | Normalised | Symbol table lookup | Result |
|---|---|---|---|
| `"add"` | `"add"` | `math_utils.py#Calculator.add` | ✅ DOCUMENTS |
| `"Calculator"` | `"calculator"` | `math_utils.py#Calculator` | ✅ DOCUMENTS |
| `"run_demo"` | `"run_demo"` | `main_app.py#App.run_demo` | ✅ DOCUMENTS |
| `"Overview"` | `"overview"` | — (no match) | skipped |
| `"Dependencies"` | `"dependencies"` | — (no match) | skipped |

### Scope

**Repo ingestion only.** `_link_docs_to_code()` runs inside `RepoGraphBuilder.build()`
after `_resolve_calls()`. It only links artifacts within the same `repo_id`.

**File upload path is explicitly out of scope.** Uploaded business documents
(Word, PDF, Markdown) stand alone — they have no code graph to link against.
Cross-ingestion linking between uploaded documents and code repositories is
deferred to a future project.

---

## Implementation

### New method in `RepoGraphBuilder`

```python
def _link_docs_to_code(self, graph: RepoGraph, symbol_table) -> None:
    """
    IS8: Create DOCUMENTS relationships from MARKDOWN_SECTION nodes
    to the code symbols they document.
    Exact name match via symbol table. Deterministic, no LLM.
    """
```

Called at the end of `build()`:

```python
symbol_table = build_symbol_table(graph)
self._attach_defines(graph)
self._resolve_calls(graph, symbol_table)
self._link_docs_to_code(graph, symbol_table)   # IS8 — new, last step
return graph
```

### No schema changes

`DOCUMENTS` is a new value for the existing `relation_type` text column in
`document_relationships`. No migration required.

### Relationship metadata

```json
{
  "match_strategy": "exact_name",
  "section_name": "add",
  "confidence": 1.0
}
```

Confidence is always 1.0 for exact matches. Recorded for future use if
fuzzy matching is introduced.

---

## What This Enables

### At query time

A query landing on `math_utils.py#Calculator.add` (code) can traverse
incoming DOCUMENTS edges to find `README.md#...calculator.add` (docs) —
bringing documentation context into a code query automatically.

A query landing on `README.md#...calculator.add` (docs) can traverse
outgoing DOCUMENTS edges to find the implementation — bringing code
context into a documentation query.

### Example traversal

```
Query: "how does add work?"
    ↓
Vector search → seeds: README.md#...calculator.add (docs)
    ↓
DOCUMENTS edge traversal →
    math_utils.py#Calculator.add (code)
    ↓
DEFINES edge traversal →
    math_utils.py#Calculator (class context)
    ↓
LLM receives: docs + implementation + class context
```

---

## Two Ingestion Paths — Explicitly Separated

```
PATH 1: Repo ingestion (RepoGraphBuilder)
    .py  → AST extraction     → code graph
    .md  → MarkdownExtractor  → section graph
    IS8  → _link_docs_to_code → DOCUMENTS edges (within repo only)

PATH 2: File upload (ingest.py)
    .md        → MarkdownExtractor → section graph (standalone)
    .docx/.pdf → Docling → Markdown → section graph (standalone)
    .xlsx/.csv → Docling → flat chunks
    No cross-linking — business documents stand alone
    No expectation of linking to code repos (deferred to future project)
```

This separation is a deliberate architectural boundary, not a limitation.
Business knowledge documents and code repositories are independent knowledge
domains. Linking them across ingestion boundaries requires query-time context
that does not exist during ingestion.

---

## Alternatives Considered

### LLM-based matching

Use an LLM to determine whether a section documents a symbol based on
semantic content.

**Rejected because:**
- Violates ADR-030 invariant: "No LLM usage during ingestion"
- Non-deterministic — same input may produce different links
- Not rebuild-safe
- Adds latency and cost to ingestion

### Fuzzy / similarity matching

Use edit distance or token overlap to match section names to symbol names.

**Rejected because:**
- Non-deterministic across thresholds
- Produces false positives (e.g. `"usage"` matching `"use"`)
- Exact matching is sufficient for well-structured documentation
- Fuzzy matching can be added later as an opt-in extension

### Canonical ID path matching

Match section canonical ID path components against code canonical IDs.

Example: `README.md#math_utils.calculator.add` contains `calculator` and `add`
— match against `math_utils.py#Calculator.add`.

**Considered but deferred:** More powerful than name matching but requires
path decomposition logic and introduces ambiguity when path components are
common words. Exact name matching is a safer first step.

---

## Consequences

### Positive

- ADR-030 "Document → Code traceability" goal fulfilled for repo ingestion
- No schema changes required
- No LLM usage during ingestion — deterministic and rebuild-safe
- Graph traversal now crosses documentation/code boundary within a repo
- RAG quality improves for queries that span docs and code
- Zero impact on file upload path

### Negative

- Only sections whose `name` exactly matches a symbol name are linked
  (well-structured documentation will link well; prose headings will not)
- Symbol table currently maps by short name only — ambiguous if two symbols
  share a name in different files (symbol table returns first match)
- Uploaded documents remain unlinked from code (accepted, by design)

---

## Future Work

- Canonical ID path matching for richer section-to-symbol resolution
- Cross-ingestion linking between uploaded documents and code repos (future project)
- Fuzzy name matching as opt-in extension with confidence threshold
- Reverse traversal tooling: given a code symbol, find all documenting sections

---
