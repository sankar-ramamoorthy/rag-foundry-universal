 ## docs/architecture/codebase-ingestion-diagram.md:

# Codebase Ingestion Pipeline — ASCII Diagram

**Phases:** Extraction → Resolution → Persistence → Rebuild Safe Graph



# Codebase Ingestion Pipeline — ASCII Diagram

**Phases:** Extraction → Resolution → Persistence → Rebuild Safe Graph

```

+---------------------+
|     Repository      |
|  (Source Files, ADRs)
+---------+-----------+
|
v
+---------------------+

| Extraction Phase        |
| ----------------------- |
| - File discovery        |
| - Parsing (AST, MD)     |
| - Canonical ID gen      |
| +---------+-----------+ |

```
      |
      v
```

+---------------------+

| Resolution Phase          |
| ------------------------- |
| - Symbol resolution       |
| - Relationship derivation |
| - Metadata validation     |
| +---------+-----------+   |

```
      |
      v
```

+---------------------+

| Persistence Phase             |
| ----------------------------- |
| - document_nodes              |
| - document_relationships      |
| - Apply indexes & constraints |
| +---------+-----------+       |

```
      |
      v
```

+---------------------+

| Rebuild-Safe Graph         |
| -------------------------- |
| - Deterministic IDs        |
| - Repo isolation           |
| - Cross-artifact traversal |
| +---------------------+    |

```

**Notes:**

* `Extraction Phase` produces structured artifacts (nodes) with canonical IDs.  
* `Resolution Phase` computes relationships (edges) and validates references.  
* `Persistence Phase` stores everything in PostgreSQL with constraints and indexes.  
* Full pipeline is idempotent: running it multiple times produces identical graph state.  

---

