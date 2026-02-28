---

# 📜 ADR-004 — Explicit Document Relationships 
# (No Retrieval Impact)

**Status:** Accepted
**Milestone:** MS3
**Date:** 2026-02-01

---

## Context

As of Milestone 2, the system introduces `DocumentNode` as a first-class persisted entity.
Vector-based retrieval remains **unchanged** and operates exclusively on chunk embeddings.

However, many real-world knowledge domains require **explicit relationships between documents**, such as:

* “explains”
* “depends_on”
* “derived_from”
* “supersedes”

These relationships must be **modeled explicitly** and **persisted**, even if they are not yet used in retrieval.

---

## Decision

We introduce a **DocumentRelationship** table that:

* explicitly links two `DocumentNode` records
* records a typed relationship
* enforces referential integrity via foreign keys
* is **not traversed** during retrieval

This change is **purely structural**.

---

## Consequences

### Positive

* Enables future graph-aware retrieval
* Preserves provenance and explainability
* Prevents retrofitting relationships later (high risk)
* Keeps retrieval deterministic for now

### Neutral

* Slight schema complexity increase
* No runtime impact

### Explicit Non-Consequences

* ❌ No traversal
* ❌ No ranking changes
* ❌ No inference over relationships
* ❌ No graph algorithms

---

## Alternatives Considered

### Implicit relationships via metadata (rejected)

* Not queryable
* Not enforceable
* Not evolvable

### Graph DB (Neo4j, etc.) (rejected)

* Premature
* Operationally heavy
* Not required for current scope

---

## Summary

This ADR introduces **structure without behavior**.

Relationships exist so that future intelligence has a stable foundation.

---
