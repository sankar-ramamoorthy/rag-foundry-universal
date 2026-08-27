# Phase 0 Research: RAG Quality Baseline (WP-Q0)

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

spec.md left no `[NEEDS CLARIFICATION]` markers — the methodology doc
(`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`) already answers most
scope questions. What remains are execution-level decisions the spec
deliberately left to planning. Each is recorded below as Decision /
Rationale / Alternatives, per the plan workflow's Phase 0 format.

## Decision 1: Which documents make up the "2-3 representative documents"

**Decision**: Use documents that already exist in the repository (e.g. a
couple of `DOCS/audit/` or `README`-level docs with clear factual content),
not newly authored text.

**Rationale**: spec.md FR-001 requires "real ingested data, not synthetic
text," and the Assumptions section rules out new authoring effort. Using
pre-existing project documents also avoids the risk of unconsciously writing
documents whose answers are easy to retrieve, which would bias Recall@K
upward.

**Alternatives considered**:
- Author new synthetic documents for the evaluation — rejected, contradicts
  FR-001 directly.
- Use only `shared/smoke_repo`'s own README as the document corpus —
  rejected, doesn't give a genuine code+document mix (spec.md FR-002
  requires questions "mixing code and document queries").

## Decision 2: Evidence file location and shape

**Decision**: A single file,
`DOCS/test_results/2026-08-26-wp-q0-rag-quality-baseline.md` (date set at
actual execution time, not authoring time, if they differ), containing the
diagnostic table, clean-context scores, failure classifications, and final
verdict together in one document.

**Rationale**: the methodology's WP-Q0 acceptance criteria (§0) call for "one
recording table... in `DOCS/test_results/`." A single file keeps the full
diagnostic surface reviewable in one place for Scenario 4's classification
step, rather than requiring cross-referencing multiple files.

**Alternatives considered**:
- Separate files per phase (corpus, diagnostics, clean-context, verdict) —
  rejected, makes the Scenario 4 classification pass (which reads from
  everything at once) harder to execute and review.

## Decision 3: How Recall@K and rate metrics get computed

**Decision**: Ranks, leakage checks, and duplicate counts are recorded
directly from `/v1/vectors/search` (or the orchestrator's retrieval path)
responses per question, by manual inspection, per the methodology §2 "How to
check" procedure. A short ad hoc script may be used to tally Recall@5/20
percentages from the recorded per-question ranks, but it is not committed as
part of any service package — it's a throwaway aid, not new eval
infrastructure.

**Rationale**: matches spec.md's Assumptions (manual/semi-manual evaluation,
no new automated eval harness) and spec.md's Non-Goals (no new automated
tooling beyond what the methodology already calls for).

**Alternatives considered**:
- Build an automated evaluation harness now — rejected; spec.md Non-Goals
  explicitly excludes this until evidence shows a recurring need for one.

## Decision 4: How the clean-context generation test is invoked

**Decision**: Call Ollama directly for the clean-context step (bypassing the
LiteLLM-routed `/generate` service), using the model currently in
production per `LLM_DEFAULT_ALIAS`, so latency and quality numbers reflect
the actually-deployed model.

**Rationale**: this is the exact choice the methodology (§3) already
specifies as acceptable for this diagnostic — recorded here as the concrete
decision made for this evaluation run, not restated as methodology.

**Alternatives considered**:
- Route through the `/generate` service as normal — rejected for this
  specific isolation step; the point of Scenario 3 is to isolate generation
  from retrieval *and* from routing plumbing, so a direct model call keeps
  the measurement focused on grounding/citation/omission alone.

## Output

All unknowns relevant to executing this plan are resolved above. No
`[NEEDS CLARIFICATION]` markers remain.
