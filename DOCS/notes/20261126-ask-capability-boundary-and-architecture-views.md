---
title: "What Ask (D1) is designed to answer: capability boundary, as of 2026-11-26"
date: 2026-11-26
type: note
status: current
summary: "Status snapshot, 2026-11-26 22:49 EST (owner-stated). Ask is one predetermined retrieval-and-expansion pass followed by one model call: evidence retrieval and synthesis, not iterative investigation. Records, per question class, architectural suitability separately from demonstrated reliability, what a stronger model can and cannot change, three corrections to the outside analysis this was reviewed from, and the open boundary question. Descriptive only: no proposals, no changes."
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

- The suitability column below is **conceptual, from reading the design**.
  The reliability column records only what has been demonstrated. No
  benchmark or accuracy figure is claimed in this note.
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

## Question classes: suitability versus demonstrated reliability

Two different things are kept apart throughout this note:

1. **Architectural suitability:** whether the question could be answered
   from a small amount of source, given how Ask is built.
2. **Demonstrated reliability:** whether Foundry has been shown to retrieve
   that source and deliver it to the model.

A question such as "what does function X do?" is architecturally simple.
That does not make it reliably answerable by the current Ask.

| Question shape | Architectural suitability | Demonstrated reliability |
| --- | --- | --- |
| Explain one named function or class | High, if the function is retrieved | **Known retrieval failures** (correction 1) |
| Explain a localized implementation (JWT creation, password hashing) | High, if sufficient context is delivered | Not established |
| Immediate dependencies ("what does this handler call") | Conditional on resolved CALL edges and the passages surviving selection | Not established |
| Subsystem or repository overview | Limited by breadth and the byte budget; overview controls are off by default; ORIENT answers a narrower inventory question deterministically | Not established |
| Complete execution-path trace | Not designed for systematic multi-step discovery (one hop, small budget, no follow-up) | Not established through Ask |
| Repository-wide negative claim ("does any endpoint bypass auth") | Not designed for completeness (five seeds cannot establish absence) | Not established through Ask |
| Comprehensive impact analysis | Not designed for completeness (see correction 2) | Not established through Ask |
| Runtime behavior (concurrency, races) | Static source only | Not established |

"Known retrieval failures" is scoped: it is the seed-search measurement for
named symbols in one 77,625-chunk repository (2026-11-11), not an
end-to-end failure rate for all repositories. "Not established" means no
evidence either way, not a failure. Ask answers with citations have been
returned in the 2026-11-25 Linux run (six questions across two
repositories, each pinned to the deployed generation), but that run checked
pinning, error contracts and that ranged citations read back to stored
source, not that the answers were correct; it does not establish
reliability.

Two dimensions explain which questions are harder: evidence scope (how much
of the repository must be examined) and discovery difficulty (how easily the
relevant evidence is identified before answering). A question need not be
complicated to fail: a simple question about one file is hard if similarity
ranking cannot reach that file.

| | Easy to discover | Hard to discover |
| --- | --- | --- |
| **Localized** | Highest suitability | Conditional (named file missed by ranking) |
| **Broad** | Conditional (well-documented subsystem) | Not designed for it |

See the
[2026-11-25 Linux run report](/DOCS/test_results/2026-11-25-440-linux-deployed-run.md)
for what that run did and did not verify.

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

1. **Suitability was conflated with reliability; a named function is
   architecturally simple but not reliably retrieved.** The outside analysis
   first labeled named-function questions a "strong fit". The owner accepted
   the correction and the two-column table above replaced that label. The
   [2026-11-11 evidence note](/DOCS/notes/20261111-code-intelligence-retrieval-failure-evidence.md)
   (F2) ranked every chunk of a 77,625-chunk repository against the query.
   The best-ranked chunk of each expected implementation symbol sat at ranks
   329 to 7,861, behind the top 25 (examples, reproduction scripts, tests,
   markdown). With `top_k` 5, those symbols could not reach the model.
   That is the failure that started this review: suitability is high if the
   function is retrieved, and retrieval is the part that failed.
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

The owner also agreed that Ask's limitations must not be attributed to
Foundry as a whole: its deterministic and investigative capabilities need
separate evaluation of operational use and accuracy.

The analysis also named a specific stronger model. That model was not
verified here, and the argument does not depend on it.

## Open question (not decided)

Can a reasonably objective boundary be drawn between questions Ask should
answer and questions that need deeper investigation? The code already
contains partial boundary-like mechanisms (the inventory pattern shortcut,
the claim-type controls, the evidence-workflow modes), but this note neither
evaluates nor proposes using them. No decision is recorded.

## Not verified

- Demonstrated reliability for any question class other than the named-symbol
  retrieval failures cited above, on any current corpus.
- Whether a stronger model reliably recognizes insufficient evidence from
  the Ask envelope.
- External callers of Ask, TRACE, IMPACT or Evidence.
- The exact call count and timing of a live Ask request.

## Appendix: D1, one Ask request on the product path

The three working diagrams are committed alongside this note as Mermaid
sources: [L1 logical](/DOCS/architecture/foundry-L1-logical-architecture.mmd),
[P1 physical](/DOCS/architecture/foundry-P1-physical-architecture.mmd) and
[D1 flow](/DOCS/architecture/foundry-D1-ask-data-flow.mmd). The saved P1 and
D1 are simplified overviews (D1 is a stage flowchart). The chronological
sequence below was reviewed against the code and is the version this note
relies on.

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
