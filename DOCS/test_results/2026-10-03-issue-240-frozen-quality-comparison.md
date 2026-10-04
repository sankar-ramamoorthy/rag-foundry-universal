---
title: "Issue #240 pinned overview quality comparison"
date: 2026-10-03
type: test-results
status: complete-with-failed-merge-gate
tags: [evaluation, repository-overview, retrieval, provenance]
related:
  - "[Frozen protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Earlier production localization](/DOCS/test_results/2026-09-20-issue-240-orientation-failure-localization.md)"
---

# Issue #240 pinned overview quality comparison

## Snapshot and arms

All 11 requests in each arm used the selected repository
`f7641840-ba13-5f9d-9ae6-87e1f924709d`, ready generation
`d3ecfaea-23a1-4067-8f1a-0010c3158004`, source SHA `00e0cc9`,
`ollama/Qwen3:4b`, `rerank=false`, and the [frozen requests](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md).
Generation and source SHA were checked before and after every request and
again at the end; all stayed ready and unchanged. The full response-derived
records, including seeds, expanded IDs, final manifests, diagnostics, answers,
trace IDs, and the ORIENT inventory, are in the three JSON files:
[production baseline](/DOCS/test_results/2026-10-03-issue-240-baseline.json),
[ORIENT branch](/DOCS/test_results/2026-10-03-issue-240-orient-candidate.json),
and [selection prototype](/DOCS/test_results/2026-10-03-issue-240-selection-candidate.json).
The repeatable capture command is in
[`scripts/issue240_overview_eval.py`](/scripts/issue240_overview_eval.py).

| Arm | Runtime and change |
| --- | --- |
| Baseline | Deployed `d7fbf874`; original retrieval and answer path. |
| ORIENT branch | Local orchestrator loaded from committed `e00ddb2`, pointed read-only at production ingestion/vector/LLM services; canonical selection disabled. |
| Selection prototype | Same local ORIENT branch plus an opt-in canonical-passage selector, later preserved as `07a5d59`; root provenance roles remained unchanged. |

The production `/version` endpoints still reported `d7fbf874` at the end.
Neither candidate is a production verification. The local development
`/version` endpoint reports `unknown`, so the code arm is identified by the
checkout/process state above and its saved source changes, not a release
attestation.

## Frozen-case results

`P` means the predeclared answer and evidence requirement passed; `F` means
it failed; `partial` means some required facts reached the answer but the
full acceptance criterion did not. Controls' answer behavior and source
requirement are shown separately because C2 and C3 already missed their
predeclared exact source on the baseline. This is a baseline rubric miss,
not an after-the-fact pass.

| Case | Baseline | ORIENT branch | Selection prototype |
| --- | --- | --- | --- |
| Q1 generic structure | F: says structure unavailable | partial: uses ORIENT services/counts but adds an unsupported proposed relationship and metadata | F: says no question was asked |
| Q2 actual structure | F: says structure unavailable | F: says no question was asked | F: says no question was asked |
| Q3 named repository structure | F: says structure unavailable | F: still refuses current layout and quotes old `rag-foundry-docgraph` plan | partial: gives current services from ORIENT and distinguishes the archived plan, but omits some requested structure |
| Q4 architectural map | F: wrong-project `docs/architectural-diagram.md` claim | F: repeats that claim | F: repeats that claim |
| Q5 purpose, k=10 | F: canonical purpose absent | F: canonical purpose absent | partial: canonical purpose in final context and main purpose correct; repeats stale “Rust/Java planned” claim |
| Q5 purpose, k=20 | F: canonical purpose absent | F: canonical purpose absent | partial: same retrieval gain and stale claim |
| Q6 what the project does | P: canonical purpose present and main answer correct | partial: purpose present, but repeats stale language claim | partial: same stale claim |
| Q7 purpose and sources | F: canonical purpose absent, source kinds incomplete | F: canonical purpose absent | partial: canonical purpose present and documents covered, but repeats stale language claim |
| C1 historical note | answer P, source P | answer P, source P | answer P, source P |
| C2 smoke repository | answer P, exact fixture README absent | answer P, exact fixture README absent | answer P, exact fixture README absent |
| C3 assembler | answer P, exact method absent; class source present | answer P, exact method absent; class source present | answer P, exact method absent; class source present |

The candidate answer failures are substantive, not merely missing citations.
For Q4 the retrieved passages remained scoped to this repository; one of its
notes discusses the separately ingested `py-coding-agent` diagram. The model
promoted that embedded discussion into a claim about the selected repository.
The original shadow diagnostics reported no concerns in the old runtime;
`e00ddb2` identifies historical note passages but did not prevent this answer.

## Independent hypothesis results

**Classification only, static counterfactual.** On the pinned index,
`README.md` and `CLAUDE.md` both have role `unknown_mixed`; the research note
under `DOCS/notes/` has `documentation`; `shared/smoke_repo/README.md` has
`example_fixture`. The rule is path-based and correctly shows a metadata gap.
`hybrid_retrieve` filters seeds by repository/generation/source type and its
optional tie-break uses `doc_type`, not provenance role. Therefore a role-only
change cannot change this generation's seed membership. Re-ingestion with a
revised classifier was **not performed**; the role-only quality arm is an
inspected counterfactual, not a measured end-to-end re-ingest. It is not a
supported standalone fix for Q5.

**Selection only, measured.** With old roles untouched, deterministic lookup
of `CLAUDE.md#claude_md.what_this_project_is` and a generation-filtered
search-by-document placed three chunks of that section first in final context
for the overview claim. On Q5 at both k=10 and k=20, the target remained
absent from vector seeds and graph expansion but survived through the policy
channel. This isolates candidate selection as necessary for the Q5 evidence
miss. It also shows candidate inclusion is insufficient for the full frozen
set: Q1/Q2 regressed, Q4 still asserted the wrong-project diagram, and
Q5–Q7 repeated a stale language-status claim from `CLAUDE.md`. The opt-in
selector remains disabled by default and is **not approved for merge**.

**Combined change.** Not run. There is no evidence that changing roles in
addition to this selector would fix the remaining answer failures; doing so
would require a new, labeled arm and an isolated re-ingestion.

The `GenerateSkill.run` seed-found/final-context-dropped case remains a
separate context-budget issue. No result above claims to fix it.

## Merge verdict and next experiment

**No-go for merging `e00ddb2` or the later `07a5d59` prototype as a #240 fix.** Its measured structural
answers fail Q2–Q4; the selection prototype also fails the frozen acceptance
criteria. The branch has no verified production runtime, and this environment's
`gh` authentication cannot create a PR or inspect live CI. Elevated Git can
read and publish the branch. No production
data or deployment was changed.

The next bounded experiment should prevent historical/evaluation passages
from speaking as *current repository facts* on generic overview questions,
while retaining them when explicitly requested (C1), and should include
current architecture evidence for Q4. The canonical `CLAUDE.md` language
sentence was corrected in the checkout *after* this frozen run; a new
generation is required before evaluating that correction. Prefer current
README/ORIENT facts when source claims conflict; then compare on that newly
pinned generation without rewriting this frozen run. Keep exact-symbol
context survival in its own workstream.

Local verification of the prototype: `pytest -m unit` in the orchestrator
passed (298 passed, 12 deselected); focused policy tests passed (5); Ruff
and Pyright passed for changed Python files. These mechanics checks do not
override the failed answer-quality gate.
