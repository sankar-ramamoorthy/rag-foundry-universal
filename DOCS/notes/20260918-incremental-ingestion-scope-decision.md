# Decision: #196 re-scoped as snapshot-lineage-first; MVP re-parses unchanged files but skips re-embedding them (2026-09-18)

Status: decided, not yet implemented. Scopes #196 before any code is
written; nothing here changes running behavior by itself.

## Decision

Two decisions, made together:

1. **Snapshot lineage is the foundation, incremental processing is the
   optimization built on top of it** — not two parallel efforts. #196's
   acceptance bar is that an incremental run produces the same graph as
   a clean full rebuild of the same commit; lineage (what commit, what
   generation, what file fingerprints) is what makes that claim
   checkable at all, so it has to exist first, not as an afterthought.

2. **For the first version, "incremental" means incremental *expensive*
   work, not incremental parsing.** Every ingestion — full or
   incremental — re-walks and re-parses every supported file into fresh
   IR and re-runs whole-repo symbol resolution from that fresh IR. What
   an incremental run skips is re-chunking and re-embedding files whose
   content fingerprint (and the chunking/embedding config that produced
   their existing vectors) didn't change; those files' existing
   `document_nodes`/`vector_chunks` rows are carried forward under the
   new `ingestion_id` instead of being regenerated.

No new "snapshot" table or abstraction: `ingestion_id` already acts as
generation identity (ADR-050/051), and `ingestion_requests` already has
a `repo_id` column and an `ingestion_metadata` JSON column. Snapshot
lineage rides on that existing substrate — `ingestion_metadata` gains
`source_commit_sha`, `parent_generation_id`, and file-fingerprint data;
nothing about `document_nodes`' one-generation-per-repo_id ownership
model, the generation-status read path, or the LRU graph cache changes.

## Why not "skip parse entirely" (the issue's original proposed direction)

`RepoGraphBuilder.build()` extracts every file into an in-memory
`ExtractionResult` list, then makes one `GraphAssembler.assemble()` call
that builds a whole-repo symbol table and resolves imports/calls/
inheritance against it globally (`ingestion_service/src/core/codebase/
graph_assembler.py`). Checked what the resolver actually consumes
(`ingestion_service/src/core/codebase/ir.py`) against what gets
persisted: `SymbolRecord`/`ImportRecord`/`CallSite` carry raw,
*unresolved* data (`callee_name`, `raw_module`, docstrings, spans) that
`document_nodes`/`document_relationships` do not retain — persisted
rows only hold the *resolved outcome* (a CALL edge already points at
its resolved target, or at a synthetic `EXTERNAL_*` node if resolution
failed).

Skipping parsing for unchanged files therefore requires a second,
durable, raw-IR persistence layer to feed the resolver without
re-reading those files — and that layer would need an `extractor_version`
invalidation scheme of its own: an extractor upgrade (tree-sitter
version bump, a bug fix in symbol extraction, a new language feature
handled) must not leave old files represented under stale extraction
semantics while changed files use new semantics. Re-parsing on every
ingestion sidesteps that whole problem for free — extractor upgrades
just apply on the next ingestion, incremental or not, with no separate
invalidation mechanism to build or get wrong.

Parsing is local CPU with no network/LLM cost; embedding is the
dominant cost (network/GPU calls to the embedder). Skipping the
embedding step for unchanged files captures the large majority of the
performance win #196 is chasing, without the lossy-reconstruction risk
or the extra invalidation surface of persisting raw IR. Treat
raw-IR persistence as a later escalation, only if profiling on a real
large repo ever shows parsing itself — not embedding — is the
bottleneck.

## Vector/chunk reuse gate

Reusing a file's existing chunks/vectors for an unchanged file requires
**all** of:
- content fingerprint (hash of raw file bytes) unchanged, AND
- chunking config/version unchanged, AND
- embedding model/version/dimension unchanged.

Content-hash match alone is not sufficient — a chunker or embedder
change must force re-embedding even for byte-identical files, or a
config/model upgrade would silently leave stale vectors being served
under semantics they were never actually produced by.

## MVP acceptance target

> Same checkout + same extraction/chunk/embed configuration ⇒
> incremental ingestion produces a graph and retrieval corpus
> equivalent to a clean full ingestion of the same commit, while only
> embedding changed/new content.

Per-file fingerprint storage shape (JSON blob on `ingestion_metadata`
vs. a more structured representation) is explicitly not decided by this
note — real design work, tracked in the #196 spec.
