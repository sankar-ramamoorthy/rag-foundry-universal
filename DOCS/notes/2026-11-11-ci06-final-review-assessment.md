---
title: "CI-06 supplied assessment: close the review loop after final Codex verification"
date: 2026-11-11
type: note
status: complete
summary: "User-supplied assessment supports acceptance and merge after reporting cleanup and current CI; cache follow-up separate, deployment deferred"
source: "Assessment pasted by the owner after the second Codex review; authorship of the pasted assessment is not independently established"
authority: "Supplied assessment and recommendations; does not record formal ADR acceptance, merge, or deployment authorization"
tags: [ci06, review, assessment, opus-codex, issue-337, pr-339]
related:
  - "[Final Codex verification](/DOCS/audit/2026-11-11-ci06-pr339-final-verification.md)"
  - "[Original independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)"
  - "[Verification report](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[CI-06 handoff](/DOCS/notes/2026-11-10-ci06-embedding-input-contract-handoff.md)"
  - "[ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md)"
---

# CI-06 supplied final-review assessment

The owner requested preservation of the following assessment alongside the
final independent verification. It is supplied commentary, not a claim of a
third independently executed test run. Heading levels and escaped numbering
were normalized for this document; its recommendations and qualifications are
preserved.

## Supplied review

The second Codex review has reached a much stronger conclusion: the two original correctness blockers are resolved, and Codex recommends accepting ADR-056 and merging PR #339.

I've reviewed its findings alongside the updated verification report and evaluation scripts.

### Independent review outcome

| Finding | Codex's conclusion | My assessment |
|---|---|---|
| R1 — Silent embedding truncation | Resolved | Strong evidence, including real Ollama tests |
| R2 — Generation mixing | Resolved | Strong PostgreSQL tests, including deliberately removing the fix |
| R3 — Inaccurate token counting | Resolved | Incorrect measurements withdrawn; provider-based verification substituted |
| R4 — Delivery quality | Passed bounded criteria | Useful evidence, but not full RAG answer-quality validation |
| R5 — Identity and rollout | Addressed within CI-06 | Broader CI-03 correctly remains separate |

The particularly convincing result is R2: removing the generation fence caused the PostgreSQL tests to fail, while restoring it made them pass.

That establishes that the tests are capable of detecting the actual defect.

### Two remaining findings

1. Evaluation-cache validation — Medium

The evaluation harness can reuse a cached legacy embedding without establishing that the same input passes strict provider validation.

Codex reproduced this behavior. It then checked all 4,505 potentially affected upload passages against the actual Ollama model, with zero rejections.

That substantially reduces concern about the published evaluation, but the harness defect still exists.

2. Incorrect reporting — Low

The report says no expected statements were lost. The accurate claim is that no evaluated case experienced a decline in its total number of delivered statements.

One case did lose a particular expression while gaining others.

This doesn't invalidate the predefined acceptance criteria, but the documentation should be corrected.

### The quality result

Evidence delivered: **48 → 61**, of 112 expected expressions.

Multilingual retrieval: **102 → 94**, top-5 hits of 150; exactly the allowed regression margin.

The multilingual regression remains worth investigating later, but it met the pre-registered acceptance criterion. It shouldn't automatically become another CI-06 blocker.

### My recommendation

I would accept ADR-056 and approve PR #339 for merge, with one small cleanup before merging: correct the misleading statement in the verification report.

I would track the evaluation-cache issue separately rather than launch another lengthy experiment. The reviewer has already performed a targeted provider check to assess its impact.

There is no need for another architecture review cycle.

One limitation: Codex couldn't independently confirm the current GitHub CI status because its authentication failed. The final merge should still require the reported green CI to be current.

And as you've decided, no deployment or re-ingestion yet.

### What this says about the Opus–Codex experiment

This has been a revealing exercise. Opus built a major correction autonomously, Codex identified genuine defects, Opus corrected them, and Codex subsequently verified those corrections.

It demonstrates why independent model review is worthwhile, even for work produced by a capable autonomous coding agent.

More importantly, CI-06 now has substantially stronger correctness evidence than it had when the first green PR appeared.

I think we're ready to close the engineering loop on CI-06 and move forward.

## Recording disposition

The reporting correction was applied when this note was recorded. The cache
issue remains an open, nonblocking follow-up in the final verification record.
ADR acceptance and merge are recommendations awaiting their own explicit state
changes; deployment and re-ingestion remain deferred. No GitHub issue, merge,
or deployment was performed as part of recording this assessment.
