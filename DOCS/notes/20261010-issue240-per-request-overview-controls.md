---
title: "Issue #240 per-request repository-overview controls"
date: 2026-10-10
type: note
status: deployed-evaluated
tags: [repository-overview, evaluation, gradio, runtime-controls]
related:
  - "[Current status](/DOCS/status.md)"
  - "[Frozen overview evaluation](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
---

# Issue #240 per-request repository-overview controls

The [PR #246](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/246)
follow-up adds independent
request overrides for claim selection, structured answers, and canonical
selection. It also adds a Normal RAG / Repository Overview query mode to
Gradio. Repository Overview sends `claim_type=repository_overview`; without
that claim type, the three controls cannot activate overview policy.

Gradio defaults all controls off and sends explicit booleans with each query.
The orchestrator validates JSON booleans, resolves effective values once per
request, never mutates cached settings, and returns them in
`retrieval_plan.repository_overview_controls`. Gradio displays that server
confirmation; an older runtime that omits it is labeled unconfirmed.
Normal RAG requests do not activate overview behavior even if controls are
sent. Existing API callers that omit overrides retain their current
deployment-setting defaults, preserving the frozen evaluation path; no `.env`
change is required to use per-request controls after this version is
deployed. The frozen evaluator additionally accepts `--claim-selection`,
`--structured-answers`, and `--canonical-selection`, each with `inherit`,
`on`, or `off`.

The previously passing candidate combination is:

```text
Query mode: Repository Overview
Overview claim selection: on
Structured repository answers: on
Canonical source selection: off
```

Local HTTP tests verify this combination and the Q2 structured path, plus
all eight control combinations, strict JSON validation, omitted values,
normal-mode isolation, and simultaneous requests with opposite structured
settings. This is a wiring/mechanics check. Equivalence to the prior 11/11
live result still requires a new pinned-generation HTTP run after deployment.
The follow-up was deployed at `f344bd58`. The
[production matched frozen comparison](/DOCS/test_results/2026-10-10-issue-240-per-request-controls-production-verification.md)
passed 11/11 with the controls above against a new ready generation from the
same source commit. The flag-off baseline passed 2/11.
