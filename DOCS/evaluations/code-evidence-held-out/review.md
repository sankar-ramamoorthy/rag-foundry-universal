---
title: "E1 held-out set: independent second-review record"
date: 2026-10-28
type: experiment-record
status: approved-manifest-frozen
tags: [held-out, review, adr-054, evidence-delivery]
related:
  - "[Issue #281](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/281)"
  - "[Stratification declaration, section 9](/DOCS/evaluations/code-evidence-held-out/stratification.md)"
  - "[Review package](/DOCS/evaluations/code-evidence-held-out/review-package.md)"
  - "[Frozen manifest](/DOCS/evaluations/code-evidence-held-out/manifest.json)"
---

# E1 held-out set: independent second-review record

Roadmap phase: Phase 6, workstream E. Tracked by #281. Reviewer: the repository owner
(independent second reviewer, declaration section 2). This file records the reviewer's
verdicts **as stated**, and what was done about them. It does not record any approval that
has not been given.

## Verdicts as stated by the reviewer (2026-10-28)

> ACCEPT: H2, H4, P2, P3, P4, W1.
> REWRITE: H1, H3, P1, W2, W3, W4.
> DROP: None.

| Case | Verdict | Reviewer's note (as stated) |
| --- | --- | --- |
| H1 | REWRITE | feature normalization and invalid-dependency handling must be explicitly relevant |
| H2 | ACCEPT |  |
| H3 | REWRITE | clarify file selection and modification versus preservation |
| H4 | ACCEPT |  |
| P1 | REWRITE | remove incidental debug/image-writer requirements or make them explicitly relevant |
| P2 | ACCEPT |  |
| P3 | ACCEPT |  |
| P4 | ACCEPT |  |
| W1 | ACCEPT |  |
| W2 | REWRITE | resolve the startup-banner dependency |
| W3 | REWRITE | resolve the terminal-echo dependency |
| W4 | REWRITE | resolve the environment-copy requirement |

Reviewer's instructions, as stated:

- For each rewrite, align the required evidence with what the question actually asks.
- Preserve the predeclared selection rules, pinned commits and stratification quotas.
- Do not inspect retrieval outputs, control results, candidate results or oracle byte costs.
- Record the H1/H2/H4 concentration and the P2/P4 overlap as evaluation limitations, without
  opportunistically replacing selected functions.
- Return the six revised cases with their complete question and required-evidence
  specifications, highlighting what changed; re-run mechanical checks; confirm semantic
  necessity against the pinned function bodies.
- Do not merge PR #289 or freeze the manifest until the reviewer approves the revisions.
  No ingestion or retrieval runs yet.

## What was done (round 1)

The six rewrites were made and are listed with their changes in the review package. The
selection rules, pinned commits and quotas are unchanged (re-checked mechanically: every
expression is verbatim and single-occurrence, 4-5 operations and 3-4 dependencies per case,
all quotas met). The six accepted cases are byte-for-byte unchanged in question and evidence.
Semantic necessity was confirmed by mapping every operation and dependency of the six revised
cases to the clause of its question that needs it (the `needed_for` field of each item), and
checking each against the pinned function body.

## Limitations recorded (not acted on by replacing functions)

- Concentration: three of pypa/hatch's four cases (H1, H2, H4) are `hatch env` click commands with decorator-heavy signatures; the fourth (H3) is a release script. Hatch results characterise those commands, not the repository broadly.
- Overlap: P2 and P4 both live in tools/dumppdf.py and both involve dumpxml, so they are not independent observations.
- Narrow coverage: three of pdfminer.six's four cases are command-line utilities under tools/, not library modules.
- Training-data exposure: pallets/werkzeug is very likely well represented in model training data despite its star count.
- Source text is the pinned function source, not the stored DocumentNode.text; that comparison happens at ingestion time.

## Reviewer approval (2026-10-28)

> approve the revisions and freeze the manifest

(The reviewer's words, as stated.) Before freezing, the structural oracle was run only to check
that every expression is located and unambiguous and every function parses: 34 function-readings,
0 problems. No byte cost was computed. No retrieval, control or candidate output, and no
ingestion, was involved at any point.

## Status

**Approved and frozen on 2026-10-28.** `manifest.json` is pinned by `manifest.sha256`
(`ef5727be08d1a569957760e9014b884d83c4e71a70e25e7ddf2e92c16f97cfc5`). The draft manifest was removed; the authored case specs in `cases/` remain as the
source of the manifest and are checked against it by a test. Any further change needs a new
dated declaration.
