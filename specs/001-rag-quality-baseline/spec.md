# Feature Specification: RAG Quality Baseline (WP-Q0)

**Feature Branch**: `001-rag-quality-baseline`

**Created**: 2026-08-26

**Status**: Draft

**Tracking Issue**: #49

**Roadmap Context**: Phase 2.75 (WP-Q0). Gates the reranker sub-task of WP-S8
(`DOCS/audit/04-Scalability-Plan.md`) and Phase 3/4 work generally. Depends on
issue #48 (closed) per issue #49's stated dependency.

**Input**: User description: "Establish a reproducible RAG-quality baseline
that distinguishes ingestion, chunking, retrieval/ranking, context-assembly,
and generation failures and produces evidence for the next architectural
decision. Evaluation only — not an implementation of reranking, hybrid
retrieval, embedding changes, chunking changes, or prompt/model changes."

## Scenarios & Testing *(mandatory)*

<!--
  This is evaluation work, not a product feature — there is no end user.
  Scenarios below are evaluation scenarios: each is a step in producing
  evidence for the reranker/architecture decision, not a user journey.
-->

### Scenario 1 - Establish the evaluation corpus and known-answer question set (Priority: P1)

Assemble a small, curated evaluation corpus (an ingested code repository plus
a handful of documents) and a set of answerable questions, each with a known
correct source, so that every later measurement has a ground truth to check
against.

**Why this priority**: without a known-answer set, no rank, recall, or
generation-quality measurement in this spec means anything — every other
scenario depends on this one.

**Independent Test**: the corpus is ingested and queryable, and the question
set exists as a reviewable artifact (question, expected `canonical_id` or
passage, `repo_id`) independent of any later measurement being run yet.

**Acceptance Scenarios**:

1. **Given** `shared/smoke_repo` and 2-3 representative documents, **When**
   they are ingested into the evaluation environment, **Then** each is
   confirmed present in the index before any question referencing it is used.
2. **Given** the ingested corpus, **When** 8-12 answerable questions are
   drafted, **Then** each question has an exact expected source (a
   `canonical_id` for code or a specific passage for a document) and mixes
   code and document queries.

---

### Scenario 2 - Record the full diagnostic surface per question (Priority: P1)

For every known-answer question, record one diagnostic row covering ingestion
presence, seed rank, expanded-context rank, duplicate-candidate count,
cross-repo leakage, and end-to-end answer quality — in a single pass per
question, not as separate audits.

**Why this priority**: this is the evidence the reranker/architecture
decision is ultimately made from; every later classification step reads from
this table.

**Independent Test**: the diagnostic table is complete for all questions and
independently reviewable, regardless of whether classification or the
clean-context test has happened yet.

**Acceptance Scenarios**:

1. **Given** a known-answer question whose expected source is absent from the
   index, **When** it's evaluated, **Then** it is recorded as an ingestion
   failure and excluded from ranking-based classification (per the decision
   table in `DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §2).
2. **Given** a known-answer question whose expected source is present,
   **When** it's evaluated, **Then** its seed rank, expanded-context rank,
   duplicate count, repo-leakage result, and final answer quality are all
   recorded in the same row.

---

### Scenario 3 - Isolate generation quality with clean context (Priority: P2)

For every question whose end-to-end answer failed, re-run generation with a
hand-picked, correct 2-4 chunk context to determine whether the failure is a
retrieval problem or a generation/prompting problem.

**Why this priority**: without this isolation step, a bad end-to-end answer
can't be attributed to retrieval versus generation — this scenario only runs
against failures from Scenario 2, so it depends on that scenario but is not
on the critical path for questions that already passed.

**Independent Test**: every failed question (and only failed questions) has a
clean-context grounding/citation/omission score, reviewable independently of
the final classification step.

**Acceptance Scenarios**:

1. **Given** a question whose end-to-end answer failed, **When** the
   clean-context test is run with the correct chunks as context, **Then** a
   grounding/citation/omission score and latency are recorded for it.
2. **Given** a question whose end-to-end answer already passed, **When**
   evaluation proceeds, **Then** no clean-context test is run for it (the
   methodology explicitly limits this step to failures only).

---

### Scenario 4 - Classify every failure and produce an evidence-backed decision (Priority: P1)

Classify every recorded failure against the methodology's decision table
before changing anything, then produce an explicit go/no-go verdict on
reranking (and, if reranking isn't justified, an indication of which other
lever the evidence points to).

**Why this priority**: this is the deliverable of the whole spec — the
output every downstream Phase 3/4 decision depends on.

**Independent Test**: a written verdict exists, with the failure-count
breakdown that justifies it, independent of whether anyone has acted on it
yet.

**Acceptance Scenarios**:

1. **Given** the completed diagnostic table and clean-context scores, **When**
   every failure is classified (absent from top 20 / rank 8-20 / top-3-but-
   poor-answer / cross-repo leakage / duplicate crowding), **Then** the
   classification is recorded before any chunking, retrieval, or generation
   change is proposed.
2. **Given** the classified failures, **When** the reranker decision gate
   (`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §4) is applied,
   **Then** an explicit go/no-go verdict on reranking is recorded, along with
   the failure-count breakdown, or — if no dominant pattern holds — the
   negative result is recorded explicitly rather than left ambiguous.

---

### Edge Cases

- What happens when a question's expected source is absent from the index?
  Stop classification for that question at the ingestion check — it's
  recorded as an ingestion defect, not scored against the retrieval/reranker
  decision table.
- What happens when cross-repo leakage is found? It's recorded as a
  correctness bug (an ADR-030 violation) and filed as a separate GitHub
  issue; this spec does not fix it.
- What happens when duplicate/near-duplicate chunks crowd the top-20? It's
  recorded as a finding (duplicate rate) feeding the eventual chunking/dedup
  decision, not fixed within this spec.
- What happens if Docling output for a document appears to be re-chunked by
  `TextChunker` (double-chunking)? It's recorded as an explicit finding per
  the methodology's WP-Q1 acceptance criteria, not fixed here.
- What happens if fewer than 8 or more than 12 genuinely answerable questions
  can be constructed from the available corpus? The actual count and the
  reason for the deviation are documented; 8-12 is the methodology's
  guideline, not a hard gate on proceeding.

## Non-Goals

- Implementing a reranker.
- Adding hybrid lexical/vector retrieval.
- Changing the embedding model or re-embedding any index.
- Redesigning chunking strategy or chunk-size heuristics.
- Changing prompts, the generation model, or model-routing configuration.
- Fixing any correctness bugs discovered during evaluation (e.g. cross-repo
  leakage, double-chunking) — these are filed as separate tracked issues,
  not resolved as part of this spec.
- Building new automated evaluation tooling/harness beyond what the
  methodology's manual/semi-manual procedure already calls for.

These may become the outcomes of a future spec once this evaluation produces
evidence for them — this spec must not presuppose which one.

## Governing References

- Constitution: `.specify/memory/constitution.md` (Principles III, VI, VII,
  VIII apply directly to this spec)
- ADRs: ADR-030 (repository isolation — cross-repo leakage would be a
  correctness bug against this), ADR-039 / ADR-040 (artifact-level embedding
  — why code has no chunk-boundary question today), ADR-045 (the hybrid
  vector-graph retrieval flow being evaluated)
- Audit/roadmap: `DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` (this
  spec operationalizes that methodology's WP-Q0 section into requirements —
  see it for full procedural detail, not restated here),
  `DOCS/audit/04-Scalability-Plan.md` (WP-S8, the downstream work this spec
  gates), `DOCS/audit/07-Roadmap.md` (Phase 2.75 position)
- Tracking issue: #49

**Known conflicts**: None.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The evaluation MUST use a curated corpus containing both
  ingested code (`shared/smoke_repo`) and 2-3 representative uploaded
  documents — real ingested data, not synthetic text.
- **FR-002**: The evaluation MUST define 8-12 answerable questions, each with
  an exact expected source (a `canonical_id` for code, a specific passage for
  a document), mixing code and document queries.
- **FR-003**: For every question, the evaluation MUST record: source-present-
  in-index, seed rank, expanded-context rank, duplicate-candidate count,
  cross-repo-leakage result, and end-to-end final answer quality, in a single
  diagnostic row.
- **FR-004**: The clean-context generation test MUST be run only for
  questions whose end-to-end answer failed, not for every question.
- **FR-005**: Every recorded failure MUST be classified against the
  methodology's decision table before any chunking, retrieval, or generation
  change is proposed.
- **FR-006**: The evaluation MUST produce an explicit go/no-go verdict on
  reranking, with the failure-count breakdown that justifies it; if reranking
  is not justified, the evidence MUST identify which other lever (chunking,
  filtering, deduplication, traversal, prompting) the failures point to, or
  record an explicit negative result if no dominant pattern holds.
- **FR-007**: All evidence produced (diagnostic table, clean-context scores,
  final verdict) MUST be written to `DOCS/test_results/`.
- **FR-008**: Any correctness bug discovered during evaluation (e.g. cross-
  repo leakage, double-chunking) MUST be filed as a separate GitHub issue
  rather than fixed within this spec's scope.

### Key Entities

- **Evaluation Corpus**: the ingested repo (`shared/smoke_repo`) and 2-3
  documents used as fixture data for this evaluation; not modified by this
  spec.
- **Known-Answer Question**: a (question, expected `canonical_id` or passage,
  `repo_id`) tuple used as ground truth.
- **Diagnostic Record**: one row per question capturing the six-field
  diagnostic surface (FR-003).
- **Failure Classification**: the decision-table category assigned to a
  failed question (absent from top 20 / rank 8-20 / top-3-but-poor-answer /
  cross-repo leakage / duplicate crowding).
- **Evidence Artifact**: the file(s) under `DOCS/test_results/` recording the
  diagnostic table, clean-context scores, and final verdict.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A curated evaluation corpus (the ingested repo plus 2-3
  documents) exists and is referenced in the evidence artifact.
- **SC-002**: 8-12 known-answer questions are defined with exact expected
  sources, covering both code and document queries.
- **SC-003**: 100% of defined questions have a complete diagnostic record (all
  six fields from FR-003) in `DOCS/test_results/`.
- **SC-004**: 100% of questions whose end-to-end answer failed have a
  recorded clean-context grounding/citation/omission score.
- **SC-005**: 100% of recorded failures are classified against the decision
  table before any chunking/retrieval/generation change is proposed anywhere
  in the project.
- **SC-006**: An explicit go/no-go decision on reranking, with a
  failure-count breakdown, is recorded before Phase 3/4 work resumes.

## Evaluation Evidence

**Evaluation Required**: Yes — this spec's entire deliverable is evaluation
evidence; there is no separate "implementation" to evaluate against it.

**Baseline**:
- The current, unmodified production retrieval and generation pipeline
  (`rag_orchestrator`'s `/v1/rag` graph-aware path and `/v1/rag/simple` flat
  path, current chunking, current embedding model, current prompting) — no
  candidate change is proposed by this spec; the baseline itself is what's
  being measured and recorded.

**Metrics**:
- Recall@5 and Recall@20 for the known-answer question set
- Cross-repo leakage rate (must be zero; any nonzero result is a correctness
  bug, not a tuning signal)
- Duplicate/near-duplicate rate within the top-20 candidate set
- Clean-context grounding, citation, and omission scores per failed question
- Clean-context generation latency (cold and warm)
- Failure-class distribution (ingestion / chunking-or-retrieval / rank 8-20 /
  generation-or-prompting)

**Decision Criteria**:
- Reranking is justified only if a non-trivial fraction of failures
  consistently land at rank 8-20 and are not already explained by a chunking
  defect or a confirmed generation defect (per
  `DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §4).
- If "absent from top 20" dominates, the next work is chunking/embedding/
  filtering, not reranking.
- If "top-3-but-poor-answer" dominates, the next work is prompting/model
  choice, not reranking.
- If neither pattern dominates, the negative result is recorded explicitly
  and the next lever is chosen from whichever signal the corpus actually
  shows.

**Evidence Artifact**:
- `DOCS/test_results/` (per `DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`
  and the roadmap's requirement that nothing ships without its benchmark/eval
  delta recorded).

## Assumptions

- `shared/smoke_repo` is available and ingestable as the code corpus fixture
  without modification.
- 2-3 representative documents can be assembled from existing project
  material without new authoring effort.
- The evaluation is run manually/semi-manually via direct API calls and human
  scoring, per the methodology's existing "How to check" procedures — this
  spec does not require building new automated eval tooling (see Non-Goals).
- The live stack (`ingestion_service`, `vector_store_service`,
  `rag_orchestrator`, `llm_service`) is running and reachable for the
  duration of the evaluation.
- Ollama (local and/or the remote Tailscale endpoint per
  `LLM_DEFAULT_ALIAS`) is available for the clean-context generation test.
