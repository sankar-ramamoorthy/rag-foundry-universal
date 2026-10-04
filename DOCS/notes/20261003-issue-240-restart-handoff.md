---
title: "Issue #240 restart handoff after pinned quality comparison"
date: 2026-10-03
type: handoff
status: active
tags: [handoff, repository-overview, retrieval, evaluation]
related:
  - "[Frozen protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Measured result](/DOCS/test_results/2026-10-03-issue-240-frozen-quality-comparison.md)"
---

# Issue #240 restart handoff

## Where the checkout and deployment stand

This note is an interim handoff on
`feature/240-repository-overview-followup`, containing committed `e00ddb2`
and the default-off experiment commit `07a5d59`.
At the start of this work, local `main` and its recorded `origin/main`
were both `00e0cc9`, and the feature branch and recorded remote-tracking
branch were both `e00ddb2`, one commit ahead. A later elevated, read-only
`git ls-remote` confirmed those same live GitHub refs before publication.
A prior 119-line production follow-up was uncommitted; its diagnostic
interpretation has now been corrected and committed in the issue #240
localization record. Use `git status --short --branch` and
`git log -3 --oneline` on restart for the resulting commit state.

Production still reports `d7fbf874` from both orchestrator and ingestion
`/version` endpoints. The ready self-repository generation is
`d3ecfaea-23a1-4067-8f1a-0010c3158004`, source `00e0cc9`, selected
repo `f7641840-ba13-5f9d-9ae6-87e1f924709d`. This is an old runtime
serving a newer source corpus, not proof of a local/remote Git mismatch and
not verification of `e00ddb2`. All evaluation calls kept that generation
stable; production data was not changed.

## What was saved

- The corrected production follow-up explains that the manifest and
  diagnostics are nested under `retrieval_plan`, that Q4 is answer-subject
  contamination rather than a repository-filter leak, and that Q5 has an
  indexed purpose source missed by retrieval.
- The frozen 11-request protocol, executable read-only capture script,
  three full response-derived JSON records, and scored comparison are linked
  above. The original five questions are Q1–Q5; Q5 also has the exact k=20
  repro. C1–C3 are historical, fixture, and implementation controls.
- A local, opt-in purpose-passage selector prototype is preserved in
  `07a5d59`. Its config default is **false**. It
  was measured against the same generation but failed the quality gate; do
  not enable or deploy it based on its Q5 retrieval improvement alone.
- The root `README.md` and `CLAUDE.md` provenance roles on the pinned
  corpus are `unknown_mixed`. A role-only change cannot alter current seed
  selection because that path does not rank on provenance role.

The [comparison](/DOCS/test_results/2026-10-03-issue-240-frozen-quality-comparison.md)
is the authority for exact traces and scoring. In short, `e00ddb2` did not
make Q2–Q4 pass; deterministic purpose inclusion made Q5's canonical
passage survive, but Q1/Q2 regressed and Q4 stayed wrong. `CLAUDE.md` still
said Rust/Java were planned although current README and implementation say
they have shipped. The checkout's opening `CLAUDE.md` paragraph was
corrected after the frozen run; the production corpus still contains the
prior version until a new ingestion.

## Merge gate and next action

**Do not merge or deploy the current branch as a #240 fix.** The measured
answer-quality gate failed. `gh auth status` reported an invalid token in
this shell. Elevated Git access could read the live refs and is used to
publish the branch commits; `gh` PR and CI operations remain unavailable
here. No PR, CI run, merge, or docs-only handoff branch was created in this
session. Reauthenticate `gh` before PR work, and refresh live refs rather
than trusting saved remote-tracking state.

Next, keep the source/generation pin and run a bounded authority-selection
experiment: for generic overview questions, stop old notes and archived
plans from becoming current-repository claims; retain them when explicitly
requested (C1); supply current architecture evidence for Q4. Ingest a new
generation containing the corrected `CLAUDE.md` before claiming Q5–Q7
correctness. Label the result as a **new** matched baseline/candidate
comparison, leaving the
2026-10-03 frozen result intact. Repeat the same controls and inspect seeds,
candidate entry, final-context survival, answer subject, and unsupported
claims. Keep `GenerateSkill.run` context survival separate from #240.

Only after the frozen gate passes: open the feature PR, obtain CI/review,
merge with the limitations stated accurately, then create the requested
docs-only branch from merged `main` to update this handoff with final PR,
release, and production-verification identifiers. A production deployment
must be verified by its actual `/version` SHA and the five original questions
against a ready pinned generation.

Local checks already run: orchestrator unit suite `298 passed, 12 deselected`;
focused overview policy tests `5 passed`; Ruff and Pyright clean for changed
Python files. The live quality failures remain despite those mechanics checks.
