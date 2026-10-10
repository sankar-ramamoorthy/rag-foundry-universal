---
title: "Issue #240 claim-specific authority comparison on corrected corpus"
date: 2026-10-04
type: test-results
status: complete-with-failed-merge-gate
tags: [evaluation, repository-overview, authority, retrieval]
related:
  - "[Frozen protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Prior comparison](/DOCS/test_results/2026-10-03-issue-240-frozen-quality-comparison.md)"
---

# Issue #240 comparison on the corrected source corpus

## Pin and arms

The one-line `CLAUDE.md` correction was merged independently in
[PR #242](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/242)
after all four CI checks passed. No #240 policy or selector code was in that
merge. Production ingestion `f873147c-a1d1-4891-bb98-972672db8e9a` is
ready from exact main SHA `7a805d5b3cee031c44fbe0d9b8048065ce8ef039`.
The indexed canonical purpose chunks contain the corrected Rust/Java wording,
without the old "planned" claim.

The [baseline JSON](/DOCS/test_results/2026-10-04-issue-240-corrected-baseline.json)
used deployed orchestrator `00e0cc9`. Four labeled, local opt-in candidate
arms used the same production ingestion, vector, and LLM services read-only:
[v1](/DOCS/test_results/2026-10-04-issue-240-claim-selection-candidate.json),
[v2](/DOCS/test_results/2026-10-04-issue-240-claim-selection-v2.json),
[v3](/DOCS/test_results/2026-10-04-issue-240-claim-selection-v3.json), and
[v4](/DOCS/test_results/2026-10-04-issue-240-claim-selection-v4.json).
Each arm ran all 11 frozen requests once with `ollama/Qwen3:4b`, `rerank=false`,
and the same context settings. The generation/source SHA checks before and
after every request, and the response generation, all matched. Local
`/version` reports `dev/unknown`; the candidate arms are identified by their
ordered code revisions and saved traces, not by a deployed release SHA.

## Findings

The experiment uses distinct evidence obligations for repository purpose,
current structure, current architecture, current behavior, and explicitly
requested historical sources. No numeric authority score was introduced.
The final v4 arm uses ORIENT for current structure, current README architecture
plus implementation URL configuration for architecture, the canonical
`CLAUDE.md` purpose section for purpose, and leaves explicitly requested
historical material retrievable.

| Case | Baseline on corrected corpus | v4 candidate |
| --- | --- | --- |
| Q1 generic structure | Fail: answers from an old diagnostic note | Pass: current ORIENT facts, correct repository subject |
| Q2 actual structure | Fail: says structure unavailable | **Fail:** says every service has a Python package and nearly every service has a test directory despite contrary inventory |
| Q3 named repository | Fail: refuses actual layout | **Fail:** gives useful inventory but also says every service has a dedicated source directory; `postgres` is a Compose service |
| Q4 architecture | Fail: promotes another repository's diagram | **Fail:** current diagram and URL source survive, but answer says all six services communicate over HTTP, including PostgreSQL |
| Q5 purpose, k=10 and k=20 | Fail: canonical purpose absent | Pass: corrected canonical purpose reaches final context and answer |
| Q6 what project does | Pass | Pass |
| Q7 purpose and source kinds | Fail: canonical purpose absent | Pass: corrected purpose and code/document kinds |
| C1 historical note | Correct answer and requested note | Correct answer and requested note |
| C2 fixture | Correct answer; exact fixture README absent | Correct answer; exact fixture README still absent |
| C3 method | Correct answer; exact method absent | Correct answer; exact method still absent |

The v4 purpose target survived final context for Q5, Q6, and Q7 (3/3), versus
1/3 on the baseline; Q5 at k=20 also survived in v4. Current README
architecture evidence survived Q4 in v4. Candidate entry and final-context
identity, excluded passages, model, trace IDs, and answers are in the JSON
records. These retrieval gains did not make Q2–Q4 pass. C1–C3 answers did not
regress, while C2/C3 retain their predeclared exact-source misses.

v1 showed that excluding historical notes could recover current answers, but
miscounted repeated Compose declarations as distinct services. v2 corrected
that count and supplied current architecture sources, yet a retrieved old
design diagram reached Q4. v3 narrowed structure/architecture context; Q3
then refused the named repository because ORIENT carries an ID without a
display name. v4 verified the display name against the pinned repository
listing and rendered per-service facts, but the model still generalized
beyond them. These revisions were measured as separate arms, not repeats of
one unchanged candidate.

## Decision

**No-go for a #240 PR, merge, or production policy deployment.** The new
claim-specific selector remains disabled by default. Unit checks passed
(`298 passed`); focused policy tests passed (`11 passed`), and Ruff and
Pyright passed. Those checks do not override the frozen answer failures.
The next change should address answer formation from verified per-service
facts without treating another broad prompt instruction as proof of factual
correctness. Preserve this comparison and the October 3 result as separate
measurements.
