## DOCS\adr\ADR-043-MarkdownExtractor.md

# 📍 1. **Markdown Section Extractor ADR**

**ADR-XYZ — Markdown Section Extraction into Unified Artifact Graph**

**Status:** Proposed
**Context:**
The repository ingestion system currently extracts structured Python AST artifacts and PDFs, storing them as graph nodes in the Unified Artifact Graph (UAG). Markdown files contain critical documentation and should also be represented as structured artifacts in the graph for RAG retrieval and reasoning.

**Decision:**
Implement `MarkdownSectionExtractor` using **`markdown-it-py`** to parse `.md` files. Each heading in Markdown becomes a `SECTION` artifact in the graph, preserving hierarchy, text content, and metadata.

**Rationale:**

* Headings in Markdown define a natural hierarchy, analogous to classes/functions in Python.
* Storing sections as graph nodes ensures semantic search coverage and enables linking documentation to code artifacts.
* Consistent canonical IDs ensure deterministic referencing and potential future indexing in a symbol table.

**Consequences:**

* Adds `SECTION` artifact type to UAG.
* Section nodes store text for embedding.
* Parent-child relationships mirror heading nesting levels.
* Graph integration allows cross-linking documentation and code symbols.

**Artifact Node Example:**

```jsonc
{
  "artifact_type": "SECTION",
  "id": "README.md#installation.docker_setup",
  "name": "Docker Setup",
  "parent_id": "README.md#installation",
  "relative_path": "README.md",
  "metadata": {
    "level": 2,
    "lineno": 24
  },
  "text": "Full section text exactly as in source."
}
```

---

# 📍 2. **Canonical Slug Policy Spec**

**Objective:**
Ensure deterministic, collision-free canonical IDs for Markdown headings.

**Rules:**

1. **Normalization:**

   * Convert to lowercase
   * Strip leading/trailing whitespace
   * Replace spaces and punctuation with underscores

2. **Allowed Characters:**

   * Letters, digits, underscores only

3. **Deduplication:**

   * For duplicate headings in the same file, append numeric suffix: `overview_2`, `overview_3`, etc.

4. **Canonical ID Construction:**

   * `<relative_path>#<slug>` for top-level sections
   * `<relative_path>#<parent_slug>.<slug>` for nested sections

**Example Slugs:**

| Heading              | Slug         |
| -------------------- | ------------ |
| Installation         | installation |
| Docker Setup         | docker_setup |
| API: Usage           | api_usage    |
| Duplicate `Overview` | overview_2   |

---

