## DOCS\architecture\extraction-hierarchy-model.md

# 📘 What This Change Actually Represents

We are moving from:

> Flat artifact emission

to:

> Hierarchical artifact graph emission

This is not MS3 logic.
This is strengthening MS2 to satisfy ADR-032.

So this is architectural, not incidental.

---

# ❓ Do We Need a New ADR?

No — not a new ADR.

Here’s why:

* ADR-030 (Unified Artifact Graph) already defines a graph model.
* ADR-031 (Canonical Identity Model) defines stable IDs.
* ADR-032 (Layered Resolution) assumes hierarchical relationships.

What we are doing now is:

> Aligning the extractor implementation with existing ADR intent.

So instead of a new ADR, this should be:

### 📄 A short Architecture Addendum

Add a new file:

```
DOCS/architecture/AST-HIERARCHY-MODEL.md
```

or

```
DOCS/architecture/extraction-hierarchy-model.md
```

I recommend:

👉 `DOCS/architecture/extraction-hierarchy-model.md`

Because this is specifically about extraction semantics.

---

# 📘 Design: Hierarchical Extraction Model

Here is the design you can document.

You can paste this into the file.

---

## Extraction Hierarchy Model

### Motivation

MS3 introduces layered symbol resolution and DEFINES relationships.

For this to function deterministically, extracted artifacts must explicitly encode parent-child relationships.

Flat artifact emission is insufficient.

---

## Hierarchical Artifact Structure

All artifacts emitted by extractors must include:

```
parent_id: Optional[str]
```

### Hierarchy Rules

| Artifact Type | parent_id                       |
| ------------- | ------------------------------- |
| MODULE        | None                            |
| CLASS         | module ID                       |
| FUNCTION      | module ID                       |
| METHOD        | class ID                        |
| CALL          | enclosing FUNCTION or METHOD ID |

---

## Design Principles

1. **Deterministic hierarchy**

   * No inference in RepoGraphBuilder.
   * Extractor is authoritative.

2. **Extractor responsibility**

   * Extractor must track scope context:

     * current module
     * current class
     * current function/method

3. **No resolution at extraction time**

   * CALL artifacts remain unresolved.
   * Only parent-child hierarchy is encoded.

4. **Graph layer responsibility**

   * RepoGraphBuilder establishes:

     * DEFINES edges
     * CALL resolution edges
     * Symbol tables

---

## Scope Tracking Strategy

Extractor maintains a stack:

```
scope_stack: List[str]  # canonical IDs
```

Push:

* When entering class
* When entering function/method

Pop:

* When exiting

Current parent_id is:

```
scope_stack[-1] if scope_stack else module_id
```

Module is implicitly the root.

---

## Why This Is Correct

This ensures:

* Stable canonical identity
* Deterministic hierarchy
* No second-pass guessing
* Clean layering between MS2 and MS3
* Future-proof for MS4 multi-language support

---

## Non-Goals

* No symbol resolution
* No import resolution
* No cross-file inference
* No type inference

Extraction remains purely structural.

---

# 🎯 Design Approved

If you approve this design, I will:

1. Provide a **full replacement PythonASTExtractor file**
2. Implement scope stack tracking
3. Add parent_id everywhere required
4. Keep backward compatibility for IDs
5. Keep artifact shape consistent

Clean. Deterministic. Architecturally aligned.

---

