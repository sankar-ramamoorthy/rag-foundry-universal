---
title: "What Ask (D1) is designed to answer: capability boundary, as of 2026-11-26"
date: 2026-11-26
type: note
status: current
summary: "Status snapshot, 2026-11-26 22:49 EST (owner-stated). Ask is one predetermined retrieval-and-expansion pass followed by one model call: evidence retrieval and synthesis, not iterative investigation. Records which question classes fit that design, what a stronger model can and cannot change, three corrections to the outside analysis this was reviewed from, and the open boundary question. Descriptive only: no proposals, no changes."
tags: [ask, rag, capability-boundary, architecture, d1, investigation]
related:
  - "[Code intelligence retrieval failure: evidence from 2026-11-11](/DOCS/notes/20261111-code-intelligence-retrieval-failure-evidence.md)"
  - "[ADR-045 hybrid vector-graph RAG](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md)"
  - "[LAB boundary and communication folder](/DOCS/notes/20261120-lab-boundary-and-communication-folder.md)"
  - "[Status](/DOCS/status.md)"
---

# What Ask (D1) is designed to answer

Recorded 2026-11-26, 22:49 EST (time stated by the owner), after a
read-only architecture review of L1 (logical), P1 (physical) and D1 (Ask
data flow). Scope: code repositories, ingestion complete, lab, documents and
OCR excluded. **Nothing here proposes a change.** The simplification
assessment is deliberately not started.

The analysis below began as an outside (ChatGPT) assessment. It was checked
against the code and this repository's own evidence; where it differed, the
difference is recorded under "Corrections".

## Status and limits of this note

- Question-class fit below is **conceptual suitability from reading the
  design**, not a measured accuracy figure. No benchmark in this note.
- Product Ask means `POST /v1/product/repos/{id}/ask`. It calls the
  `/v1/rag` handler in process with `execution_mode="rag"`, so the
  deterministic inventory shortcut is skipped there. Gradio's `/v1/rag` can
  take that shortcut for inventory-pattern questions.
- The call order in the appendix was read from code, not traced on a live
  request.

## Confirmed facts about Ask (read from code)

- One pass: embed the question, vector search (top 5 seeds, filtered to the
  repository, generation and source type code), drop near-duplicates,
  one-hop graph expansion (relation types chosen by regex on the question,
  capped at 20 documents), up to 3 chunks per seed or expanded document,
  limits of 5 per document and 50 overall, whole passages fitted to a byte
  budget (default 4096, compact 2048), then **one** call to the model.
- The model cannot ask for more evidence after seeing the context. Anything
  discarded before that call is invisible to it.
- Repository-overview controls (canonical selection, claim selection,
  structured answers) default to off
  (`rag_orchestrator/src/core/config.py`, `REPOSITORY_OVERVIEW_*`).
- The orchestrator holds the in-memory graph used for expansion, TRACE and
  IMPACT. No code inside Foundry calls TRACE, IMPACT or Evidence; external
  callers are unobserved.
- The model-directed execution loop (`execution_policy.py`) has no caller.
  Only the deterministic `python_inventory` path runs.

## Question classes and fit (conceptual)

| Question shape | Fit | Why |
| --- | --- | --- |
| Explain one named function or class | Strong **if retrieval finds it** | Function-level chunks; see correction 1 |
| Explain a localized implementation (JWT creation, password hashing) | Strong if the code sits in a few related functions | Similarity plus one hop can supply it |
| Immediate dependencies ("what does this handler call") | Conditional | Needs resolved CALL edges and the passages surviving selection |
| Repository overview | Conditional | Overview controls off by default; ORIENT answers a narrower inventory question deterministically |
| Complete execution-path trace | Poor | One hop, small budget, no follow-up |
| Repository-wide negative claim ("does any endpoint bypass auth") | Poor | Five seeds cannot establish absence |
| Comprehensive impact analysis | Poor through Ask | See correction 2 |
| Multi-step architectural investigation | Poor | No second retrieval after the first |
| Runtime behavior (concurrency, races) | Poor | Static source only |

Two dimensions explain the pattern: evidence scope (how much of the
repository must be examined) and discovery difficulty (how easily the
relevant evidence is identified before answering). A question need not be
complicated to fail: a simple question about one file is hard if similarity
ranking cannot reach that file.

| | Easy to discover | Hard to discover |
| --- | --- | --- |
| **Localized** | Best fit | Conditional (named file missed by ranking) |
| **Broad** | Conditional (well-documented subsystem) | Poor fit |

## What a stronger model changes

| Limitation | Can a stronger model help? |
| --- | --- |
| Understanding complicated source | Yes |
| Reasoning across several delivered passages | Yes |
| Clearer explanations | Yes |
| Recognizing that evidence is insufficient | Possibly; untested here |
| Retrieving a file vector search omitted | No |
| Following another graph edge after seeing the prompt | No |
| Requesting more source lines | No |
| Establishing repository-wide completeness | No |
| Verifying every claim is supported | Not automatically |

A stronger model improves what happens after evidence delivery. It does not
change Ask's evidence-discovery authority. This is a statement about the
Ask path as built, not a claim that model choice is irrelevant to Foundry.

## Corrections to the outside analysis

1. **"Strong fit" for a named function depends on retrieval success, and
   this repository has a measured counterexample.** The
   [2026-11-11 evidence note](/DOCS/notes/20261111-code-intelligence-retrieval-failure-evidence.md)
   (F2) ranked every chunk of a 77,625-chunk repository against the query.
   The best-ranked chunk of each expected implementation symbol sat at ranks
   329 to 7,861, behind the top 25 (examples, reproduction scripts, tests,
   markdown). With `top_k` 5, those symbols could not reach the model.
   That is the failure that started this review. In a large repository the
   fit is "strong given retrieval", and retrieval is the part that failed.
2. **Ask is not all of Foundry.** The analysis calls impact analysis and
   execution-path tracing poor fits for D1, which is right for Ask. Foundry
   also exposes deterministic TRACE, IMPACT and Evidence routes (over the
   cached graph), ORIENT, Locate, and a lab-backed Investigate path. Those
   exist; none has an observed caller inside Foundry, and this note does not
   assess how well they cover those question classes. The accurate
   statement is that Ask alone is not designed for them and that other
   capabilities exist and are not yet shown to be exercised.
3. **"The model cannot request more evidence" is a property of Ask, not of
   the codebase.** The harness (`execution_policy.py`) is built for a
   model-directed loop (tool allowlist, ledger, budgets, stop reasons) but
   has no caller. "Implemented" and "actively exercised" must stay separate.

The analysis also named a specific stronger model. That model was not
verified here, and the argument does not depend on it.

## Open question (not decided)

Can a reasonably objective boundary be drawn between questions Ask should
answer and questions that need deeper investigation? The code already
contains partial boundary-like mechanisms (the inventory pattern shortcut,
the claim-type controls, the evidence-workflow modes), but this note neither
evaluates nor proposes using them. No decision is recorded.

## Not verified

- Measured fit for any question class on any current corpus.
- Whether a stronger model reliably recognizes insufficient evidence from
  the Ask envelope.
- External callers of Ask, TRACE, IMPACT or Evidence.
- The exact call count and timing of a live Ask request.

## Appendix: D1, one Ask request on the product path

The three working diagrams (L1 logical, P1 physical, D1 flow) exist as
untracked drafts under `DOCS/architecture/` and were not changed here. The
sequence below is the reviewed version this note relies on.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant F as nginx frontend
    participant O as Orchestrator
    participant I as Ingestion service
    participant V as Vector store
    participant P as PostgreSQL
    participant E as Embedding model
    participant L as LLM service
    participant M as Generation model

    B->>F: POST /v1/product/repos/ID/ask with question and generation
    F->>O: proxied, only /v1/product/* allowed
    O->>I: GET generation for the repository
    I->>P: SQL: owner generation and request status
    I-->>O: ready generation and commit
    Note over O: Different from the pinned generation: 409 stale, no retrieval, no model call
    Note over O: Product Ask calls the /v1/rag handler in process with execution_mode rag
    O->>I: GET /v1/repos to confirm the repository exists
    O->>E: embed the question
    O->>I: GET generation again
    O->>V: POST /v1/vectors/search, repo, generation, code only, top 5
    V->>P: SQL: pgvector similarity
    V-->>O: 5 seed chunks with metadata
    Note over O: Near-duplicate seeds dropped
    O->>I: GET generation, graph cache check
    alt graph not cached for this generation
        O->>I: GET /v1/graph/repos/ID/nodes
        I->>P: SQL: all nodes and relationships
        I-->>O: full graph export, cached (LRU of 32 repositories)
    end
    Note over O: One-hop expansion by question wording, capped at 20 documents
    O->>I: POST /v1/graph/repos/ID/nodes/lookup
    I->>P: SQL: lookup
    par for each seed and expanded document
        O->>V: POST /v1/vectors/search-by-doc, k 3
        V->>P: SQL
        V-->>O: up to 3 chunks
    end
    O->>I: GET generation, verify unchanged
    Note over O: Discard: over 5 per document, over 50 overall, then whole passages fitted to the byte budget. Manifest fixed.
    O->>L: POST /generate with labeled context and question
    L->>M: chat completion
    M-->>L: answer
    L-->>O: answer, model used, fallback and capacity receipt if any
    O->>I: GET generation, commit for the envelope
    O->>I: GET generation, post-answer pin check
    Note over O: Citation scope check; out-of-scope citation withholds the result
    O-->>F: 200 answer, envelope, citations (or 409 stale, or 503)
    F-->>B: response
```
