---
title: "Document Intelligence Research Lessons"
date: 2026-10-04
type: research-note
status: draft
scope:
  - document-rag
  - parsing
  - ocr
  - document-vision
  - page-intelligence
  - chunking
  - retrieval
  - provenance
tags:
  - rag
  - document-intelligence
  - ocr
  - parsing
  - docling
  - chunking
  - provenance
  - research
related:
  - "[[2026-10-04-repository-intelligence-research-lessons]]"
  - "[[08-RAG-Quality-Evaluation-Methodology]]"
---

# Document Intelligence Research Lessons

## Purpose

This note records document-only investigations carried out outside the main Codex/Claude implementation loop, primarily through independent ChatGPT analysis of:

- uploaded-document ingestion behavior,
- PDF and image parsing,
- OCR and document-vision options,
- hardware constraints,
- parser and model licensing,
- chunking and structure preservation,
- document retrieval failures,
- and external document-intelligence architectures.

This is **not an accepted architecture document** and does not automatically create roadmap work.

The goal is to preserve the reasoning behind ideas that may otherwise disappear from chat history, while clearly separating:

1. **evidence-backed findings**,
2. **promising experiments/hypotheses**,
3. **explicitly deferred ideas**.

The scope of this document is the **document intelligence path** only. Repository/code graph retrieval, ORIENT, TRACE, IMPACT, and repository authority policy are intentionally excluded and documented separately.

---

# 1. Core conclusion: document intelligence is not "OCR + chunks"

The document path originally looked roughly like:

```text
uploaded file
   ↓
Docling / OCR
   ↓
plain text or Markdown
   ↓
generic chunking
   ↓
embeddings
   ↓
vector retrieval
   ↓
LLM answer
```

The investigations increasingly point toward a more capable pipeline:

```text
uploaded file
   ↓
file/page inspection
   ↓
cheap structural/native parse
   ↓
page-quality assessment
   ↓
selective OCR / visual escalation
   ↓
structured page representation
   ↓
structure-aware chunking
   ↓
embeddings
   ↓
retrieval
   ↓
evidence-aware context construction
   ↓
LLM answer
```

The most important conceptual change is:

> The problem is not merely extracting text. The system must preserve enough document structure that the answer-bearing evidence remains coherent and retrievable.

That changes how OCR, parsing, chunking, page provenance, model selection, and evaluation should be designed.

---

# 2. Eager parsing of every page should not be assumed

A major research thread started from the observation that many document pipelines parse or OCR every page before anyone asks a question.

This can be unnecessarily expensive for large document collections, especially when:

- many pages are already machine-readable,
- only a small subset will ever be queried,
- some pages are much harder than others,
- OCR and visual parsing are the dominant resource consumers.

We investigated a **two-stage / just-in-time parsing** pattern:

```text
document
   ↓
cheap first pass
   ↓
layout/text/page complexity
   ↓
easy pages → keep cheap result
hard pages → escalate
```

The broader lesson was more important than any single product:

> Expensive OCR or visual document understanding should be an escalation stage, not automatically the mandatory first stage for every page.

---

# 3. Pure just-in-time OCR has a bootstrap problem

A fully lazy design has an important weakness.

If the cheap representation of a page is too poor, retrieval may never identify the page as relevant, so the system never learns that the page needs better OCR.

That produces:

```text
bad first-pass representation
       ↓
page never retrieves
       ↓
visual/OCR escalation never happens
```

## Lesson

The likely best compromise is **selective eager processing**:

```text
first pass
   ↓
quality assessment
   ↓
good page → accept
suspect page → OCR now
complex page → advanced parser / vision model
```

This preserves a minimum viable searchable representation while avoiding expensive processing everywhere.

---

# 4. LiteParse-style systems inspired a useful architectural split

We investigated LiteParse as an example of a fast structural first-pass parser.

The aspects that were attractive included:

- CPU-friendly implementation,
- Rust-based parsing,
- broad document-format support,
- layout-aware extraction,
- potential page-level complexity signals,
- suitability for a fast first pass.

The architectural lesson was not "replace Docling with LiteParse."

It was:

> Parsing, OCR escalation, and chunking should be explicit, independent stages.

A target flow could be:

```text
file
 ↓
fast structural parser
 ↓
page representation
 ↓
quality / complexity assessment
 ↓
optional OCR / VLM repair
 ↓
structure-aware chunking
```

This keeps the pipeline flexible enough to compare different first-pass parsers later.

---

# 5. OCR should be a capability boundary, not a hard-coded implementation

The investigation of Tesseract, PaddleOCR, RapidOCR, and visual document models suggested that OCR should eventually sit behind a provider abstraction.

Conceptually:

```text
OCR / DocumentVision Provider
   ├── Tesseract
   ├── PaddleOCR
   ├── visual document parser
   └── external hosted parser
```

Routing could depend on:

- document/page type,
- parser confidence,
- hardware availability,
- required fidelity,
- cost/latency constraints,
- explicit user mode.

## Lesson

Do not let one OCR library define the document architecture.

The system should be able to evolve provider choice independently from the rest of ingestion.

---

# 6. Tesseract remains useful as a baseline, but text accuracy is not enough

Tesseract is valuable because it is:

- local,
- CPU-friendly,
- mature,
- easy to operate,
- adequate for many ordinary scanned pages.

But document intelligence requires more than character recognition.

A page can be transcribed reasonably well while still losing:

- row/column relationships,
- reading order,
- headings,
- form structure,
- table cells,
- figure captions,
- layout hierarchy.

## Lesson

OCR quality must be evaluated on **information structure**, not only word accuracy.

---

# 7. The uploaded-image path exposed a concrete structure-loss problem

One of the most useful document-side experiments involved a screenshot containing tabular information.

The effective path was approximately:

```text
image
 ↓
Tesseract
 ↓
plain text
 ↓
generic chunker
 ↓
vector chunks
```

The visual table structure was not preserved.

Rows could split across chunks, which means facts that were clear visually became fragmented semantically.

This demonstrated:

> Correctly recognizing the words does not guarantee preserving the evidence.

For document RAG, the system must preserve meaningful structures such as:

- rows,
- columns,
- table blocks,
- headings,
- page grouping,
- reading order.

---

# 8. Structure-aware chunking is as important as parsing quality

Even an excellent parser can be undermined by a generic token-length chunker.

Example:

```text
table
  header
  row A
  row B
  row C
```

can become:

```text
chunk 1 → header + half row A
chunk 2 → rest of row A + row B
chunk 3 → row C
```

That destroys coherent retrieval units.

## Lesson

The parser should emit structured blocks, and the chunker should preserve those structures where possible.

Potential chunk units include:

- heading + section body,
- table as one unit,
- table row groups,
- paragraph groups,
- figure caption + associated text,
- page-level blocks,
- slide-level blocks,
- spreadsheet ranges.

The likely architecture is:

```text
structured parser output
        ↓
structure-aware chunker
        ↓
retrieval units
```

rather than flattening everything into text first.

---

# 9. Page-level provenance becomes necessary when parsing is heterogeneous

Once different pages can take different processing paths, document-level provenance is too coarse.

A document may look like:

```text
page 1 → native text
page 2 → Tesseract OCR
page 3 → visual parser
page 4 → native text
```

Useful provenance may need to capture:

- page number,
- parser/provider,
- OCR vs native text,
- confidence,
- bounding boxes,
- layout elements,
- escalation reason,
- parser version,
- perhaps image/raster settings.

## Lesson

Document provenance should become page- or region-aware when heterogeneous parsing is used.

This is important for:

- debugging,
- evaluation,
- confidence reporting,
- future reprocessing,
- explaining why pages have different fidelity.

---

# 10. Docling's internal OCR behavior exposed a real operational risk

Runtime investigation showed that Docling could initialize OCR internally, including RapidOCR behavior that was not fully represented in the simplified application-level mental model.

That matters because:

```text
application thinks:
PDF → Docling

runtime actually does:
PDF → Docling → internal OCR / rasterization
```

The resources consumed by that internal step still affect the ingestion service.

## Lesson

OCR policy must include parser-internal OCR behavior, not only explicit OCR calls made by the application.

---

# 11. A real OOM / Exit 137 event made resource controls non-optional

One document ingestion test ended with the ingestion container being killed:

```text
ExitCode 137
OOMKilled
```

The failure occurred after OCR-related work began.

This turned memory management from a theoretical optimization into a correctness/reliability requirement.

## Consequences

Document ingestion needs explicit controls for:

- page rasterization size,
- DPI,
- concurrent pages,
- OCR batch size,
- model memory,
- container memory,
- fallback behavior.

A document parser that can unpredictably kill the ingestion service is not production-safe.

---

# 12. HTTP 202 is not ingestion success

The OOM case also exposed a lifecycle problem.

A request could be accepted:

```text
POST upload
→ 202 Accepted
```

and then fail later during OCR or parsing.

That creates risks:

- ambiguous status,
- incomplete vectors,
- partial chunks,
- user believes document is ready,
- later RAG produces blank/incomplete answers.

## Lesson

Document ingestion status should expose real lifecycle stages:

```text
accepted
parsing
ocr
chunking
embedding
persisting
ready
failed
```

Failure details should identify the stage.

Acceptance of a background job is not equivalent to successful ingestion.

---

# 13. Selective OCR should likely expose an explicit user mode

A practical product/API pattern discussed was:

```text
ocr_mode = auto | force | off
```

### `auto`

Use page-quality signals to decide whether OCR is needed.

### `force`

Useful when the user knows the source is scanned, damaged, or otherwise poorly represented.

### `off`

Useful when OCR cost, privacy, fidelity, or resource limits make OCR undesirable.

## Lesson

Automatic policy is useful, but users/operators should have an escape hatch.

---

# 14. PaddleOCR required hardware-specific skepticism

We investigated whether PaddleOCR was a practical upgrade path on the available Linux GPU:

```text
GTX 1080 Ti
11 GB VRAM
Pascal / SM61
```

The key concern was not simply VRAM.

Recent PaddlePaddle/CUDA combinations may not cleanly support older Pascal compute capability.

Additional concerns included:

- API changes in PaddleOCR 3.x,
- PP-StructureV3 being substantially heavier than simple OCR,
- potential VRAM pressure,
- installation success not proving GPU kernel compatibility.

## Lesson

GPU OCR compatibility must be validated on the actual target hardware.

Do not infer support from model size or CUDA availability alone.

PaddleOCR remains a candidate, not a default.

---

# 15. Visual document models became more interesting than "better OCR"

The structure-loss experiments shifted the comparison criterion.

Instead of asking:

> Which OCR engine recognizes text most accurately?

we started asking:

> Which system produces the most useful structured representation for downstream retrieval?

That led to investigation of systems/models such as:

- WeVisDoc,
- MinerU,
- GOT-OCR,
- PaddleOCR-VL / PP-Structure variants,
- DeepSeek-OCR-style approaches,
- Jina OCR and similar visual parsers.

The desired output increasingly became:

```text
page
 ↓
structured Markdown / blocks
 ↓
tables + layout + reading order
```

rather than plain OCR text.

---

# 16. WeVisDoc became a particularly interesting local candidate

WeVisDoc stood out because it appeared capable of:

- visual document understanding,
- structured Markdown output,
- tables/layout/formulas,
- relatively modest model size,
- permissive licensing,
- plausible local deployment.

Most importantly, it was tested on the available GTX 1080 Ti under constrained settings and appeared feasible.

A representative run used roughly 9 GB of VRAM, leaving limited but workable headroom on the 11 GB card.

## Lesson

A useful deployment model is likely:

```text
one difficult page
      ↓
visual document model
      ↓
structured result
```

not:

```text
entire document room
      ↓
large concurrent visual inference
```

Resource limits must shape how these models are used.

---

# 17. Model serving defaults must be constrained for older GPUs

Large-context and high-concurrency serving defaults can be dangerous on 11 GB hardware.

Settings designed for large modern GPUs can cause immediate OOM even when the underlying model itself fits.

## Lesson

For local document vision:

- process one or very few pages concurrently,
- bound context length,
- bound image resolution,
- avoid aggressive batching,
- measure peak VRAM,
- prefer predictable latency over maximum throughput.

---

# 18. Licensing is a first-order architectural constraint

Some technically impressive OCR/document models carry non-commercial or otherwise restrictive licenses.

That matters because RAG-FOUNDRY-UNIVERSAL may eventually be used beyond personal experimentation.

## Lesson

Parser/model evaluation should include license at the beginning.

A candidate should be evaluated on:

```text
quality
hardware fit
latency
memory
operability
license
```

A slightly weaker Apache/MIT-compatible model may be strategically better than a stronger non-commercial model.

---

# 19. A separate document-vision service is a strong architectural candidate

Heavy OCR and visual parsing libraries can bring:

- CUDA dependencies,
- framework conflicts,
- large memory footprints,
- process crashes,
- model-specific serving requirements.

That argues for isolating them behind a service boundary:

```text
ingestion_service
       ↓
document_vision_service
       ↓
OCR / visual providers
       ↓
structured page result
```

## Benefits

- ingestion API remains lighter,
- GPU failures are isolated,
- CPU-only deployments can omit the service,
- provider upgrades are independent,
- remote GPU use becomes possible,
- resource limits are easier to manage.

This is one of the document-side ideas that has matured enough to deserve roadmap consideration.

---

# 20. Deterministic routing should precede learned OCR routing

We considered whether a small decision model could choose among parsers.

Potential choices might include:

```text
native parse
Tesseract
visual parser
fallback provider
```

But the routing problem can initially be driven by deterministic signals such as:

- native text exists,
- text density,
- OCR confidence,
- image coverage,
- layout complexity,
- parser warnings,
- table detection,
- garbage-character ratio.

## Lesson

Start with deterministic page-quality rules.

Use a learned router only if those rules prove inadequate.

This mirrors the evidence-first principle used elsewhere in the project.

---

# 21. Page-quality assessment is a missing architectural layer

Selective parsing requires a mechanism to decide whether a page is "good enough."

Possible signals include:

```text
native text length
text density
image ratio
OCR confidence
layout complexity
table count
parser warnings
reading-order anomalies
garbage-character ratio
```

A possible decision policy:

```text
good
→ accept native/cheap representation

suspect
→ OCR

complex
→ visual parser

failed
→ alternate provider / explicit failure
```

## Lesson

Page-quality assessment is likely a roadmap-worthy capability because it links all parser/OCR providers into one coherent policy.

---

# 22. Parser benchmarks should measure downstream RAG usefulness

A parser can score well on OCR benchmarks while still producing poor retrieval units.

The evaluation should include representative hard cases:

- born-digital PDFs,
- scans,
- low-resolution pages,
- multi-column layouts,
- tables,
- forms,
- screenshots,
- formulas,
- mixed image/text pages.

Useful metrics include:

```text
text correctness
reading order
table preservation
layout fidelity
page latency
RAM
VRAM
failure rate
chunk coherence
retrieval recall
answer correctness
```

## Lesson

The winning parser is the one that preserves useful evidence through the full RAG pipeline, not necessarily the one with the best isolated OCR score.

---

# 23. Parser quality and chunker quality must be evaluated together

A structured parser can produce excellent page output that a poor chunker subsequently destroys.

Therefore parser bake-offs should include:

```text
parser
   ↓
actual chunker
   ↓
actual embedder
   ↓
actual retrieval
```

not only parser output inspection.

This is an important methodological requirement.

---

# 24. Context competition also affects document RAG

Document-side evaluation exposed a case where the correct passage was present, but the model selected a competing numerical value from another plausible passage.

This means document RAG can fail even with successful retrieval.

Potential causes include:

- similar chunks,
- duplicate facts,
- conflicting values,
- context ordering,
- weak source labeling,
- model limitations.

## Lesson

Correct retrieval is necessary but not sufficient.

Context construction should be evaluated independently from retrieval.

---

# 25. Reranking was not justified by the measured failure pattern

External RAG architectures often include a reranker.

We considered it seriously.

However, the known evaluation did not show a strong pattern of correct evidence sitting at intermediate ranks waiting to be rescued.

In the most interesting failure, the correct evidence was already high enough.

## Lesson

Do not add reranking merely because it is common in modern document RAG.

Use it when candidate ranking is actually the measured failure.

---

# 26. Embedding replacement should remain a controlled experiment

Newer embedding models may improve document retrieval.

But changing embeddings requires:

- re-embedding the corpus,
- potentially changing vector dimensions,
- rebuilding indexes,
- retesting latency/memory.

## Proposed comparison

Use the same corpus and question set, then compare:

```text
Recall@5
Recall@20
MRR
latency
memory
table/document behavior
```

Until a controlled test shows a material gain, the current embedder should remain.

---

# 27. Page-level retrieval is a promising future direction

The just-in-time parsing discussion suggested that retrieval might eventually operate over lighter page/region representations before invoking expensive parsing.

Conceptually:

```text
document
   ↓
page/region index
   ↓
cheap searchable representation
   ↓
query identifies likely page
   ↓
high-fidelity parser invoked if needed
```

This could be powerful for large ad-hoc document rooms.

But the cheap first-pass representation must be strong enough to retrieve the page.

## Lesson

Treat this as **progressive refinement**, not pure lazy OCR.

---

# 28. Embedding throughput can dominate end-to-end ingestion

A parser can be extremely fast while total ingestion remains slow because embeddings dominate.

An earlier baseline suggested only a few chunks per second under some local CPU-oriented conditions.

Therefore document performance should be broken into:

```text
parse
OCR
visual repair
chunking
embedding
vector persistence
```

## Lesson

Optimize the measured bottleneck, not whichever stage looks most sophisticated.

---

# 29. CPU-friendly should mean "functional baseline," not "all advanced parsing is cheap"

The project has often emphasized CPU-friendly operation.

The investigations refined that goal.

A more realistic deployment philosophy is:

```text
CPU-only
→ functional baseline

CPU + optional GPU document vision
→ better difficult-page fidelity

remote/provider-backed vision
→ higher-end scalability
```

This preserves accessibility while acknowledging that advanced document understanding benefits from acceleration.

---

# 30. Document parsing should preserve uncertainty

A parser can fail in different ways:

- text absent,
- layout uncertain,
- table incomplete,
- OCR confidence low,
- page partially parsed.

The system should not silently convert uncertain extraction into confident evidence.

Useful states may include:

```text
native
ocr-derived
visual-derived
partial
low-confidence
failed
```

This is analogous to explicit unknown/not-established semantics in repository intelligence.

---

# 31. Progressive processing should preserve reprocessing ability

If parser quality improves later, the system should be able to reprocess only affected pages/documents.

This suggests storing enough provenance to know:

- parser used,
- parser/model version,
- page-level result,
- source snapshot/file hash,
- downstream chunk lineage.

## Lesson

Future parser upgrades should not require treating every document as an opaque one-time ingestion.

---

# 32. Hosted document parsers are useful references, not mandatory architecture

External hosted systems can provide excellent parsing quality.

They are useful for:

- benchmarking,
- validating difficult pages,
- understanding what high-end parsers can preserve,
- comparing local output.

But they should not automatically become hard dependencies.

Reasons include:

- privacy,
- cost,
- vendor coupling,
- network availability,
- enterprise deployment requirements.

## Lesson

Hosted parsers are candidate providers and benchmark references, not necessarily the default architecture.

---

# 33. External posts and repositories should generate hypotheses, not backlog items

The document investigation was repeatedly inspired by:

- LinkedIn posts,
- GitHub projects,
- architecture diagrams,
- screenshots,
- benchmark announcements,
- model releases.

These were useful because they exposed possible approaches:

- just-in-time OCR,
- selective parsing,
- visual document models,
- parser routing,
- structured Markdown,
- OCR providers,
- page-level escalation.

But the mature rule is:

> What measurable failure in RAG-FOUNDRY-UNIVERSAL would make this technique necessary?

Examples:

### Advanced visual parser

Adopt when:

```text
plain OCR / current parser repeatedly loses answer-bearing structure
```

### Learned parser routing

Adopt when:

```text
deterministic page-quality rules repeatedly choose poorly
```

### Reranker

Adopt when:

```text
correct document/chunk repeatedly appears below the final retrieval cutoff
```

### New embedding model

Adopt when:

```text
controlled evaluation shows a material retrieval gain worth full re-embedding
```

### Pure JIT OCR

Adopt only when:

```text
cheap first-pass retrieval can reliably locate pages that still need expensive parsing
```

---

# 34. Evidence-backed roadmap implications

The following capabilities have enough evidence to deserve roadmap consideration.

## 34.1 Bounded OCR and raster resource controls

Because a real OOM/Exit 137 occurred.

## 34.2 Observable document-ingestion lifecycle

Because request acceptance did not guarantee successful completion.

## 34.3 Page-level provenance

Because multiple processing paths are likely.

## 34.4 Structure-preserving page representation

Because plain OCR + generic chunking demonstrably loses useful structure.

## 34.5 Structure-aware chunking

Because parser gains can otherwise be destroyed downstream.

## 34.6 OCR/document-vision provider abstraction

Because hardware, quality, licensing, and deployment needs differ.

## 34.7 Selective page escalation

Because both full eager OCR and pure lazy OCR have clear drawbacks.

## 34.8 Page-quality assessment

Because selective escalation requires explicit decision logic.

## 34.9 Representative document benchmark suite

Because parser selection should be driven by downstream retrieval/answer quality.

## 34.10 Optional external document-vision service

Because GPU-heavy parsing should be isolated from the main ingestion process.

---

# 35. Investigation-worthy ideas that should not yet become committed roadmap work

These remain promising but conditional:

- LiteParse as the specific first-pass parser,
- WeVisDoc as the default visual parser,
- PaddleOCR / PP-Structure,
- MinerU,
- GOT-OCR,
- DeepSeek-style OCR,
- hosted parser providers,
- learned parser routing,
- page-level query-time refinement,
- alternative embeddings,
- reranking.

Each requires a focused experiment and decision gate.

---

# 36. Explicit deferrals

The current evidence does **not** justify immediately:

- sending every page through a visual model,
- replacing all OCR with PaddleOCR,
- replacing Docling without comparative evaluation,
- pure query-time OCR with no eager searchable fallback,
- learned routing before deterministic quality signals are tested,
- always-on reranking,
- automatic embedding replacement,
- hosted parsing as a mandatory dependency.

---

# 37. Recommended design principles

The accumulated document investigations suggest these working principles.

1. **Preserve document structure, not only text.**
2. **Treat expensive OCR/vision as selective escalation.**
3. **Keep a searchable baseline representation for every relevant page.**
4. **Make OCR/document vision provider-pluggable.**
5. **Measure parser quality through downstream retrieval and answer quality.**
6. **Keep page-level provenance when processing paths differ.**
7. **Bound rasterization, concurrency, RAM, and VRAM explicitly.**
8. **Do not equate 202 Accepted with successful ingestion.**
9. **Use structure-aware chunking after structured parsing.**
10. **Keep deterministic page-quality routing before learned routing.**
11. **Treat licensing and hardware support as first-order selection criteria.**
12. **Separate parser quality, chunking quality, embedding quality, and generation quality during evaluation.**
13. **Optimize measured bottlenecks, not fashionable components.**
14. **Preserve uncertainty and partial parsing states.**
15. **Require new components to correspond to measured failure modes.**

---

# 38. Working target architecture

The accumulated lessons point toward this document-intelligence flow:

```text
Uploaded document
       │
       ▼
File type + source inspection
       │
       ▼
Cheap/native structural pass
       │
       ▼
Page-quality assessment
       │
       ├── good → accept
       ├── suspect → OCR
       ├── complex → visual parser
       └── failed → fallback / explicit failure
       │
       ▼
Structured page representation
       │
       ├── text
       ├── headings
       ├── tables
       ├── reading order
       ├── page / region identity
       ├── confidence
       └── provenance
       │
       ▼
Structure-aware chunking
       │
       ▼
Embedding + vector persistence
       │
       ▼
Document retrieval
       │
       ▼
Evidence-aware context construction
       │
       ▼
LLM synthesis
```

Optional heavy processing can live behind:

```text
document_vision_service
       │
       ├── Tesseract
       ├── local visual model
       ├── future OCR provider
       └── hosted parser
```

The key idea is:

> document understanding should progressively increase fidelity only where evidence quality requires it.

---

# 39. Roadmap reorientation implications

The next roadmap should treat document intelligence as its own capability track rather than a collection of OCR utilities.

A more accurate document-intelligence sequence is:

```text
1. Ingestion reliability and resource bounds
2. Page-level provenance and lifecycle observability
3. Structured page representation
4. Structure-aware chunking
5. Selective OCR / visual escalation
6. Parser-quality decision logic
7. Document benchmark/evaluation harness
8. Retrieval/context-quality improvements
9. Provider abstraction / optional GPU service
10. Scale and productization
```

This track should later be reconciled with:

- repository intelligence,
- shared evaluation methodology,
- common embedding/vector infrastructure,
- shared model/provider infrastructure.

---

# 40. Status of this note

This document intentionally contains a mixture of:

- measured findings,
- architectural lessons,
- hypotheses,
- and explicit deferrals.

It is **research input**, not a specification.

Before any item becomes implementation work, it should be promoted through the project’s normal evidence-first process:

```text
observed failure
    ↓
focused experiment
    ↓
measured result
    ↓
decision
    ↓
issue / ADR / roadmap item
```

That discipline is as important on the document side as it is on the repository side.
