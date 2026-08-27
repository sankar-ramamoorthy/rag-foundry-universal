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
check" procedure. A short scratch script MAY be used for deterministic
aggregation/arithmetic over that already-recorded evidence — e.g. tallying
Recall@5/20 percentages from the recorded per-question ranks — since manual
percentage arithmetic carries real transcription/math-error risk and
reproducibility matters more here than manual-only purity. If it materially
improves reproducibility, commit it under
`specs/001-rag-quality-baseline/scripts/`; if it's trivial and genuinely
one-shot, leaving it uncommitted is also fine. What remains excluded is a
reusable evaluation *framework* — a new service, database, API, or
abstraction layer — not the act of automating arithmetic.

**Rationale**: matches spec.md's Assumptions (manual/semi-manual evaluation)
and spec.md's Non-Goals (no new automated eval *tooling/harness*), while
recognizing that a five-line aggregation script is not the same thing as
building an evaluation subsystem.

**Alternatives considered**:
- Build an automated evaluation harness now — rejected; spec.md Non-Goals
  explicitly excludes this until evidence shows a recurring need for one.
- Require all aggregation to be done by hand — rejected; this increases
  transcription/math-error risk without protecting anything the constitution
  actually cares about (no production dependency, no pipeline change).

## Decision 4: How the clean-context generation test is invoked

**Decision (revised after review)**: Call the existing `llm_service`
`POST /generate` endpoint — the same endpoint production uses — substituting
the hand-picked 2-4 known-correct chunks for the retrieved context. Verified
in code (`rag_orchestrator/src/core/service.py`,
`llm_service/src/api/v1/models.py`, `llm_service/src/api/v1/main.py`) that
`/generate` already accepts exactly `{context: str, query: str}`, the same
shape production sends, and returns `provider`, `model`, `model_alias`, and
`prompt_template` in its response — so no new endpoint is needed, and the
actual model/routing/prompt-template provenance is recorded for free. Record
those returned fields in the Clean-Context Score (data-model.md).

**Rationale**: the methodology doc (§3) suggests calling Ollama directly and
says bypassing `/generate` "is fine for this diagnostic" — but review caught
that doing so changes two variables at once relative to the failed
production run: the context *and* the generation path (prompt template,
LiteLLM routing, model aliasing, fallback handling, provenance). If Scenario
3's results differ from production, that difference can't be cleanly
attributed to retrieval vs. generation when the generation path itself also
changed. Using the existing `/generate` endpoint with only the context
substituted holds the generation path constant — the cleaner controlled
experiment — while still isolating retrieval by using known-correct chunks.
This also means Constitution Principle IV's model-routing provenance is
naturally preserved rather than bypassed, since `/generate`'s existing
response already returns which model actually served the request.

**Alternatives considered**:
- Call Ollama directly, per the methodology doc's literal suggestion —
  rejected on review: confounds context quality with generation-path
  changes, and bypasses the already-implemented model provenance/fallback
  behavior instead of exercising it.
- Build a new endpoint or internal helper specifically for this diagnostic —
  rejected as unnecessary; `/generate` already accepts arbitrary context in
  the right shape, so adding a new endpoint would be exactly the kind of
  scope creep this spec's Non-Goals rule out. (Had `/generate` *not*
  supported this shape, the fallback would have been the closest existing
  internal invocation that preserves the real prompt template and routing,
  or an explicitly documented limitation in the evidence — not a new
  production endpoint.)

## Output

All unknowns relevant to executing this plan are resolved above. No
`[NEEDS CLARIFICATION]` markers remain.
