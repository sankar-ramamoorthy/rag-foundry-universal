---
title: "E1 held-out set: stratification and selection declaration"
date: 2026-10-28
type: experiment-contract
status: frozen-before-repository-selection
tags: [held-out, stratification, adr-054, evidence-delivery]
related:
  - "[Issue #281](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/281)"
  - "[Frozen statement-level contract, section 10](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
  - "[GO-rate addendum](/DOCS/evaluations/code-evidence-e1/statement-level-contract-addendum-go-rate.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[E1 development manifest](/DOCS/evaluations/code-evidence-e1/README.md)"
---

# E1 held-out set: stratification and selection declaration

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by
#281. This file is committed and merged **before any repository is chosen and before
any case is written**; its recorded SHA-256 is pinned by a CI test. The repository
selection, the cases, the second review and the manifest freeze happen later, in
that order, and are all bound by this declaration. A change after this point needs a
new dated declaration that supersedes it and is itself committed before the
repository-selection record.

## 1. What is fixed by earlier, frozen documents

- **Shape:** exactly 12 cases over exactly 3 repositories, 4 cases each (GO-rate
  addendum, section 3).
- **Excluded repositories** (development or diagnosis data): LightRAG,
  rag-foundry-universal and py-coding-agent. The deployed stack also holds six
  one-node placeholder repositories; none is eligible.
- **Gate and scores:** the delivery gate (S3, S4, S5, S6) and everything else in the
  frozen contract, unchanged.

## 2. Roles and independence

| Role | Who | Notes |
| --- | --- | --- |
| Author (selects repositories, writes cases) | Claude (AI assistant) | The same assistant wrote the oracle and drafted the contract, so shares their assumptions. Mitigations: this pre-declared stratification, mechanical validity checks, and the independent review below |
| Second reviewer | The repository owner | Not the author. Reviews every case before freezing (section 8) |
| Freezer | The repository owner | Accepts the reviewed set and approves the freeze commit |

Review findings are recorded only as the reviewer actually states them.

## 3. Repository eligibility (all must hold)

1. Public Python repository with a **permissive license**: MIT, Apache-2.0, BSD-2-Clause
   or BSD-3-Clause, so pinned function bodies can be stored in a manifest with
   attribution recorded in the manifest README.
2. Not one of the excluded repositories, and not used for development or diagnosis
   anywhere in this project.
3. **Not a retrieval/LLM/RAG/agent framework** (both development repositories are).
4. Python source of **30 to 400 files** (excluding tests, vendored code, docs, examples
   and generated files), so one repository is a coherent, ingestible codebase and not
   a monorepo of many projects.
5. **Stars between 300 and 8,000** at selection time and a commit within the last 3
   years. The lower bound avoids abandoned or toy code; the upper bound reduces the
   chance that very famous code is memorized by the answer model. This is a declared
   heuristic, not a guarantee against training-data exposure.
6. Pinned by a full commit SHA on the default branch, recorded at selection.
7. **Shape availability** (section 5): the repository offers enough candidate
   functions to fill its four cases.

## 4. Repository selection procedure (deterministic; executed after this file is merged)

Three **domains**, chosen so the held-out repositories differ from each other and from
the development repositories: **D1** command-line/developer tooling (GitHub topic
`cli`), **D2** HTTP/networking libraries (topic `http`), **D3** parsing/serialization
libraries (topic `parser`; fallback topic `serialization` only if D3 yields no
qualifying repository).

For each domain, in this order:
1. Query GitHub for `language:python topic:<topic> stars:300..8000 archived:false`
   for each of the four permitted licenses separately; merge, de-duplicate, sort by stars
   **descending**; take the first 30. Query strings may be adjusted only for syntax and
   are recorded verbatim with the date and the result list.
2. Apply eligibility criteria 2 to 6 mechanically, in list order.
3. For the first repository that passes, run the shape-availability scan (section 5).
   **Take the first repository, in star order, that passes the scan.** No other
   choice or reordering is allowed, and every rejected repository is recorded with its
   reason.

Selection uses only public metadata and static analysis of the pinned source. It does
not use retrieval output, control output, candidate output or oracle byte costs.

## 5. Stratification variables

Measured by static analysis (`ast`) on the pinned source, for module-level functions
and methods:

| Variable | Bins |
| --- | --- |
| V1 body length (lines) | short < 40; medium 40-119; long >= 120 |
| V2 signature length (lines of decorators plus `def` header) | short <= 3; long >= 8 |
| V3 witness spread (lines between first and last required expression, per case, measured once the case is written) | narrow < 25; wide >= 60 |
| V4 functions the answer needs | 1, 2 or 3 |
| V5 control-flow context of witnesses | in an `else`/`elif`; in `try`/`except`/`finally`; in a loop or `with`; none |
| V6 callable kind | module-level function; method |
| V7 question style | explicit (names the symbol and file); natural-language discovery (names neither) |

Development reference points (for orientation, not as targets): L1 spans 3 functions
with 13-line signatures; F3 is one 361-line function with a 17-line signature and wide
witnesses; F1 is a 20-line function plus a 3-line helper.

## 6. Quotas for the 12 cases (declared now)

Every case also has 4 to 5 required operations and 3 to 4 required dependency
expressions, as the development cases do, so the joint gate is comparable.

| # | Quota (over all 12 cases) |
| --- | --- |
| Q1 | at least 2 cases need 2 or 3 functions, with at least one of them having a long signature (V2 long) |
| Q2 | at least 3 cases centre on one long function (V1 long) with wide witness spread (V3 wide) |
| Q3 | at least 2 cases centre on a short function (V1 short) with narrow witnesses |
| Q4 | at least 3 cases with witnesses in an `else`/`elif`; at least 2 in `try`/`except`/`finally`; at least 2 in a loop or `with` (a case may count in several) |
| Q5 | at most 2 cases whose key function is a method; the rest module-level |
| Q6 | at least 4 cases of natural-language discovery style (V7); the rest explicit |
| Q7 | each repository contributes at least one case to Q1-Q3 and none contributes more than two cases to the same one of Q1, Q2, Q3 |

Q1 + Q2 >= 5 deliberately weights the set toward long, spread and long-signature
shapes, because the GO rule needs the unchanged control to fail at least 5 cases and
every development case failed the joint gate. This is done by stratification, not by
inspecting control results.

Per-repository **shape availability** for step 4.3: the pinned source must contain at
least 2 functions with V1 long, at least 1 with V2 long, at least 2 with V1 short and
a branch, `try` or `with`, and at least 1 pair of functions where one calls the other
(for the multi-function quota). Thresholds are minimums for eligibility, not the case
selection.

## 7. Authoring rules

1. Cases are written **from the source only**, before any retrieval, ingestion for
   evaluation, control or candidate run on the repository.
2. Each case has a question, 4 to 5 operations (steps that must be present in the
   delivered evidence) and 3 to 4 dependency expressions (conditions or state
   relationships between them), each a verbatim substring of the pinned function body.
   The questions must not quote an expression, name a line number or state the answer.
3. Every expression's first line must occur **once** in its function; otherwise the
   case pins the line number. The structural oracle may be run only to confirm that
   each expression is located and unambiguous and each function parses.
4. Questions must be answerable from the pinned source as written, and the required
   operations and dependencies must be genuinely needed for the answer, not trivia.

## 8. Validity exclusions, and what may never exclude a case

A drafted case may be dropped or rewritten **only** for: an expression that is
unlocated or ambiguous after pinning; a function that does not parse; a licensing
problem; or a reviewer finding that the question is ambiguous, unanswerable or
leaking. A case must **never** be added, dropped or reshaped because of its byte cost
under the oracle, any retrieval, control or candidate output, or any expected result.
If a quota cannot be met by valid cases, that is reported and handled by a superseding
declaration before the freeze, not by relaxing validity.

## 9. Independent review (the owner as second reviewer)

Before freezing, the reviewer checks each case against the pinned source for: (a) the
question is answerable as written; (b) every expression is verbatim, unambiguous and
necessary; (c) operations and dependencies are genuinely required, not incidental;
(d) the question does not leak an expression or the answer; (e) the stratum labels are
correct; (f) license and attribution are recorded. Verdicts are recorded per case in
`review.md` exactly as the reviewer gives them. A case the reviewer rejects is rewritten
under section 8 or dropped, and the set is re-checked against the quotas.

## 10. Freeze

After the review: `manifest.json` (questions, expressions, pinned source bodies with
file and line span, repository and commit, license), `manifest.sha256`, a README naming
each repository, commit and license, and a unit test pinning the checksum and the
counts (12 cases, 3 repositories, 4 each, no development repository). The manifest
commit comes after the GO-rate addendum (already merged) and after this declaration.
Node text in the manifest is the function source extracted from the pinned commit; it
is **verified against the stored `DocumentNode.text` when the repository is later
ingested**, and a mismatch is reported then, not silently corrected.

## 11. What must not happen before the freeze

No ingestion of a candidate repository into the stack for evaluation, no retrieval,
control or candidate run on it, and no use of E1 development results to choose among
valid cases.

## 12. Limits

Twelve cases over three repositories is an exploratory gate (GO-rate addendum,
section 5). The selection procedure removes discretion in picking repositories but not
in writing cases; that is the part the independent review exists to check.
