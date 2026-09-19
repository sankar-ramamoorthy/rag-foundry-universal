---
title: "Phase 6 sufficiency and authority: implementation findings"
date: 2026-09-19
type: research-note
status: complete
tags: [phase-6, evidence, sufficiency, provenance]
related:
  - "[Roadmap](/DOCS/audit/07-Roadmap.md)"
  - "[Claude implementation handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md)"
---

# Scope and baseline

User-directed order: bounded sufficiency first (#200, originally item #5),
authority/subject/provenance second (#199, originally item #4), then revisit
#200 with authority-aware checks. The roadmap already reflects this reorder;
use issue numbers because its current list positions are reversed.

Inspected checkout: `65ccd096e3ea525c351ae32d7f60e44c0e701bb2`.
Initial `git status --short` had no changes (Git printed an inaccessible global
ignore-file warning). Findings below describe local code, not independently
verified GitHub issue status or live deployment behavior.

# Findings saved during investigation

- Repository rules: read-only RAG product, service boundaries, HTTP coordination,
  canonical identity `(repo_id, canonical_id)`, existing artifact graph rather
  than per-artifact tables, test-guided implementation. New docs need OKF
  frontmatter and Markdown links. See [guidance](/CLAUDE.md).
- [Roadmap](/DOCS/audit/07-Roadmap.md) records #196/#197/#198 and fast-follows
  #220/#221 shipped. It explicitly authorizes #200 before #199 and excludes a
  general investigator or LLM judge from the first sufficiency version.
- [Structural traversal](/rag_orchestrator/src/retrieval/trace_impact.py)
  provides `resolve_start_symbol`, `traced_path`, `assess_impact`. Resolution
  distinguishes missing/ambiguous/exact starts. TRACE carries per-hop metadata,
  external gaps and node-cap truncation; IMPACT carries candidate bases and
  truncation. Neither is a sufficiency controller.
- Important limit: TRACE reaching `max_depth` simply stops that branch; it does
  not set `truncated`. Do not equate `truncated=False` with complete traversal.
  IMPACT separately traverses each relation type; do not promise arbitrary
  mixed-relation dependency paths without changing and evaluating its semantics.
- [ORIENT](/ingestion_service/src/api/v1/orient.py) serves persisted structural
  inventory with ingestion identity, optional commit SHA, heuristic fields and
  gaps; no vector retrieval or LLM call. Missing generation is 404; old generation
  without ORIENT is 409. Orchestrator exposes a passthrough.
- [DocumentNode](/shared/models/document_node.py) already has source, doc_type,
  ingestion_id, canonical identity and file-level content hash. These are useful
  provenance inputs but are not a source-authority/subject model.
- [Routes](/rag_orchestrator/src/api/v1/routes.py) expose independent ORIENT,
  TRACE, IMPACT and generated RAG paths. A plan must explicitly select the loop's
  API surface; it cannot assume structural modes already feed generated RAG.

## Retrieval and evidence delivery

- [service.py](/rag_orchestrator/src/core/service.py): `hybrid_retrieve`
  resolves a ready generation, scopes vector queries to its ingestion ID, and
  verifies the generation after retrieval. `run_rag` executes retrieval once,
  applies chunk limits and optional reranking, assembles context, finalizes
  evidence survival, builds a manifest, then calls `/generate` once.
- [Evidence tracing](/rag_orchestrator/src/retrieval/evidence_trace.py) exposes
  discovery, graph cap, fetch, chunk limit, reranker and final-context survival.
  It is target-driven instrumentation, not automatic question decomposition.
  Document survival alone does not prove the relevant passage survived.
- [Context adapter](/rag_orchestrator/src/retrieval/agent_adapter.py) produces
  selected whole chunks and a manifest with canonical/document/chunk identities,
  stored ordinal, fetch position, text hash, token estimate and selection reason.
  The manifest currently does not establish role/subject/derivation semantics.
- [ADR-052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md) is accepted.
  The documentation index's stale "proposed" wording was corrected during
  handoff cleanup, along with its outdated Phase 6 "items 1-2 next up" text.
  Its generation and manifest guarantees are foundations, not replacement work.
- [Graph cache](/rag_orchestrator/src/retrieval/codebase_utils.py) checks a
  generation, then `load_graph_for_repo(repo_id)` fetches by repository. Its
  returned graph has no explicit generation envelope in the inspected API.
  Multi-step workflows need a tested request-wide generation fence, including
  graph loading; cache comments alone are not proof of race-free snapshot pinning.
- Current configured TRACE limits are depth 6/nodes 300; IMPACT depth 4/candidates
  300. Routes check the upper depth bound but do not explicitly validate positive
  depth or a relation-type allowlist. New workflow inputs need explicit validation.

## Authority transport and lineage

- [IngestionRequest](/ingestion_service/src/core/models.py) has `commit_sha`,
  parent generation, incremental/config versions and structural summary. Reuse
  this substrate; a new general snapshot abstraction is not a prerequisite.
- [Graph persistence](/ingestion_service/src/core/codebase/codebase_persistence.py)
  has an explicit node-field list and preserves relationship metadata separately.
  Node metadata cannot be assumed to survive just because an extractor emits it.
- [Codebase ingestion](/ingestion_service/src/api/v1/codebase_ingest.py) enriches
  chunk metadata using selected fields. Follow those fields through the actual
  vector API/store, retrieval types, adapter and LLM payload before declaring
  provenance end-to-end. `shared/models/vector_chunk.py` alone is not that proof.
- [Architecture audit](/DOCS/audit/2026-09-07-repository-intelligence-architecture-audit.md)
  explicitly distinguishes origin, role, subject and derivation; rejects one
  universal authority score; and identifies mixed-example/fixture contamination.
  Its older implementation observations must be checked against current code.
- [Constitution](/.specify/memory/constitution.md) clarifies the database boundary:
  ingestion owns graph/document metadata; vector store owns its vector tables.
  This is more precise than the shorthand in CLAUDE.md. Keep orchestration DB-free.

## Investigation limits and next artifact

No runtime implementation, migrations, test runs, live service calls, deployment,
GitHub edits or commits were performed. No claim is made that historical audit
failures still reproduce on a currently deployed corpus. The new
[handoff](/DOCS/proposals/2026-09-19-phase-6-sufficiency-authority-handoff.md)
contains proposed implementation decisions and an explicit verification plan.
The original GitHub issue bodies were not fetched; reconcile them before coding.
