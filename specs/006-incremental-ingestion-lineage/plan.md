# Implementation Plan: Incremental ingestion + repository/file snapshot lineage

**Branch**: `006-incremental-ingestion-lineage` | **Date**: 2026-09-18 | **Spec**: [spec.md](./spec.md)

**Tracking Issue**: #196

**Roadmap Context**: Phase 6 (repository intelligence and incremental ingestion foundation), blue-star priority 1 of 13.

**Input**: Feature specification from `specs/006-incremental-ingestion-lineage/spec.md`

## Summary

Every codebase ingestion re-parses, re-extracts, and re-embeds an
entire repository, and no ingestion records which source commit it
came from. This plan makes re-ingestion cost scale with the size of
the change (FR-004/FR-006/FR-007) and records queryable snapshot
lineage (FR-001/FR-009/FR-010), by extending the existing
`ingestion_id`-as-generation model (ADR-050/051) rather than adding a
new snapshot abstraction. Every file is still parsed and the whole
repository is still resolved fresh every run (FR-002) — only
re-chunking/re-embedding is skipped for files whose content
fingerprint, chunking config, and embedding model all still match a
prior `completed` generation (FR-006).

The central technical finding of this plan (see `research.md` R1):
`CodebaseGraphPersistence.persist_graph` today unconditionally deletes
every `document_nodes` row for a `repo_id` and re-inserts all of them
with freshly generated `document_id` UUIDs, every ingestion.
`vectors.document_id` has `ON DELETE CASCADE` to
`document_nodes.document_id`. Applied unmodified, that behavior
destroys every vector on every ingestion — including ones this feature
intends to reuse — before they could ever be carried forward
(FR-007a/FR-007b). `persist_graph` must change from delete-all-then-
insert-all to an upsert-by-`(repo_id, canonical_id)` model that
preserves `document_id` for canonical IDs whose row survives
unchanged, and re-tags survivors to the new `ingestion_id`. This is the
single riskiest, most load-bearing change in the whole feature.

## Technical Context

**Language/Version**: Python 3.12 (`ingestion_service`, matching its existing `pyproject.toml`)

**Primary Dependencies**: FastAPI, SQLAlchemy 1.4 + `psycopg2`, `GitPython` (already used for `git.Repo.clone_from`), Alembic (migrations) — all existing, no new dependency introduced

**Storage**: PostgreSQL + pgvector, via `ingestion_service`'s existing `document_nodes`/`document_relationships`/`vectors` tables and `ingestion_requests` (per ADR-030/031/FR-011 — no new table)

**Testing**: `pytest` (`ingestion_service/tests`), markers `unit`/`docker`/`integration` per `CLAUDE.md`; FR-012's equivalence check is a new `integration`-marked test against real PostgreSQL, per Constitution Principle VIII (real-Postgres evidence, not mocks alone, for a DB-durability claim of this kind — consistent with how ADR-050/051 were verified)

**Target Platform**: Linux server (Docker Compose), matching existing `ingestion_service` deployment

**Project Type**: Single backend service feature (`ingestion_service`), with one new read surface consumed by `rag_orchestrator`/operators — not a new service

**Performance Goals**: SC-001 — 1-file edit in a ~2,000-file fixture repo re-embeds only that file's artifacts and completes in under 30 seconds

**Constraints**: FR-002 (every file re-parsed every run — no selective parsing), FR-011 (no new per-artifact-type table), FR-007a (document_id stability for reused rows), Constitution Principle I (canonical identity/graph topology equivalence between incremental and full rebuild)

**Scale/Scope**: Single-repository ingestion, one prior `completed` generation diffed against (no deep history) — matches spec's explicit MVP boundary

## Constitution Check

**GATE: Must pass before Phase 0 research and MUST be re-checked after Phase 1 design.**

1. **Canonical identity / deterministic ingestion impact** — PASS. FR-002 keeps whole-repo resolution from fresh IR on every run; canonical IDs (ADR-031) are untouched. `document_id` stability for reused rows (FR-007a) is explicitly *not* a canonical-identity change — Principle I itself excludes `document_id` from the identity invariant it protects.
2. **Service and database boundary impact** — PASS with a disclosed pre-existing gap. All schema/persistence changes stay inside `ingestion_service`'s existing table ownership (ADR-045 boundary). Principle II also requires every ingestion entrypoint to construct its pipeline via `ingestion_service/src/core/pipeline_factory.py::build_pipeline()` — **verified this file does not exist**; `codebase_ingest.py` constructs `IngestionPipeline` directly via a local `_build_pipeline()` helper (tracked, pre-existing, open issue #165). This plan does not fix #165 (out of scope per spec Non-Goals) and does not make it worse — new incremental-ingestion code follows the same existing entrypoint pattern `_background_ingest_repo` already uses, not a new one.
3. **Retrieval/generation architecture / evaluation evidence** — N/A. No retrieval, ranking, or generation behavior changes; confirmed in spec's Evaluation Evidence section.
4. **Model-routing provenance/fallback non-regression** — N/A. No `llm_service`/model-routing code touched.
5. **Embedding-index compatibility / re-embedding implications** — PASS. FR-006 explicitly gates reuse on embedding model/version/dimension matching; any embedding-model change forces re-embedding, consistent with Principle V's model-bound-index rule. No silent swap.
6. **GitHub issue traceability** — PASS. Tracking issue #196 cited in spec and this plan.
7. **ADR/audit references without restatement or conflict** — PASS. See spec's Governing References and the disclosed `DOCS/audit/04-Scalability-Plan.md` WP-S6 conflict (already surfaced there, not re-litigated here).
8. **Test and evaluation obligations** — PASS. FR-012 defines the equivalence-check obligation; Principle VIII's real-Postgres evidence bar applies (see Testing above) — mirrors how ADR-050/051 were verified for the same `document_nodes`/ownership surface.

No EXCEPTION REQUIRED entries. Constitution Exceptions / Complexity Tracking table is empty.

**Post-Phase-1 re-check** (after `research.md`/`data-model.md`/`contracts/`
were written): unchanged from above. The two new columns
(`document_relationships.repo_id`, `document_nodes.content_hash`) and
the `document_id`-preserving upsert (R1) stay inside `ingestion_service`'s
existing table ownership, add no new table (FR-011 honored), and do not
touch canonical ID format, retrieval/generation code, model routing, or
the embedding model. Still PASS across all eight items; no new
EXCEPTION REQUIRED entries.

## Architecture Impact

**Services touched**:
- `ingestion_service` only (`src/core/codebase/codebase_persistence.py`, `src/core/codebase/repo_graph_builder.py`, `src/api/v1/codebase_ingest.py`, `src/core/db_utils.py`, `src/core/models.py`, `shared/models/document_node.py`, `shared/models/document_relationship.py`, a new Alembic migration)

**Database ownership impact**:
- Extends `ingestion_service`-owned tables only (`document_nodes`, `document_relationships`, `ingestion_requests`); no new table (FR-011); no change to `vector_store_service`'s own tables' ownership.

**Public/API contract impact**:
- New request field on the existing codebase-ingest endpoint (`force_full_rebuild`, FR-005a).
- New or extended read endpoint exposing generation-level lineage (FR-010) — see `contracts/`.

**Canonical identity / graph impact**:
- None to canonical ID format (ADR-031 untouched). `document_id` (internal PK, explicitly non-identity per Principle I) gains a new stability guarantee for reused rows only — see `research.md` R1 and `data-model.md`.

**Embedding/index impact**:
- None to the embedding model or vector dimension. Vector *reuse* is new; vector *content* semantics are unchanged (FR-006 guards against stale-config reuse).

**Model-routing impact**:
- None.

**Relevant ADRs**:
- ADR-030 (unified artifact graph), ADR-031 (canonical identity), ADR-036 (deterministic rebuild), ADR-050 (repository lifecycle consistency — generation ownership this feature extends), ADR-051 (generation-aware graph cache — unaffected, continues to key on `ingestion_id`)

**Known conflicts**:
- Pre-existing: `DOCS/audit/04-Scalability-Plan.md` WP-S6 proposed skipping parsing entirely; this plan implements the spec's re-parse-but-skip-embed MVP instead (already disclosed in spec's Governing References).
- Pre-existing: Constitution Principle II's `pipeline_factory.py` requirement vs. current code (#165) — disclosed above, not addressed by this plan.

## Evaluation Plan

**Evaluation required**: No — confirmed N/A above (Constitution Check item 3), matching spec's Evaluation Evidence section.

## Required Non-Regressions

- Full ingestion of a repository with no prior generation MUST continue to behave exactly as today (same graph/vector output) — the upsert-by-`canonical_id` persistence change must be a strict superset of today's delete-all-then-insert-all behavior when there is no prior generation to reuse from (every canonical_id is "new" in that case, so upsert degenerates to plain insert).
- Existing full-rebuild tests (`ingestion_service/tests`) covering `CodebaseGraphPersistence.persist_graph`, ADR-050 lifecycle/generation tests, and ADR-051 cache-generation tests must remain green — the persistence-layer change is additive (a new upsert path invoked when a prior generation exists to diff against), not a rewrite of the no-prior-generation case.
- `GET /v1/repos/{repo_id}/generation` (ADR-051) and the `rag_orchestrator` graph cache's generation-keying must continue to work unmodified — this feature does not change what `ingestion_id` means as a generation identifier, only how a new one's rows get populated.
- Superseded-generation vector cleanup (ADR-050, `delete_by_ingestion_id`) must not delete a reused row's vectors as a side effect (spec Acceptance Scenario 2a) — verified by FR-007b's re-tagging requirement.

## Project Structure

### Documentation (this feature)

```text
specs/006-incremental-ingestion-lineage/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
ingestion_service/
├── src/
│   ├── api/v1/
│   │   └── codebase_ingest.py          # + force_full_rebuild request field,
│   │                                     commit-SHA resolution post-clone,
│   │                                     lineage recorded on completion
│   ├── core/
│   │   ├── models.py                    # IngestionRequest: + commit_sha,
│   │   │                                  parent_generation_id, chunking_config_
│   │   │                                  version, embedding_config_version columns
│   │   ├── db_utils.py                  # + lineage read helper(s) backing FR-010
│   │   └── codebase/
│   │       ├── codebase_persistence.py  # persist_graph: delete-all-insert-all
│   │       │                              -> upsert-by-(repo_id,canonical_id),
│   │       │                              preserving document_id for reused rows
│   │       │                              (R1); repo-scoped relationship
│   │       │                              replace (R2)
│   │       ├── repo_graph_builder.py    # + per-file content fingerprinting,
│   │       │                              changed/unchanged/new/deleted
│   │       │                              classification against prior
│   │       │                              generation's fingerprints
│   │       └── snapshot_diff.py         # NEW: fingerprint comparison /
│   │                                      classification helper (small,
│   │                                      focused module — not a framework)
│   └── api/v1/repos.py                  # + lineage read endpoint (FR-010)
shared/models/
├── document_node.py                      # + content_hash column
│                                           (file-level rows; FR-003)
└── document_relationship.py              # + repo_id column (denormalized;
                                            see research.md R2)
migrations/versions/
└── <new>_incremental_ingestion_lineage.py  # additive columns only, no data
                                              migration required (nullable,
                                              defaults apply only going forward)
```

**Structure Decision**: All changes live inside `ingestion_service` and the
`shared/models` it (and `vector_store_service`, unaffected here) already
share — this is a codebase-ingestion-pipeline feature with no new service
boundary, consistent with Constitution Principle II and `CLAUDE.md`'s
architecture map. `snapshot_diff.py` is a new, narrowly-scoped module
(fingerprint classification only) rather than folding this logic into
the already-large `repo_graph_builder.py`, so it can be unit-tested
independent of a real repo walk.

## Constitution Exceptions / Complexity Tracking

None. No EXCEPTION REQUIRED entries in the Constitution Check above.
