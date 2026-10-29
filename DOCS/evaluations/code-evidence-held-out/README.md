---
title: "E1 held-out set (frozen)"
date: 2026-10-28
type: evaluation-manifest
status: frozen-before-any-run
tags: [held-out, adr-054, evidence-delivery, frozen]
related:
  - "[Issue #281](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/281)"
  - "[Frozen manifest](/DOCS/evaluations/code-evidence-held-out/manifest.json)"
  - "[Stratification declaration](/DOCS/evaluations/code-evidence-held-out/stratification.md)"
  - "[Selection record](/DOCS/evaluations/code-evidence-held-out/selection-record.md)"
  - "[Independent review record](/DOCS/evaluations/code-evidence-held-out/review.md)"
  - "[Statement-level contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
  - "[GO-rate addendum](/DOCS/evaluations/code-evidence-e1/statement-level-contract-addendum-go-rate.md)"
---

# E1 held-out set (frozen)

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by #281.
Twelve held-out cases, four in each of three repositories that were never used for
development or diagnosis in this project (ADR-054). Written from the pinned sources only,
reviewed by the repository owner as independent second reviewer (round 1: six accepted, six
rewritten, none dropped; the revisions were then approved), and **frozen on 2026-10-28** before any
ingestion, retrieval, control or candidate run touched these repositories.

## Repositories, pins and attribution

Function text from these projects is stored in `manifest.json` under their licenses. The
copyright notice and license text of each are kept here and must accompany any redistribution.

| Repository | License | Pinned commit | Copyright notice | License text |
| --- | --- | --- | --- | --- |
| [pypa/hatch](https://github.com/pypa/hatch) | MIT | `740565ac2929597cb9def8d46338cbef6493fc8d` | Copyright (c) 2017-present Ofek Lev <oss@ofek.dev> | `licenses/pypa-hatch.LICENSE.txt` |
| [pallets/werkzeug](https://github.com/pallets/werkzeug) | BSD-3-Clause | `b73dce5a2ce14f7c7fd645699d1d878de48d2948` | Copyright 2007 Pallets | `licenses/pallets-werkzeug.LICENSE.txt` |
| [pdfminer/pdfminer.six](https://github.com/pdfminer/pdfminer.six) | MIT | `a18de2a9c479b4c847538500017b449ddaec177e` | Copyright (c) 2004-2016  Yusuke Shinyama <yusuke at shinyama dot jp> | `licenses/pdfminer-pdfminer.six.LICENSE.txt` |

## Cases

| Case | Repository | Function(s) | Slot | Question style |
| --- | --- | --- | --- | --- |
| H1 | pypa/hatch | `show` | A | explicit |
| H2 | pypa/hatch | `lock`, `run_lock_workflow` | B | explicit |
| H3 | pypa/hatch | `main` | C | explicit |
| H4 | pypa/hatch | `run` | D | natural |
| P1 | pdfminer/pdfminer.six | `extract_text_to_fp` | A | explicit |
| P2 | pdfminer/pdfminer.six | `dumpallobjs`, `dumppdf`, `dumptrailers` | B | explicit |
| P3 | pdfminer/pdfminer.six | `extract_text` | C | explicit |
| P4 | pdfminer/pdfminer.six | `dumpoutline` | D | natural |
| W1 | pallets/werkzeug | `send_file` | A | natural |
| W2 | pallets/werkzeug | `is_running_from_reloader`, `make_server`, `run_simple` | B | explicit |
| W3 | pallets/werkzeug | `run_with_reloader` | C | explicit |
| W4 | pallets/werkzeug | `run_wsgi_app` | D | natural |

Each case has 4-5 required operations and 3-4 dependency expressions, every expression a
verbatim single-occurrence line of its pinned function. Slots follow the declaration: A longest
eligible function, B largest signature calling a same-file function, C shortest branchy
function, D natural-language question.

## What is frozen, and how to verify it

`manifest.json` is pinned by `manifest.sha256` (SHA-256 of the file's LF content; the repository
pins both files to LF). A CI test fails if they disagree.

```bash
git show HEAD:DOCS/evaluations/code-evidence-held-out/manifest.json | sha256sum
```

It must print the value in `manifest.sha256`. Changing anything needs a new dated declaration
that supersedes this one; it cannot be edited in place. The manifest records the SHA-256 of the
stratification declaration, the GO-rate addendum and the statement-level contract it was built
under.

## Use rules (stratification declaration, section 10; GO-rate addendum)

- The unchanged control runs on these cases too, and control drift is reported.
- Each frozen candidate version runs on this set **once**. A failed case is not retried or fixed
  in place. Once a held-out result is used to change a candidate, those cases become development
  data and a new held-out set must be frozen for the next version.
- The decision rule is the GO-rate addendum's: at least 10 of 12 passing the delivery gate, at
  least 5 wins over the unchanged control, at least 3 of 4 per repository and no regressions.
  Answer correctness does not decide it. Twelve cases are an exploratory gate, not a
  generalization claim.
- Results are reported per case and never pooled with the development cases.

## Known limitations (recorded at review; selected functions were not replaced)

- Concentration: three of pypa/hatch's four cases (H1, H2, H4) are `hatch env` click commands with decorator-heavy signatures; the fourth (H3) is a release script. Hatch results characterise those commands, not the repository broadly.
- Overlap: P2 and P4 both live in tools/dumppdf.py and both involve dumpxml, so they are not independent observations.
- Narrow coverage: three of pdfminer.six's four cases are command-line utilities under tools/, not library modules.
- Training-data exposure: pallets/werkzeug is very likely well represented in model training data despite its star count.
- Source text is the pinned function source, not the stored DocumentNode.text; that comparison happens at ingestion time.

## Not yet done

No repository has been ingested into the evaluation stack. The stored node text must be compared
with the pinned function text when each is ingested. A trustworthy matched control replay
(#270) is a precondition for any run.
