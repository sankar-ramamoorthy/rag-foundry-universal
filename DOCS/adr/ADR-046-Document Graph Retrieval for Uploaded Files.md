# ADR-046: Document Graph Retrieval for Uploaded Files

**Status:** Accepted
**Date:** 2026-02-26
**Supersedes:** ADR-005 (Relationship-Aware Retrieval Planning, rag-foundry-docgraph)
**Relates to:** ADR-030 (Unified Artifact Graph), ADR-031 (Canonical Identity), ADR-043 (Markdown Section Extraction), ADR-045 (DB access via ingestion_service HTTP API)

---

## Context

ADR-030 defines a Unified Artifact Graph covering both code and documents. In practice,
graph-aware retrieval has only been implemented for code repositories. Uploaded documents
(PDF, text, Markdown) produce flat `DocumentNode` entries with no relationships and are
queried via pure vector search in `simple_service.py`.

This leaves a gap relative to ADR-030's stated goals:

- Code → Document linking: not implemented
- Document graph traversal: not implemented
- Relationship-aware retrieval for documents: not implemented

ADR-005 from the predecessor project (`rag-foundry-docgraph`) proposed
relationship-aware retrieval planning for documents. The implementation was partially
built — `traversal_planner.expand_retrieval_plan()` and `document_relationships` CRUD
exist — but were never wired into the ingestion or retrieval paths.

ADR-043 (Markdown Section Extraction) introduced structured `MARKDOWN_SECTION` nodes
for `.md` files in repositories. MS6-IS3 extends this to uploaded `.md` files, creating
the first document type with persistent graph relationships in the uploaded file path.

---

## Decision

### 1. Uploaded Markdown files get structured graph nodes with relationships

When a `.md` file is uploaded via `POST /v1/ingest/file`:

- One `MARKDOWN_MODULE` node is created for the file
- One `MARKDOWN_SECTION` node is created per heading
- `DEFINES` relationships are persisted to `document_relationships` for each
  parent → child section link
- `repo_id = str(ingestion_id)` — consistent with existing file ingestion convention

This reuses `MarkdownSectionExtractor` from ADR-043 without modification.

### 2. `simple_service.py` adopts relationship-aware retrieval planning

After vector search returns seed chunks, `simple_service.py` will:

1. Extract `canonical_id` from seed chunk metadata
2. Resolve `canonical_id` → `document_id` via ingestion_service graph API
3. Call `expand_retrieval_plan()` using `traversal_planner.py` (already exists)
4. Wire `list_outgoing_relationships` to the ingestion_service HTTP API
5. Populate `expanded_document_ids` in the `RetrievalPlan`
6. Pass expanded plan to `execute_retrieval_plan()` as normal

This completes the ADR-005 intent: `expand_retrieval_plan()` was built but never called.

### 3. Traversal constraints for document retrieval

Consistent with ADR-005's conservative principle:

```python
TraversalConstraints(
    max_depth=1,
    allowed_relation_types={"DEFINES"}
)
```

One-hop DEFINES expansion only. A query landing on a child section expands to its
parent and siblings. No multi-hop, no CALL/IMPORT traversal in the document path.

### 4. Other uploaded file types unchanged

PDF and plain text files continue to produce flat nodes with no relationships.
`DocumentGraphBuilder` (PDF in-memory graph) is not connected to `document_relationships`
and remains unchanged. This is deferred to a future milestone.

---

## Canonical Identity for Uploaded Files

Uploaded `.md` files have no true repo concept. `repo_id = str(ingestion_id)` is used
as the namespace, consistent with existing file ingestion in `pipeline.py`.

Canonical IDs follow the same slug policy as ADR-043:

```
README.md                            → markdown_module
README.md#overview                   → markdown_section (H1)
README.md#overview.installation      → markdown_section (H2)
```

These are deterministic within a single ingestion. Re-ingesting the same file with the
same `ingestion_id` produces identical canonical IDs. Re-ingesting with a new
`ingestion_id` produces a new graph (new `repo_id` namespace).

---

## Implementation

### New pipeline entry point

`IngestionPipeline.run_with_sections()` in `pipeline.py`:

```python
def run_with_sections(
    self,
    *,
    source: str,               # raw markdown text
    ingestion_id: str,
    filename: str,
    doc_type: str = "markdown_module",
) -> None:
```

Internally:
1. Calls `MarkdownSectionExtractor.extract(source)` → section artifacts
2. Creates one `DocumentNode` per artifact via `create_document_node()`
3. Creates `DocumentRelationship` entries for DEFINES links via `create_document_relationship()`
4. Embeds each section's text
5. Persists vectors with `canonical_id` in `source_metadata`

### Routing in `ingest.py`

```python
is_markdown = filename.endswith(".md")

if is_pdf:
    # existing path
elif is_markdown:
    pipeline.run_with_sections(source=text, ingestion_id=..., filename=...)
else:
    # existing flat text path
```

### Retrieval wiring in `simple_service.py`

```python
# After vector search, before LLM call:
from rag_orchestrator.src.retrieval.traversal_planner import (
    expand_retrieval_plan, TraversalConstraints
)

def _list_outgoing(document_id: str) -> List[Dict]:
    # HTTP call to ingestion_service
    url = f"{settings.INGESTION_SERVICE_URL}/v1/graph/docs/{document_id}/relationships"
    r = requests.get(url)
    return r.json().get("relationships", [])

plan = expand_retrieval_plan(
    plan=plan,
    list_outgoing_relationships=_list_outgoing,
    constraints=TraversalConstraints(
        max_depth=1,
        allowed_relation_types={"DEFINES"}
    )
)
```

### New ingestion_service API endpoint

`GET /v1/graph/docs/{document_id}/relationships`

Returns outgoing relationships for a single document:

```json
{
  "relationships": [
    {
      "target_document_id": "486dcf66-...",
      "relation_type": "DEFINES"
    }
  ]
}
```

This is thin — it calls `list_outgoing_relationships()` from existing
`document_relationships.py` CRUD which already exists.

---

## Files to Create / Modify

| File | Action | Issue |
|---|---|---|
| `ingestion_service/src/core/pipeline.py` | Add `run_with_sections()` | MS6-IS3 |
| `ingestion_service/src/api/v1/ingest.py` | Add `.md` branch in `background_ingest_file` | MS6-IS3 |
| `ingestion_service/src/api/v1/graph.py` | Add `GET /graph/docs/{document_id}/relationships` | MS6-IS3 |
| `rag_orchestrator/src/core/simple_service.py` | Wire `expand_retrieval_plan()` after vector search | MS6-IS3 |
| `rag_orchestrator/src/core/config.py` | No change needed | — |

---

## What This Does Not Change

- `service.py` (graph-aware code RAG) — unchanged
- `codebase_ingest.py` — unchanged
- `RepoGraphBuilder` — unchanged
- `DocumentGraphBuilder` (PDF in-memory graph) — unchanged
- `community_detector.py` — still unused, deferred
- Schema — no migrations needed, `document_relationships` table already exists

---

## Relation to ADR-005

ADR-005 proposed relationship-aware retrieval planning with these principles:

| ADR-005 Principle | This ADR |
|---|---|
| Planning, not execution | ✅ `expand_retrieval_plan()` expands the plan only |
| One-hop expansion only | ✅ `max_depth=1` |
| Explicit and bounded | ✅ `allowed_relation_types={"DEFINES"}` |
| Backward-compatible | ✅ docs with no relationships behave identically to before |

ADR-005 is formally superseded. Its intent is fulfilled here within the ADR-030
Unified Artifact Graph architecture.

---

## Relation to ADR-030

ADR-030 states the graph covers documents and code. This ADR activates the document
side for the first time in this project. It does not fulfill all of ADR-030's
cross-artifact goals (Code → Document linking remains future work) but it closes
the most important gap: documents now participate in graph-aware retrieval.

---

## Consequences

### Positive

- Uploaded `.md` files get meaningfully better RAG quality via section context expansion
- ADR-005 intent fulfilled — `traversal_planner.py` is finally used
- ADR-030 document graph goal partially activated
- No schema changes required
- Fully reuses existing infrastructure: extractor, CRUD, traversal planner, graph API

### Negative

- `simple_service.py` adds an HTTP call to ingestion_service per query (one call
  per seed document to fetch outgoing relationships). Acceptable at current scale.
- Uploaded `.md` files now produce more nodes than before (one per section vs one flat).
  This is correct behavior but increases node count.
- PDF and plain text files still produce flat nodes — inconsistent until a future ADR
  addresses those types.

---

## Future Work

- ADR-047: Document graph relationships for PDF files (section/page structure)
- ADR-048: Cross-artifact linking (code → documentation, ADR → code)
- `community_detector.py` — evaluate whether clustering adds value for multi-document queries
- Multi-hop traversal for deeply nested documentation (deferred per ADR-005 principle)

---