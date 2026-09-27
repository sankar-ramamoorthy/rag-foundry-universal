---
title: "Deliberate Repetition of Experiments as Architectural Evidence"
type: brainstorm
status: raw
tags: [brainstorm, evaluation, experiments, document-ingestion, roadmap]
created: 2026-09-27
related:
  - "/DOCS/audit/07-Roadmap.md"
  - "/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md"
  - "/DOCS/status.md"
source:
  - "C:\\Users\\bosto\\Downloads\\ocr-document-vision-history-and-prior-decisions.md"
  - "C:\\Users\\bosto\\Downloads\\2026-09-27-image-table-ingestion-investigation.md"
---

# Deliberate Repetition of Experiments as Architectural Evidence

## Trigger

Two summaries of prior OCR/document-vision work and a new WMI screenshot
table-ingestion investigation were reviewed against the project roadmap.
The project has moved from proving that individual components can run to
making architectural choices that need measured, reproducible evidence.

## Raw Input

> Earlier, repeating an experiment could look like wasted effort because we
> were primarily proving that components worked. Now we're making
> architectural choices, so reproducibility and controlled repetition become
> part of the evidence.
>
> For example, I would absolutely rerun the earlier WeVisDoc experiments.
> This time the question is no longer simply "Can WeVisDoc-2B run on a 1080
> Ti?" We already demonstrated that. The questions are now:
>
> - Does it preserve the WMI table correctly?
> - What exactly does its raw output look like?
> - Can we convert that output into stable structural objects?
> - Does that structure survive chunking and retrieval?
> - What happens at 100/120/150 DPI?
> - What are repeat-run latency and peak VRAM?
> - What happens on difficult pages, malformed tables, mixed prose/tables,
>   receipts, and scans?
> - How does it fail, and can the system recognize that failure?
>
> Similarly, repeating a Docling experiment now has different value. We can
> compare Docling's native structured document object vs
> `export_to_markdown()` vs what eventually reaches our chunks. That's a
> much better experiment than simply asking whether Docling can extract a
> PDF.
>
> I'd use a principle going forward:
> Do not repeat experiments accidentally. Repeat them deliberately when the
> question, instrumentation, environment, acceptance criteria, or
> architectural decision has changed.
>
> And we're definitely at that point. The Red/Blue work has pushed the system
> beyond proving individual components. We should increasingly demand
> measured evidence before architectural changes, including rerunning earlier
> tests under the new requirements.
>
> I would also revise the historical note's wording from "don't repeat
> experiments" to "don't unknowingly repeat experiments; use prior results to
> design better repetitions."

## Observations

- The historical OCR note records a successful WeVisDoc-2B run on a GTX 1080
  Ti at about 120 DPI, with observed GPU memory near 9 GB and higher-resolution
  tests around 150/200 DPI reported as possible OOM cases. It also records
  good receipt/table observations and weaker chart semantics. These are
  prior observations, not evidence for the proposed structure-preserving
  ingestion contract.
- The WMI PNG was processed by the current image route: Tesseract returned
  plain text, then generic chunking split logical table rows across chunks.
  Docling did not process this PNG.
- The current `DoclingConverter` returns Markdown from
  `result.document.export_to_markdown()`; its richer native document object
  is not propagated through that interface. Comparing native structure,
  Markdown, and downstream chunks would answer a new architectural question.
- The existing roadmap places evidence-driven retrieval experiments at Phase
  6 item #201 and JIT OCR/selective heavy-parse escalation at item #204. The
  latter does not explicitly name structure-preserving extraction or
  downstream structure survival as evaluation requirements.
- `DOCS/audit/09-Retrieval-Technique-Decision-Gates.md` already requires
  project-specific measured evidence before adopting retrieval techniques.
  The new principle generalizes that discipline to deliberate repetitions
  and architectural evaluations beyond retrieval.
- According to `DOCS/status.md`, #200 Stage A and #199 Stage B, plus the #200
  Stage C follow-up, have implementation and production verification recorded.
  The formal frozen #200 evaluation gate remains open. The roadmap still
  shows #199 and #200 unchecked, so its checklist should not be read as the
  freshest completion record.

## Ideas

- Revise the historical OCR note's warning to: "Do not unknowingly repeat
  experiments; use prior results to design better repetitions." Keep prior
  results and their environment visible as baselines, not as a reason to
  avoid a new experiment when the decision or acceptance criteria changed.
- Add the deliberate-repetition principle to #201's experiment process,
  covering a changed research question, instrumentation, environment,
  acceptance criteria, or architectural decision as valid reasons to rerun.
- When planning #204, include a controlled document-vision evaluation that
  compares provider output and native document structure through normalized
  structure, chunks, retrieval, and answer evidence.
- Use the WMI PNG as a fixed regression fixture, but include a broader fixed
  set: prose-only pages, simple and dense tables, merged/grouped cells,
  mixed prose and tables, born-digital and scanned PDFs, receipts, and a
  chart case scored separately.
- Record raw outputs, repeat-run latency, peak RAM/VRAM, resolution/DPI,
  failure behavior, and whether extraction failures are recognized. Measure
  table/cell relationships and downstream evidence survival, not just
  non-empty text or character accuracy.
- Keep external document vision provider-neutral in the core design. Treat
  WeVisDoc-2B as an initial candidate; do not infer from the successful
  hardware run that it is accepted as the production provider.

## Questions

- Should #201 own a general repeat-experiment protocol, with #204 referring
  to it, or should #204 carry its own experiment protocol as well?
- Which historical OCR note is the exact target for the wording revision,
  and should the original note remain immutable with a dated correction or
  be edited in place?
- What constitutes stable structural output for comparison: normalized
  internal objects, provider-native output plus normalized objects, or both?
- Which repeat counts and page-resolution conditions are needed to report
  meaningful latency and VRAM variation on the 1080 Ti?
- What measurable threshold should define preservation of a table row and
  successful recovery of its header-to-cell relationships?
- How should this document-ingestion work be sequenced with current Phase 6
  work, including the still-open formal #200 evaluation gate?

## Concerns

- The successful WeVisDoc hardware run answers a feasibility question, not
  table fidelity, output normalization, chunk survival, retrieval quality,
  repeatability, or production reliability.
- Lower character error rate can coexist with broken row/cell associations.
- A one-page WMI regression fixture can expose the known failure but cannot
  alone establish robust behavior across tables, scans, receipts, and mixed
  layouts.
- Image ingestion and PDF/Docling ingestion currently take different paths;
  the PNG result must not be presented as a Docling failure.
- CPU fallback, GPU memory bounds, timeouts/OOM handling, provider
  replacement, and reprocessing/versioning remain specification questions.
- Charts and visual semantics need separate evaluation; OCR/table success
  does not establish chart understanding.

## Possible Next Outputs

- Update #201's experiment guidance with the deliberate-repetition
  principle and refer to prior evidence when designing repetitions.
- Refine #204's evaluation scope to cover structure-preserving extraction
  and its survival through chunking and retrieval, then specify before
  implementation.
- Update the historical OCR note's wording while preserving its recorded
  results and context.
- Prepare a fixed document fixture set and a pre-registered evaluation
  question set before rerunning WeVisDoc and Docling comparisons.
- No provider or schema decision until the controlled evaluation is
  specified and its results are recorded.
