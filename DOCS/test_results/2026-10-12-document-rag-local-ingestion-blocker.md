---
title: "D0 local baseline: Markdown upload fails at the extractor contract"
date: 2026-10-12
type: test-result
status: blocked-by-markdown-ingestion-defect
tags: [document-rag, d0, ingestion, contract-regression]
related:
  - "[Frozen baseline protocol](/DOCS/evaluations/2026-10-12-document-rag-baseline.md)"
  - "[Failure evidence](/DOCS/test_results/2026-10-12-document-rag-ingestion-failure.json)"
  - "[Local runtime snapshot](/DOCS/test_results/2026-10-12-document-rag-local-runtime.json)"
  - "[Current status](/DOCS/status.md)"
---

# D0 local ingestion blocker

Docker availability resolved the infrastructure prerequisite, but the unchanged
Markdown document-upload path fails before the twelve-question baseline can run.
The first frozen upload receives HTTP **202 accepted**, then terminal **failed**.
The confirmed error is **`'ExtractionResult' object is not iterable`**.
This is an ingestion failure, not twelve failed answers or a retrieval score.

## Isolated setup and observed result

The [evaluation Compose file](/docker-compose.document-eval.yml) creates a separate
Docker project, `rag-foundry-document-eval`, with an isolated PostgreSQL database
`document_eval_test`. Its schema was migrated to head before service startup.
The four services use existing local images with current source mounted read-only
and loopback ports 8101-8104. Remote Ollama provides inference only; no production
ingestion or vector data is modified. Production database volumes and `.env` are
not used. Service dependencies were installed normally by the image entrypoints.

The [runtime snapshot](/DOCS/test_results/2026-10-12-document-rag-local-runtime.json)
records effective retrieval limits, default model `ollama/Qwen3:4b` / alias
`default`, `rag_answer.v1` source hash, model digests, image identities and source
hashes. Version fields are explicitly assigned for the mounted source; they do
not independently attest image contents or production configuration parity.

All four service health checks succeeded before the upload. The fresh ingestion
API reported an empty corpus. The [baseline runner](/scripts/document_rag_baseline.py)
checked the frozen manifest, then uploaded **operations.md** through local
`POST /v1/ingest/file`. Job **8022bcb0-af3f-4c89-8f34-e2fd80f14a39** moved from
accepted to failed. The service log names the failing interface. The local
repository listing remains empty. Preparation stopped immediately; the other
three files were not uploaded, and there were **zero answer requests**.

The [prepared-corpus record](/DOCS/test_results/2026-10-12-document-rag-prepared.json)
is marked `failed-ingestion`. The initial runner exited before persisting failed
admission details; those were recovered explicitly from terminal-status HTTP and
logs, with that retrospective recording noted. The runner now preserves failed
admission/status records automatically. No successful frozen run is overwritten.

## Localized cause

`MarkdownSectionExtractor.extract()` returns the language-agnostic
`ExtractionResult(symbols=[SymbolRecord, ...])` in
[markdown_extractor.py](/ingestion_service/src/core/extractors/markdown_extractor.py).
`IngestionPipeline.run_with_sections()` in
[pipeline.py](/ingestion_service/src/core/pipeline.py) assigns that result to
`artifacts` and directly iterates it, expecting dictionaries with `id`, `name`,
`parent_id`, `doc_type` and `text`. The structured result is not iterable; its
records also have a different identity/parent representation. Merely iterating
`.symbols` would leave the dictionary accesses and graph identities unresolved.

A pure extractor probe on all four frozen sources confirms the same return type
and iteration error without performing additional uploads. Symbol extraction
itself succeeds; the consumer contract fails before graph/embedding persistence.
Repository ingestion already consumes the IR through its graph assembly path,
which explains why repository re-ingestion succeeded while uploaded Markdown
fails. The upload path's existing successful HTTP admission is not ingestion
success.

Rich-document/Docling paths also call `run_with_sections`, so they warrant
coverage when repairing this interface. They were not executed here. PDF fallback
uses a separate path; this record does not claim all PDF/OCR ingestion fails.

## Decision and checks

**NO-GO for the twelve-question baseline; diagnose and repair the upload/IR
integration before proceeding.** Freeze a narrow ingestion compatibility fix
with regression coverage for module/section identities, parent relationships,
source text/table preservation and terminal status. Then rerun ingestion in a
clean isolated corpus before any answer-quality evaluation. Do not bypass
document upload, alter source-type filtering, increase retrieval volume, change
the model or tune prompts to mask this defect.

No runtime implementation is changed by this investigation. The questions,
fixture source bytes, scoring and acceptance gates remain frozen; #254 and #243
stay deferred. Native-format evaluation and the MCP pilot remain later gates.
The seven runner safety tests pass; Ruff and Pyright pass for the new helpers.
Those checks validate harness mechanics, not Markdown ingestion or answer quality.
Local evaluation containers are stopped after evidence capture; their diagnostic
data are retained, and production services are untouched.
