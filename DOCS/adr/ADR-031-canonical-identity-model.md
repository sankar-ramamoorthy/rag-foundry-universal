## docs/adr/ADR-031-canonical-identity-model.md


---

# ADR-031: Canonical Identity Model for Artifacts

**Status:** Accepted
**Date:** 2026-02-12
**Depends on:** ADR-030 (Unified Artifact Graph with Repository Isolation)
**Supersedes:** None

---

## Context

The system represents documents, code artifacts, and architectural records within a unified artifact graph.

To preserve:

* Deterministic ingestion
* Rebuild-safe indexing
* Provenance traceability
* Cross-artifact traversal
* Multi-repository support

We must define a canonical identity model that:

* Does not depend on database-generated values
* Does not depend on ingestion order
* Does not depend on runtime state
* Remains stable across rebuilds

Identity must be a function of structure — not execution.

---

## Decision

Artifact identity will be:

```
(repo_id, canonical_id)
```

Where:

* `repo_id` is a UUID identifying a repository boundary
* `canonical_id` is a deterministic string derived from structural location

Primary uniqueness constraint:

```
UNIQUE (repo_id, canonical_id)
```

No artifact identity will be generated via UUIDs.

---

## Canonical ID Format

### 1. File-Level Artifacts (Modules, Documents)

```
<relative_path>
```

Example:

```
payments/stripe.py
docs/architecture/overview.md
```

Rules:

* Path must be relative to repository root
* Use forward slashes
* No leading slash
* Case sensitivity preserved as-is
* No normalization beyond path cleaning

---

### 2. Symbol-Level Artifacts (Classes, Functions, Methods)

```
<relative_path>#<symbol_path>
```

Examples:

```
payments/stripe.py#StripeClient
payments/stripe.py#StripeClient.charge
auth.py#login_user
```

Where:

* `#` separates file scope from symbol scope
* `symbol_path` is dot-separated
* Class methods use `ClassName.method`
* Nested classes use full dot path
* No whitespace
* No parameter signatures included

---

## What Is Explicitly Excluded From Identity

Identity must NOT include:

* Function parameters
* Line numbers
* Column numbers
* AST node IDs
* Hashes
* Timestamps
* Runtime resolution state
* Import resolution outcomes

Reason:

These change across refactors and rebuilds.

Identity must represent structural location, not implementation detail.

---

## Repository Isolation

Without repository scoping, two repositories containing:

```
auth.py#login
```

would collide.

Therefore:

* `repo_id` is mandatory
* All queries must include `repo_id`
* All rebuild operations delete by `repo_id`
* Cross-repo traversal is not allowed unless explicitly modeled

---

## Determinism Requirements

For any given repository state:

* Running ingestion multiple times must produce identical `(repo_id, canonical_id)` sets.
* Relationship edges must reference only canonical IDs.
* Reordering files must not change IDs.
* Rebuilding after full deletion must reproduce identical graph structure.

If these properties fail, the ingestion implementation is incorrect.

---

## Relationship Identity

Relationships are defined by:

```
(repo_id, source_id, target_id, relationship_type)
```

Relationships are deterministic functions of extracted structure.

Relationship identity must not include:

* Confidence score
* Resolution attempt metadata
* Traversal depth
* Query-time enrichment

Confidence is metadata, not identity.

---

## Why Not UUIDs?

UUID-based identity was rejected because:

* UUIDs break rebuild determinism
* UUIDs require stateful mapping
* UUIDs obscure structural meaning
* UUIDs prevent traceability outside the database
* UUIDs complicate debugging

Deterministic IDs:

* Are human-readable
* Are reconstructable
* Support external referencing
* Align with code structure naturally

---

## Why Not Content Hashes?

Example rejected identity:

```
hash(file_contents + symbol_name)
```

Rejected because:

* Minor refactors break identity
* Whitespace changes invalidate identity
* Reformatting tools cause artificial churn
* Symbol relocation becomes destructive

Identity should survive internal modification unless structural location changes.

---

## Identity Stability Rules

### 1. Refactoring Behavior

| Change                 | Identity Impact  |
| ---------------------- | ---------------- |
| Modify method body     | No change        |
| Rename method          | Identity changes |
| Move class to new file | Identity changes |
| Reorder methods        | No change        |
| Add parameters         | No change        |

This is intentional.

Identity represents location + symbol path.

---

### 2. File Renames

If a file is renamed:

* All artifact IDs in that file change.
* This is acceptable and expected.
* Historical tracking is not handled at ingestion layer.

Version-aware diff tracking is a future concern.

---

## Tradeoffs

### 1. Renames Cause Identity Changes

Accepted.

Identity tracks structure, not logical equivalence.

---

### 2. No Cross-Version Continuity

Current model does not preserve artifact lineage across commits.

Accepted for initial scope.

Future extension may introduce version dimension.

---

### 3. Long String IDs

Canonical IDs are longer than UUIDs.

Accepted due to:

* Debuggability
* Traceability
* Determinism
* Human inspection benefit

---

## Invariants

The following must always hold:

1. Identity must be reproducible from source alone.
2. Identity must not depend on database state.
3. Identity must not depend on ingestion order.
4. Identity must not depend on LLM interpretation.
5. Identity must not require stored mapping tables.
6. Identity must remain stable across rebuilds.

Violation of these invariants is considered a design defect.

---

## Consequences

### Positive

* Deterministic rebuilds
* Clear debugging
* Human-readable graph
* Clean cross-artifact linking
* Repository-safe multi-tenancy

### Negative

* Identity changes on file relocation
* No implicit version tracking
* Longer key strings
* Requires disciplined repo scoping

These tradeoffs are acceptable.

---

## Future Considerations

Possible future extensions:

* Add `version_id` to support historical graph states
* Add soft-alias table for renamed symbols
* Introduce cross-repo linking layer
* Add commit-aware lineage modeling

None are required for current milestone scope.

---

## Final Position

Artifact identity is defined as:

```
(repo_id, canonical_id)
```

Canonical IDs are deterministic structural paths derived from source.

Identity is immutable, reproducible, and rebuild-safe.

This model is foundational to the integrity of the Unified Artifact Graph.

---

# Why ADR-031 Is Critical

ADR-030 defines structure.

ADR-031 defines truth.

If someone proposes:

* Adding UUIDs
* Adding hash-based IDs
* Generating synthetic IDs during ingestion
* Storing AST node references as identity



This is the mathematical core.

---
