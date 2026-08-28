---
title: "Retrieval Technique Decision Gates — External Ideas as Hypotheses"
date: 2026-08-27
type: decision-gates
status: living
tags:
  - audit
  - retrieval
  - decision-gates
  - constitution
  - rag-foundry
related:
  - "[[00-Audit-Overview]]"
  - "[[04-Scalability-Plan]]"
  - "[[08-RAG-Quality-Evaluation-Methodology]]"
  - "[[06-LLM-Provider-LiteLLM-Plan]]"
  - "[[03-Multi-Language-Graph-Plan]]"
---

# 🚦 Retrieval Technique Decision Gates

> [!abstract] Purpose
> A durable place to record retrieval/generation architecture ideas
> encountered outside this repo — in other RAG systems, papers, vendor docs,
> conversations — without letting them enter the roadmap by osmosis. This
> document is deliberately **not** part of `07-Roadmap.md` and is not itself
> a work package. It exists so an idea can be captured once, cheaply, and
> revisited later against actual evidence, instead of being either forgotten
> or implemented because it sounded reasonable somewhere else.

## Principle

> External architectures are sources of hypotheses, not backlog instructions.
>
> A technique enters the implementation roadmap only after a measured
> failure mode makes it relevant and an issue/spec defines how its value
> will be evaluated.

This document operationalizes the project constitution's **Principle III —
Evidence Before Retrieval/Generation Architecture Changes** prospectively:
Principle III governs changes already under consideration; this document is
where ideas live *before* they're under consideration, so Principle III has
something concrete to gate once they are. It does not restate Principle III,
`08-RAG-Quality-Evaluation-Methodology.md`'s reranker decision gate, or
`04-Scalability-Plan.md`'s `WP-S8` — see those documents for the mechanics.

## Status categories

Every row below carries one of four statuses. These are not stages of a
pipeline a technique automatically advances through — most rows should stay
`hypothesis` indefinitely, and a `deferred` item can stay deferred forever if
nothing ever surfaces the failure mode it would address.

| Status | Meaning |
|---|---|
| **validated** | Supported by this project's own measured evidence (a `DOCS/test_results/` entry or equivalent), scoped strictly to what was actually measured — not a license to generalize further without more evidence. |
| **investigate** | Our own evidence shows a relevant failure mode exists, but does not yet establish what the fix should be or where it belongs. A filed issue about the *finding* is not the same as authorization for an *implementation*. |
| **hypothesis** | A potentially useful idea from outside this project, with no supporting evidence yet from this project's own corpus or evaluations. |
| **deferred / NO-GO** | Evaluated, or clearly considered, and currently not justified. Revisiting requires new evidence, not renewed enthusiasm. |

## Decision gate table

| Technique | Status | Current position | Reconsider when |
|---|---|---|---|
| **Graph-aware expansion** (vector seed + deterministic BFS traversal) | validated (bounded) | Validated at initial WP-Q0 scale: raw-vector Recall@5 measured 70% vs. 90% for the production vector+graph path on the WP-Q0 corpus (`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`). | Continue measuring as corpus size, repository diversity, and language coverage increase ([[03-Multi-Language-Graph-Plan]]). Do not generalize this one result beyond the evaluated corpus without further evidence. |
| **Reranking** | deferred / NO-GO | NO-GO per the WP-Q0 reranker decision gate (issue #49). See [[04-Scalability-Plan#WP-S8 — Retrieval quality/perf at scale\|WP-S8]] and [[08-RAG-Quality-Evaluation-Methodology#4 · Reranker decision gate\|the methodology's gate]] for the mechanics — not restated here. | A non-trivial set of failures has the correct evidence retrieved but ranked below the context cutoff, especially roughly ranks 8–20. WP-Q0 had 0/10 such cases. |
| **Hybrid lexical + vector retrieval** (BM25 / full-text / RRF or similar) | hypothesis | Not evaluated; not implemented. | Exact identifiers, configuration names, APIs, symbols, or other lexical targets repeatedly exist in the corpus but are absent from, or poorly ranked in, semantic retrieval results. Measure this directly — it is a new evaluation, not an extension of the existing WP-Q0 pass. |
| **Embedding-model migration** | hypothesis (high migration cost) | Not evaluated. Current baseline is `mxbai-embed-large` (1024-dim) per ADR-039/ADR-040. | A controlled evaluation shows another model materially improves retrieval quality on representative code/document/multilingual workloads, compared directly against the current baseline. Any change requires re-embedding and per-index model tagging per Constitution Principle V and [[06-LLM-Provider-LiteLLM-Plan]] §5 — never a silent swap. |
| **Context deduplication** | investigate | Evidence-backed investigation candidate. Issue #65 (near-duplicate module/sole-child chunk crowding) is filed and measured, but the right fix location is not yet decided. | Duplicate/near-duplicate candidates consume meaningful top-k/context budget, or start contributing to actual failures — WP-Q0 measured a mean of 4 duplicate candidate slots per code question without one causing a failure yet (issue #65). Determine whether the intervention belongs at ingestion, retrieval, or final context assembly before implementing any of them. |
| **Context assembly / distractor handling** | investigate | Evidence-backed investigation candidate. WP-Q0's Q7 is the concrete example: production failed despite correct evidence already ranked top-3; the same generation path (`llm_service` `/generate`) passed twice with clean, hand-picked context (`DOCS/test_results/2026-08-27-wp-q0-rag-quality-baseline.md`, Scenario 3). | Correct evidence is highly ranked but answers fail because competing context causes conflation or selection of the wrong fact. Candidate interventions (chunk ordering, source grouping/labels, pruning, explicit conflict-resolution instructions, etc.) must each be evaluated against the methodology, never assumed to work. |
| **Hierarchical routing / index partitioning** | hypothesis (future scale) | Not evaluated; no current evidence of need. | Corpus scale or domain diversity makes broad retrieval measurably noisy, expensive, or slow, and metadata/domain narrowing demonstrably improves candidate quality or latency in a real measurement. Do not build for hypothetical 10M-document scale ahead of that evidence — see [[04-Scalability-Plan]]'s measure-first discipline. |
| **Agentic / LLM retrieval routing** | deferred | Considered and deferred. The current retrieval path is deterministic (vector seed + typed-edge BFS) per ADR-045. | Deterministic routing can no longer express the required retrieval policy, *and* evaluation demonstrates an LLM/agent router improves results enough to justify its added latency, nondeterminism, complexity, and evaluation burden. |

## How this document is used

- **Adding an idea:** append a row with status `hypothesis` (or
  `investigate` if it's already backed by a specific measured finding) and a
  one-sentence "reconsider when" condition. No issue, spec, or roadmap entry
  is required to *record* a hypothesis here — that is the point of keeping
  this list separate from `07-Roadmap.md`.
- **Promoting an idea:** a row only moves toward `validated`, or off this
  table into the roadmap, when its "reconsider when" condition is met with
  cited evidence (a `DOCS/test_results/` entry, or an issue with measured
  findings attached) **and** a GitHub issue/spec defines how the change will
  be evaluated (Constitution Principles VI and VIII). Update the row in
  place and say what changed and why — don't delete the record of what the
  position used to be, the way `00-Audit-Overview.md`'s dated status
  overlays don't erase the audit underneath them.
- **This document does not itself authorize implementing anything in it.**
  It is a gate, not a queue.

## Non-goals of this document

- It is not `07-Roadmap.md`, and nothing here should be copied into that
  file without going through the promotion step above.
- It does not restate the WP-Q0 evidence, the reranker decision gate, the
  embedding lifecycle rules, or the constitution's principles — see the
  linked documents for those. If this document ever appears to conflict
  with one of them, the linked document is authoritative; fix the conflict
  here, don't silently pick a side.
- It is not a bug tracker. Issue #64 (the code-query seed filter's
  `doc_type` match never firing) is a plain correctness defect surfaced
  during WP-Q0, not an external technique under evaluation — it stays in
  the normal bug-fix workflow and is out of scope for this table. Issue #65
  appears above because it backs a genuine technique-level question (where
  should deduplication happen), not because every WP-Q0 finding belongs
  here.
