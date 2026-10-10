---
title: "Issue #240 C1 historical-note correction and frozen verification"
date: 2026-10-10
type: test-result
status: complete-with-provenance-follow-up
tags: [repository-overview, evaluation, source-authority, generation]
related:
  - "[Frozen overview protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[New-generation comparison](/DOCS/test_results/2026-10-10-issue-240-new-generation-http-comparison.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #240 C1 historical-note correction

## Diagnosis

The October 10 candidate C1 answer cited the requested note and correctly
described the `my_test_repo` subject-contamination incident, but omitted the
frozen requirement to label the note historical. Both baseline and candidate
placed the same note chunk first in final context. A generation-fenced
read-only vector fetch reproduced that chunk's saved SHA-256 and its explicit
phrase `historical/test-result material`; reconstructed retrieved-context
byte counts matched both saved manifests. The candidate's `explicit_source`
selection excluded no chunks, and the exact-source ordering rule did not
activate. The loss occurred when the model synthesized the answer, after
evidence delivery. The two saved outputs cannot establish whether conditional
prompt wording or model variability caused the omission.

The source provenance role was `documentation` with unknown validity. The
overview assessment identified the path as historical/evaluation material,
but only the assessment's overall status, not its per-source finding, was
rendered to the model. The generic instruction to label a historical source
was already present in both arms.

## Bounded correction and verification

The local candidate now adds an answer-side qualification only when an
`explicit_source` question names one unambiguous dated `DOCS/notes` source,
that exact note survived final context, and one of its surviving passages
explicitly says `historical`. It leaves ambiguous, unavailable, unlabeled,
and unrelated requests unchanged, and does not change retrieval, source
selection, chunk caps, or budgets. When the model already labels the note,
the qualifier is not duplicated. The response trace records the source and
whether the qualifier was added.

The [focused C1 HTTP repeat](/DOCS/test_results/2026-10-10-issue-240-c1-fix-focused.json)
used the same ready generation, `top_k=10`, `rerank=false`, and
`ollama/Qwen3:4b`. It recorded `historical_source_qualification.status=added`,
cited the requested note, and gave the correct subject-contamination answer.
Its before/after generation reads and RAG response all matched
`efd94377-679d-494d-84af-53b00c83f487`. This repeat was a focused
mechanism check, separate from the scored frozen pass.

The [full candidate JSON](/DOCS/test_results/2026-10-10-issue-240-c1-fix-candidate.json)
contains one complete HTTP pass of all 11 frozen cases on the same generation
and recorded corpus source commit `7a805d5b3cee031c44fbe0d9b8048065ce8ef039`.
All before/after generation reads matched. Q1-Q4 rendered with zero schema
validation errors and answers identical to the prior candidate. Q5 at both
Top K values, Q6, and Q7 kept the canonical purpose passage in final context
and citations and gave correct purpose answers. C1 kept the requested note,
explicitly labeled it historical, and correctly described the incident. C2
and C3 retained and cited their exact sources and answered correctly. The
candidate therefore passed **11/11 frozen answer/source checks** in this
local-on-remote comparison. Manifest canonical-ID order and cited sources
were unchanged in every case from the previous candidate run.

Local mechanics checks: orchestrator unit suite `311 passed, 37 deselected`;
focused overview-policy and structured-HTTP tests `27 passed`; Ruff and
Pyright passed for changed Python files. The local HTTP orchestrator was
stopped after capture. No remote deployment, ingestion, PR, or merge was
performed for the C1 correction.

The frozen answer-quality gate passes for this candidate on this generation.
The separate corpus-provenance limitation remains: the new generation still
reports the older source commit while its persisted Compose byte digests
differ from the earlier capture. This record does not claim the latest branch
was the ingested repository subject or that the C1 correction is deployed.

## Subsequent source-byte check

The [independent verification record](/DOCS/test_results/2026-10-10-issue-240-source-snapshot-verification.md)
later matched both production Compose digests to exact Git bytes at the
generation's recorded source commit `7a805d5b`. That resolves the narrow
Compose-byte uncertainty for this generation. The October 8 adapter used
different local bytes; the feature branch remains the candidate runtime,
not the proven ingested repository subject. Full-corpus provenance is still
outside this check.
