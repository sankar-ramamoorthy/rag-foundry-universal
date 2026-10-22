---
title: "D0: bounded document-RAG development baseline"
date: 2026-10-12
type: evaluation-protocol
status: blocked-by-markdown-ingestion-defect
tags: [document-rag, evaluation, d0, frozen-baseline]
related:
  - "[Deferred #254 decision](/DOCS/notes/2026-10-12-issue-254-deferred.md)"
  - "[Document research lessons](/DOCS/research/2026-10-04-document-intelligence-research-lessons.md)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Current status](/DOCS/status.md)"
---

# Bounded document-RAG development baseline

The isolated local stack is now available, but the
[first Markdown upload failed](/DOCS/test_results/2026-10-12-document-rag-local-ingestion-blocker.md)
at the extractor/consumer interface (`ExtractionResult` versus legacy dictionary
artifacts). HTTP admission succeeded; terminal ingestion failed. The other three
uploads and all twelve answer requests remain unexecuted. A narrow ingestion
compatibility repair is the next gate; do not expand to native formats or MCP yet.

Current [post-deployment preflight](/DOCS/test_results/2026-10-12-document-rag-post-deploy-preflight.md)
confirms the frozen sources were re-ingested as repository artifacts at `109f12d`,
but their sixteen root-document chunks are tagged `source_type: code` and excluded
by document RAG. This does not replace uploaded-file ingestion. No baseline
answers have been requested; an isolated document stack is still required.

The next workstream is D0 document evaluation. This initial corpus is a small
synthetic **development** benchmark, separate from #243's held-out repositories.
No model, prompt, retrieval, parser or architecture comparison is included.
Prepare expected evidence before observing answers; run once, record failures,
and make an explicit GO/NO-GO/INVESTIGATE decision before changing production.

## Corpus and bounded workload

The [fixture directory](/DOCS/evaluations/document-rag-d0/questions.json) contains
four Markdown documents: fictional Cedar operations, a service-level table,
current retention rules, and an explicitly obsolete retention distractor.
The files have no external licensing or factual verification dependency.
The questions fix twelve cases, source sections, factual obligations and
unsupported-question expectations. The [frozen manifest](/DOCS/evaluations/document-rag-d0/manifest.json)
records exact file hashes, checked with the
[freeze utility](/scripts/document_rag_freeze.py). All expected source headings
resolve. The utility passes Ruff and Pyright; this validates preparation,
not ingestion or retrieval behavior.
This is a controlled first baseline, not a representative real-document survey.

| Cases | Coverage |
| --- | --- |
| D01-D02 | Single-passage facts and responsible roles |
| D03-D04 | Table cells, units and threshold interpretation |
| D05-D06 | Joining evidence across documents |
| D07 | Retention schedule plus preservation exception/state |
| D08 | Current evidence versus obsolete distractor |
| D09-D10 | Staffing/deadline distinctions and cross-passage responsibility |
| D11-D12 | Unsupported facts and explicit abstention |

Exactly twelve end-to-end requests, in case-ID order, with no retries after a
successful response, answer-driven edits or adaptive tuning. Infrastructure
errors are recorded separately from incorrect answers; this is not a reliability
estimate from repeated trials. Pin ready/completed ingestion IDs, source bytes,
parser/chunker/embedding configuration, index contents and runtime/model/prompt
identities before execution; do not ingest or deploy on production for this run.

Use unchanged `/v1/rag/simple`, `top_k=5`, `rerank=false` and the existing default
model alias. Freeze the resolved model/template before the first answer and
reject model fallback or runtime/corpus changes during the run. Record all
effective limits and the model's stochastic defaults; do not invent a seed.
The local implementation defaults to `max_total_tokens=2048`, and its
`conservative_token_count` counts UTF-8 bytes, not tokenizer tokens. Its effective
budget is the minimum of that allowance and window-minus-reserves/query cost.
This document baseline therefore **does not inherit #254's 4096-byte cap**.
Deployed settings not exposed over HTTP are unknown until supplied/observed.

## Scoring, fixed before answers

Record each layer separately, rather than collapse failures into one score:

1. **Ingestion/representation:** upload acceptance, terminal status, elapsed
   time, expected section/table presence and original source-byte identity.
   HTTP 202 is not completed ingestion. Verify table row/header relationships,
   not merely numeric string presence.
2. **Retrieval and survival:** required source sections discovered and delivered
   in `final_context_manifest`; label evidence unobservable if the endpoint lacks
   the trace needed to distinguish retrieval loss from context loss. Final
   manifest absence alone does not identify the earlier failed stage.
3. **Factual correctness:** every declared obligation correct, with no relevant
   contradiction/invention. Report satisfied obligations and per-case full pass
   separately. D08 rejects obsolete retention values as current facts.
4. **Citation accuracy:** each substantive claim's actual citation resolves to
   delivered evidence and that evidence supports the claim. A returned `sources`
   list or correct ID alone is not a citation pass. Record absent/unsupported
   citations separately from factual correctness and role attribution.
5. **Abstention:** D11-D12 state that the requested information is unspecified
   and invent no number, fee or backup period.

A fully accepted case requires every applicable factual obligation, supported
citations and required delivered evidence; unsupported cases also require
abstention. Report denominators, raw answers, evidence manifests, timing and
limitations. Twelve API completions alone are not twelve behavioral passes.
If missing telemetry prevents a judgment, mark it **unobservable**, not passed.
No GO to a production change follows automatically from a baseline pass.

## Execution preflight and current boundary

Read-only deployed OpenAPI discovery is captured in
[API inventory](/DOCS/test_results/2026-10-12-document-rag-api-inventory.json).
There is no uploaded-document list endpoint. `/v1/rag/simple` exposes `repo_id`
in its request model, but the local route does not forward it to the service;
the service's vector search filters out code without selecting a corpus or
generation. Do not treat that field as demonstrated corpus isolation.
There is also no public per-document generation-pinning argument for this path.
These are preflight observations, **not proposed fixes**.

At initial preflight, the Docker engine was unavailable. It is now available and
the isolated local stack has been initialized, but the first upload fails as
recorded above. No document answers have been requested and **no end-to-end
score is claimed**. Execute on an isolated test
stack containing only these four documents. Alternatively, replace this initial
corpus before any answers with user-supplied original documents and ingestion
IDs, explicitly accounting for corpus-wide retrieval and distractors.
That alternative requires a separately frozen source manifest and questions.

PDF native-text extraction, scanned OCR, screenshots, merged cells, page-level
citations and large-document/OOM behavior are **unmeasured follow-up strata**.
Markdown table success must not be represented as PDF/table-parser reliability.
Reserve an independent real-document evaluation after this development baseline;
do not touch or relabel #243 datasets for document work.
