---

## 📘 ADR-005: Vector Store Implementation Without ORM

### Status

**Accepted**

### Context

The ingestion service requires a reliable, performant vector store backed by PostgreSQL + pgvector.

The initial implementation attempted to use **SQLAlchemy 1.4 ORM** for:

* session management
* vector persistence
* similarity search using `pgvector` operators

During development, this approach caused persistent static-typing and tooling issues:

* Pyright/Pylance reporting `Object of type "None" cannot be called`
* ORM method resolution failing for pgvector operators
* Type stubs for pgvector incomplete or incompatible
* SQLAlchemy 1.4 session typing inconsistencies
* Excessive `type: ignore` required in core logic

Despite multiple refactors, these issues:

* obscured real bugs
* slowed development
* increased cognitive load
* reduced confidence in correctness

---

### Decision

We will **not use SQLAlchemy ORM** for the vector store implementation.

Instead, the vector store will:

* Use **PostgreSQL + pgvector directly**
* Use **psycopg / psycopg2** (or async equivalent) for SQL execution
* Keep SQLAlchemy **only** for:

  * schema migrations (Alembic)
  * non-vector relational models (ingestion metadata, audit tables)

The vector store remains behind the `VectorStore` interface, preserving architectural isolation.

---

### Rationale

1. **pgvector is not ORM-friendly**

   * Vector operators (`<->`, `<=>`, `<#>`) are SQL-first
   * ORM abstractions add little value and significant friction

2. **Tooling reliability matters**

   * Static typing errors blocked progress despite correct runtime behavior
   * Core ingestion code should be boring and obvious

3. **Performance & clarity**

   * Raw SQL makes vector queries explicit
   * Easier to tune indexes and query plans

4. **Isolation via interface**

   * `VectorStore` already abstracts persistence
   * No API or pipeline changes required

---

### Consequences

**Positive**

* Simpler, clearer vector code
* No ORM-pgvector impedance mismatch
* Fewer `type: ignore` annotations
* Easier debugging and testing

**Negative**

* Slightly more SQL to maintain
* Requires explicit connection handling
* Two persistence styles in the codebase (acceptable tradeoff)

---

### Alternatives Considered

| Option                    | Outcome                                              |
| ------------------------- | ---------------------------------------------------- |
| SQLAlchemy 2.0            | Rejected (broader migration risk)                    |
| Supabase                  | Deferred (platform decision, not ingestion-specific) |
| ORM wrappers for pgvector | Rejected (immature tooling)                          |

---
