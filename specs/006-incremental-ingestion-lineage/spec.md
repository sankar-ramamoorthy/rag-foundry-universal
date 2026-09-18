# Feature Specification: Incremental ingestion + repository/file snapshot lineage

**Feature Branch**: `006-incremental-ingestion-lineage`

**Created**: 2026-09-18

**Status**: Draft

**Tracking Issue**: #196

**Roadmap Context**: Phase 6 (repository intelligence and incremental ingestion foundation), blue-star priority 1 of 13. Formerly WP-S6 (`DOCS/audit/04-Scalability-Plan.md`), never picked up for implementation until now.

**Input**: User description: re-scope #196 as snapshot-lineage-first, then incremental processing on top of it; re-parse unchanged files every run but skip re-embedding them; no new snapshot abstraction, ride on the existing `ingestion_id`-as-generation substrate (ADR-050/051).

## Clarifications

### Session 2026-09-18

- Q: How should the incremental-vs-full equivalence check (FR-012) actually run — only as a test-suite check against a fixture repo, or also as a recurring production job? → A: Test-suite only. FR-012 equivalence is verified in automated CI using a fixture repository and scripted add/change/delete scenarios; no recurring production full-rebuild verification job is required in this feature.
- Q: Should this feature include an explicit way to force a full rebuild even when a valid prior completed generation exists? → A: Yes. A `force_full_rebuild=true` request option bypasses reuse and performs a normal full rebuild, while still creating a new generation with the same lineage metadata (source commit SHA, ingestion timestamp, and parent-generation linkage) as any other generation.
- Q: What concrete, measurable target should SC-001 use for the "cost scales with change size, not repo size" performance claim? → A: Concrete target — in a ~2,000-file fixture repository, editing 1 file triggers re-embedding of only that file's artifacts, completing in under 30 seconds.
- (Not a formal Q&A, raised after the clarification session by design review) Vector/node reuse across generations requires more than "leave the row alone": `vectors.document_id` has `ON DELETE CASCADE` to `document_nodes.document_id`, and the existing full-rebuild persistence path deletes and re-inserts every `document_nodes` row (with fresh `document_id`s) on every ingestion. Reuse is only physically possible if `document_id` stability for unchanged files, and re-tagging reused rows to the new `ingestion_id`, are both explicit requirements — added as FR-007a/FR-007b.

## Scenarios & Testing *(mandatory)*

### User Story 1 - Re-ingest a mostly-unchanged repository fast (Priority: P1)

An operator re-ingests a repository after a small change (a handful of
files edited, added, or removed out of a much larger repository).
Today this fully re-parses, re-extracts, and re-embeds the entire
repository regardless of how much actually changed. The operator needs
the cost of a re-ingestion to scale with the size of the change, not
the size of the repository — so that keeping a large, actively-changing
repository's index current stops being prohibitively expensive.

**Why this priority**: This is the entire performance premise of the
feature and the roadmap's stated goal ("nightly re-ingest of a 1M-LOC
monorepo touches only changed files"). Without it, nothing else in this
spec has a reason to exist.

**Independent Test**: Ingest a fixture repository, edit N files out of
M, re-ingest, and measure that embedding/network work scales with N,
not M, while the resulting graph and retrieval corpus are indistinguishable
from a clean full ingestion of the same commit (see Success Criteria).

**Acceptance Scenarios**:

1. **Given** a repository already ingested at commit A, **When** it is
   re-ingested at commit B where only a small subset of files changed
   between A and B, **Then** only those changed/added files are
   re-chunked and re-embedded; unchanged files' existing chunks/vectors
   are carried forward into the new generation unchanged.
2. **Given** a repository re-ingested this way, **When** its resulting
   graph, chunk/vector membership, and retrieval behavior are compared
   against a clean full ingestion of the same commit B, **Then** they
   are equivalent (see Success Criteria's equivalence check).
2a. **Given** an unchanged file's vectors were carried forward into a
    new generation, **When** superseded-generation cleanup (ADR-050)
    subsequently removes the prior generation's vectors, **Then** the
    carried-forward vectors are unaffected — they are gone only if the
    new generation's own vectors are, never as a side effect of
    cleaning up the generation they were carried forward from.
3. **Given** a repository whose previous ingestion attempt for the same
   `repo_id` did not complete successfully (interrupted, failed,
   or still running), **When** a new ingestion is requested, **Then**
   it falls back to a full rebuild rather than diffing against
   inconsistent prior state.
4. **Given** a repository with a valid prior `completed` generation,
   **When** a new ingestion is requested with `force_full_rebuild=true`,
   **Then** every file is re-chunked and re-embedded regardless of
   fingerprint match, and the resulting generation still records source
   commit SHA, ingestion timestamp, and parent-generation linkage like
   any other generation.

---

### User Story 2 - Know exactly which source snapshot a corpus/generation represents (Priority: P1)

An operator or evaluator needs to know, for any given repository's
currently-served state, exactly which commit it was ingested from and
when — both to reason about staleness, and to avoid the specific
failure mode already observed in production: an evaluation or quality
conclusion silently invalidated because the corpus being queried and
the corpus that was actually evaluated had quietly drifted apart.

**Why this priority**: This is a correctness/provenance concern, not
just a convenience — it's equally load-bearing as User Story 1 and is
a precondition for User Story 1's equivalence check to mean anything
(you cannot prove "incremental equals full rebuild of the same commit"
without first being able to say, unambiguously, what commit either run
targeted).

**Independent Test**: After any ingestion (full or incremental), query
an endpoint and get back the repository's current commit SHA,
ingestion timestamp, and — for an incremental run — which prior
generation it was built from.

**Acceptance Scenarios**:

1. **Given** a repository ingestion (full or incremental) has
   completed, **When** its lineage is queried, **Then** the response
   includes the resolved source commit SHA and the ingestion timestamp.
2. **Given** an incremental ingestion, **When** its lineage is queried,
   **Then** the response also identifies the prior generation it was
   built from.

---

### User Story 3 - Deletions are fully reflected, never orphaned (Priority: P2)

When files are removed from a repository between snapshots, an
operator needs those files' graph nodes, relationships, and vectors to
be fully removed from the new generation — not silently left behind as
dead evidence that can still surface in retrieval or traversal.

**Why this priority**: A partially-correct incremental implementation
that handles adds/changes but leaks deletes is worse than no
incremental implementation at all, because it produces a graph that
looks complete but silently diverges from the real repository state —
exactly the kind of drift User Story 2 exists to catch, but this would
be causing it, not detecting it.

**Independent Test**: Ingest a fixture repository, delete a file that
had graph nodes/relationships/vectors, re-ingest, and confirm no rows
referencing that file's canonical IDs remain in the new generation.

**Acceptance Scenarios**:

1. **Given** a file present in the previous snapshot is absent from the
   current checkout, **When** incremental ingestion completes,
   **Then** no graph nodes, relationships, or vectors for that file's
   canonical IDs exist in the new generation.
2. **Given** a file was deleted and another, unrelated file references
   a symbol that file used to define, **When** incremental ingestion
   completes, **Then** that reference resolves the same way a full
   rebuild would (e.g. to an external/unresolved node), not to stale
   graph state.

---

### Edge Cases

- What happens when a file changes only in whitespace/formatting but
  its content fingerprint changes anyway (SHA-256 has no semantic
  awareness)? It is treated as changed and re-embedded — accepted,
  not a bug; see Assumptions.
- What happens when the chunking configuration or embedding
  model/version changes between two ingestions, even though no source
  files changed? Every file's existing vectors become ineligible for
  reuse and must be re-embedded — the reuse gate checks configuration
  identity, not just content fingerprint identity (see FR-006).
- What happens when an extractor is added or changed for a language
  between two ingestions (e.g. a bug fix, or new-language support)?
  Every file is re-parsed every run regardless of content fingerprint
  (see FR-002), so an extractor change takes effect on the very next
  ingestion — incremental or full — with no separate invalidation
  step required.
- What happens when the previous generation for a `repo_id` is still
  `building` (a prior ingestion attempt is in flight) when a new
  ingestion is requested? The existing repo-scope advisory lock
  (ADR-050) already serializes this — a new ingestion cannot start
  concurrently with one still running for the same `repo_id`.
- What happens when the previous generation for a `repo_id` exists but
  its status is `failed`, not `completed`? Fall back to a full
  rebuild rather than diffing against a possibly-inconsistent prior
  state (Acceptance Scenario 3 above).
- What happens on the very first ingestion of a repository (no prior
  generation to diff against)? It is always a full ingestion by
  definition — there is nothing to reuse.

## Non-Goals

- **Selective parsing.** Every file is re-parsed and re-extracted on
  every ingestion, incremental or full; only re-chunking/re-embedding
  is skipped for unchanged, reusable files. See
  `DOCS/notes/20260918-incremental-ingestion-scope-decision.md` for why
  this was chosen over persisting raw unresolved IR to skip parsing
  entirely.
- **A general snapshot/version-history browsing feature.** This spec
  records enough lineage to identify the current generation's source
  commit and its immediate parent generation. It does not build
  history browsing, retention policies, or "what changed since last
  week" query support beyond that single-parent link (the roadmap's
  stated future direction for a richer history feature is explicitly
  out of scope here).
- **Non-git sources.** Local-path ingestion without a git repository
  behind it has no commit SHA to resolve; it is out of scope for the
  commit-identity half of this feature (existing local-path ingestion
  behavior is unaffected, but it cannot participate in the equivalence
  guarantee tied to a specific commit).
- **Branch/worktree awareness, webhook-driven auto-updates.** Deferred;
  not part of this feature.
- **Durable/distributed job execution reliability.** Tracked
  separately (blue-star tranche issue for durable ingestion execution)
  — this spec is about *what* gets re-processed on a re-ingestion
  request, not *how reliably* that request's job runs to completion.
- **A general source-authority/provenance model** (origin, role,
  subject, derivation, snapshot as a unified concept beyond ingestion
  lineage) — tracked separately (#199). This spec's lineage model is
  narrower: source commit + fingerprints + parent generation, nothing
  more.
- **Superseding #180 by fiat.** This spec's lineage model is intended
  to satisfy #180's narrower ask (pinned git ref + resolved SHA +
  config fingerprint), but #180 is closed only once this ships and is
  verified against its acceptance criteria, not assumed subsumed in
  advance.

## Governing References

- Constitution: `.specify/memory/constitution.md`
- ADRs: `DOCS/adr/ADR-030-unified-artifact-graph.md` (repository
  scoping, two-table invariant), `DOCS/adr/ADR-031-canonical-identity-model.md`
  (canonical ID stability — file fingerprints are metadata, never
  identity), `DOCS/adr/ADR-036-deterministic-rebuild.md` (the
  equivalence guarantee this feature must uphold), `DOCS/adr/ADR-050-repository-lifecycle-consistency.md`
  (generation ownership model this feature builds on),
  `DOCS/adr/ADR-051-generation-aware-graph-cache.md` (generation
  identity as already consumed by the query path)
- Audit/roadmap: `DOCS/audit/04-Scalability-Plan.md` (WP-S6, prior art
  only — re-scoped by this spec, not restated), `DOCS/audit/07-Roadmap.md`
  Phase 6
- Decision record: `DOCS/notes/20260918-incremental-ingestion-scope-decision.md`
  (why re-parse-but-skip-embed was chosen for this spec's MVP boundary)
- Tracking issue: #196
- Related, not duplicated: #160 (bounded ingestion memory — adjacent
  ingestion-pipeline scalability work), #180 (ingestion source-revision
  provenance — narrower ask this spec's lineage model should satisfy)

**Known conflicts**: `DOCS/audit/04-Scalability-Plan.md`'s WP-S6
section proposes "unchanged files: skip parse entirely" as its
direction. This spec deliberately departs from that for its MVP (see
Non-Goals and the linked decision record) in favor of re-parsing every
file but only re-embedding changed ones. The audit doc has not been
updated to reflect this; treat this spec, not the audit doc, as
authoritative for MVP scope once accepted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST resolve and record the source commit SHA
  for any git-backed ingestion, at ingestion time.
- **FR-002**: The system MUST re-parse and re-extract every
  extractor-supported file on every ingestion (full or incremental),
  and MUST re-run whole-repository symbol/import/call/inheritance
  resolution from that freshly extracted data on every ingestion — no
  file's extracted structure is reused from a prior generation without
  being freshly re-derived this run.
- **FR-003**: The system MUST compute and record a per-file content
  fingerprint (SHA-256 of raw file bytes) for every file in a given
  ingestion.
- **FR-004**: For a re-ingestion of a repository with an existing
  `completed` prior generation, the system MUST classify every file in
  the current checkout as unchanged, changed, new, or deleted relative
  to that prior generation's recorded fingerprints.
- **FR-005**: For a re-ingestion of a repository whose prior generation
  for that `repo_id` is not `completed` (still building, or failed),
  the system MUST perform a full ingestion rather than an incremental
  one.
- **FR-005a**: The system MUST provide a request-level option
  (`force_full_rebuild`) that, when set, performs a full ingestion —
  bypassing FR-004's reuse classification entirely, as if no prior
  generation existed — regardless of whether a valid prior `completed`
  generation exists. A forced full rebuild MUST still record the same
  lineage metadata (FR-009) as any other generation, including its
  parent-generation linkage, purely as a recovery mechanism for
  suspected drift or a corrupted fingerprint record — not as a way to
  opt out of lineage tracking.
- **FR-006**: The system MUST re-chunk and re-embed a file's content
  unless all of the following hold: the file's content fingerprint is
  unchanged from the prior generation, the chunking configuration is
  unchanged, and the embedding model/version/dimension is unchanged.
  A match on content fingerprint alone MUST NOT be treated as
  sufficient grounds for reuse.
- **FR-007**: For files classified as unchanged and eligible for reuse
  under FR-006, the system MUST carry their existing graph nodes and
  vector chunks forward into the new generation without re-embedding
  them.
- **FR-007a**: A reused file's `document_id` (the internal database
  primary key backing its graph node) MUST remain stable across the
  generation transition — verified against current code: `vectors.document_id`
  has an `ON DELETE CASCADE` foreign key to `document_nodes.document_id`,
  and the existing full-rebuild persistence path deletes every
  `document_nodes` row for a `repo_id` and re-inserts all of them with
  freshly generated `document_id`s on every ingestion. Applied
  unmodified to an incremental ingestion, that behavior would cascade-
  delete every vector — including ones this feature intends to reuse —
  the moment the new generation's nodes are persisted, before they
  could ever be carried forward. This is a correctness-blocking
  constraint on the persistence design, not an implementation nicety:
  reusing a file's vectors is only possible if its `document_id`
  survives the generation transition unchanged. (`document_id` is
  explicitly not part of canonical identity per ADR-031/the project
  constitution's Principle I, so guaranteeing its stability for reused
  rows does not conflict with either — it is a new guarantee, not a
  changed one.)
- **FR-007b**: A reused file's graph node and vector chunk rows MUST be
  re-tagged to the new generation's `ingestion_id` (both
  `document_nodes.ingestion_id` and `vectors.ingestion_id`) as part of
  publishing the new generation, not left recorded under the prior
  generation's `ingestion_id`. Verified against current code:
  superseded-generation cleanup (ADR-050) deletes a prior generation's
  vectors by `ingestion_id` (`delete_by_ingestion_id`) once a new
  generation completes — a reused row left tagged with the old
  `ingestion_id` would be destroyed by that same cleanup it was
  supposed to survive.
- **FR-008**: For files classified as deleted, the system MUST ensure
  no graph nodes, relationships, or vectors referencing that file's
  canonical IDs exist in the new generation.
- **FR-009**: The system MUST record, per completed ingestion, the
  resolved source commit SHA, the ingestion timestamp, and — for an
  incremental ingestion — the identifier of the prior generation it was
  built from.
- **FR-010**: The system MUST expose recorded lineage (commit SHA,
  ingestion timestamp, parent generation, full-vs-incremental) via an
  existing or new read endpoint.
- **FR-011**: The system MUST NOT introduce a new per-artifact-type
  table for lineage or fingerprint storage; lineage/fingerprint data
  MUST be represented as an extension of the existing generation
  (`ingestion_requests`) and artifact (`document_nodes`) substrate,
  consistent with the project's two-table invariant for artifact
  storage.
- **FR-012**: The system MUST provide an automated equivalence check,
  run in the test suite (CI) against a fixture repository under
  scripted add/change/delete scenarios, that proves an incremental
  ingestion's resulting graph, vector/chunk membership, and recorded
  lineage are equivalent to a clean full ingestion of the same target
  commit, under matching extraction/chunking/embedding configuration.
  A recurring production verification job is explicitly out of scope
  for this feature (see Non-Goals) — durable/scheduled job
  infrastructure does not yet exist and is tracked separately.

### Key Entities *(include if feature involves data)*

- **Generation** (existing concept, `ingestion_id`): one ingestion
  attempt's worth of state for a `repo_id`. This feature extends what
  a generation records (source commit, parent generation, per-file
  fingerprints) but does not change its existing ownership/servability
  semantics (ADR-050/051).
- **File fingerprint**: a per-file, per-generation record of a file's
  content hash, associated chunking configuration, and embedding
  model/version — the basis for the reuse decision in FR-006. Not
  part of any artifact's canonical identity (ADR-031) — purely
  change-detection metadata.
- **Snapshot lineage**: the record, per generation, of its source
  commit SHA, ingestion timestamp, and (for incremental generations)
  parent generation — what FR-009/FR-010 expose.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a fixture repository of approximately 2,000 files,
  editing 1 file and re-ingesting triggers re-embedding of only that
  file's artifacts (not the repository's other ~1,999 files), and
  completes in under 30 seconds.
- **SC-002**: For a fixed target commit and fixed
  extraction/chunking/embedding configuration, an incremental
  ingestion's resulting graph structure, vector/chunk membership, and
  recorded lineage are indistinguishable from a clean full ingestion of
  that same commit, verified by an automated check (FR-012).
- **SC-003**: After a re-ingestion that deletes files, zero graph or
  vector rows referencing those files' canonical IDs remain queryable
  in the new generation.
- **SC-004**: For any completed ingestion, the source commit and
  ingestion timestamp are retrievable without needing to inspect
  database internals or re-run the ingestion.

## Evaluation Evidence

**Evaluation Required**: No.

This feature is a correctness/performance property of the ingestion
pipeline (graph and vector-corpus equivalence to a full rebuild), not a
retrieval-ranking or generation-quality change — it does not alter
what gets retrieved or generated for a given, already-current corpus.
The equivalence check (FR-012/SC-002) is the relevant evidence
mechanism and is specified as a functional/success requirement above
rather than a retrieval-quality evaluation.

## Assumptions

- Content fingerprinting is byte-level (SHA-256 of raw file content),
  with no semantic awareness — a whitespace-only or formatting-only
  change is treated as a real change and triggers re-embedding. This
  is the same tradeoff ADR-036 already made in rejecting content
  hashes as an *identity* mechanism, applied here as a *change
  detection* mechanism instead, which is the use ADR-036 itself
  suggested as future work ("track file hash... to detect changes").
- The existing repo-scope advisory lock (ADR-050) continues to
  serialize ingestion attempts per `repo_id`; this feature does not
  need to add its own concurrency control.
- `GitPython` (already a dependency, already used for
  `git.Repo.clone_from`) is sufficient for commit SHA resolution;
  no new git tooling dependency is introduced.
- The existing per-file walk/filter logic in `RepoGraphBuilder`
  (ignored directories, extractor-suffix support) remains the source
  of truth for "which files participate in ingestion at all" — the
  changed/unchanged/deleted classification in FR-004 operates over
  that same filtered file set, not a raw `git diff`, so that a file
  gaining or losing extractor support between generations is handled
  by the existing walk/filter logic rather than by a separate git-diff
  code path that could disagree with it.
- Exact storage representation for per-file fingerprints (a column on
  `document_nodes`' file-level rows vs. another shape consistent with
  FR-011) is a design decision for the implementation plan
  (`/speckit-plan`), not fixed by this spec.
- FR-010's lineage endpoint exposes generation-level lineage (source
  commit SHA, ingestion timestamp, parent generation, full-vs-incremental,
  whether it was a forced full rebuild) — not a full per-file fingerprint
  dump. Per-file fingerprint data is internal change-detection state,
  not something this feature commits to exposing via API.
- FR-007a/FR-007b require `ingestion_service/src/core/codebase/codebase_persistence.py::CodebaseGraphPersistence.persist_graph`
  (today: unconditional delete-all-then-insert-all-with-fresh-UUIDs, in
  one transaction, per repo per ingestion) to change to an upsert-by-
  `canonical_id` model for reused rows. The exact mechanism (in-place
  `UPDATE` vs. a different transaction shape; whether this needs its
  own ADR given how central it is to this feature and how it changes a
  previously-unconditional invariant) is a `/speckit-plan` decision —
  this spec fixes only the outcome (`document_id` stability +
  `ingestion_id` re-tagging for reused rows), not the mechanism.
