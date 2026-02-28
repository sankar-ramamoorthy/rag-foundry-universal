---

# 📐 DESIGN — Milestone 3 (Relationships, Still No Behavior Change)

## Goal

Introduce **explicit, typed document relationships** while keeping:

* ingestion unchanged
* retrieval unchanged
* vector search unchanged

---

## New Entity: `DocumentRelationship`

### Conceptual Model

A relationship is a **directed edge** between two `DocumentNode`s.

```
(from_document) ──[relation_type]──▶ (to_document)
```

---

## Relationship Semantics

Relationships are:

* directed
* typed
* explicit
* immutable once created (initially)

Examples:

| relation_type | Meaning          |
| ------------- | ---------------- |
| explains      | A explains B     |
| derived_from  | A derived from B |
| depends_on    | A depends on B   |
| supersedes    | A replaces B     |

No semantics are enforced yet — types are **opaque strings**.

---

## Database Schema (Proposed)

### `document_relationships`

| Column           | Type      | Notes           |
| ---------------- | --------- | --------------- |
| id               | UUID (PK) | generated       |
| from_document_id | UUID (FK) | source          |
| to_document_id   | UUID (FK) | target          |
| relation_type    | TEXT      | e.g. `explains` |
| metadata         | JSONB     | optional        |
| created_at       | TIMESTAMP | default now     |

Constraints:

* FK → `document_nodes.document_id`
* `(from_document_id, to_document_id, relation_type)` unique

---

## Updated ER Diagram (MS3)

```
+--------------------+
| DOCUMENT_NODES     |
+--------------------+
| document_id (PK)   |
| ingestion_id (FK)  |
| title              |
| text               |
| source_metadata    |
+--------------------+
        ▲        ▲
        |        |
        |        |
+------------------------------+
| DOCUMENT_RELATIONSHIPS       |
+------------------------------+
| id (PK)                      |
| from_document_id (FK)        |
| to_document_id (FK)          |
| relation_type                |
| metadata                     |
| created_at                   |
+------------------------------+
```

---

## ORM Design (Intent)

The ORM will expose:

```python
DocumentNode.outgoing_relationships
DocumentNode.incoming_relationships
```

But:

* no traversal helpers
* no graph logic
* no recursive queries

Just raw access.

---

## CRUD Scope (MS3)

Allowed:

* create relationship
* list relationships for a document
* delete relationship (optional)

Not allowed:

* traversal
* chaining
* ranking
* inference

---

## Retrieval Behavior (Explicitly Unchanged)

Retrieval pipeline remains:

```
Query
 → embedding
   → vector similarity search
     → vector chunks
```

Relationships are **not consulted**.

This must remain true for the entire milestone.

---

## Why This Is Deliberate

Graph-aware retrieval is powerful but dangerous if introduced prematurely.

By separating:

* **structure (MS3)**
* **behavior (MS4+)**

we ensure:

* debuggability
* predictable evolution
* clear rollback boundaries

---

# 📌 MS3 Scope Summary

### Included

✅ Relationship table
✅ ORM model
✅ Alembic migration
✅ Basic CRUD
✅ Documentation

### Excluded

❌ Traversal
❌ Graph algorithms
❌ Retrieval changes
❌ RAG orchestration changes

---

## Naming Convention

Milestone naming:

> **MS3 — Relationships (Structure Only)**

Anything that *uses* relationships belongs to **MS4+**.

---

## Next Logical ADR (Future)

**ADR-005: Graph-Aware Retrieval (Multi-hop, bounded)**
(Not part of MS3)

---

