---
title: "SCIP Semantic Enrichment and Evidence-Aware Graph Relationships"
date: 2026-11-12
created: 2026-11-12
type: strategy-note
status: exploratory
authority: "Owner/assistant architectural brainstorming; not an accepted ADR, issue, milestone, implementation authorization, or benchmark result"
verification_status: "Conceptual analysis based on discussion and November 10 planning/audit context; no fresh implementation inspection, SCIP indexer execution, benchmarking, or live deployment verification"
scope: rag-foundry-universal
review_period: "January 2027 or after foundational correctness gates"
tags:
  - code-intelligence
  - scip
  - tree-sitter
  - semantic-resolution
  - graph-provenance
  - evidence-aware-relationships
  - strategy
  - brainstorm
related:
  - "[Full vision and strategic roadmap](/DOCS/notes/20261110-full-vision-and-strategic-roadmap.md)"
  - "[Code intelligence outlook and portability goals](/DOCS/notes/20261110-code-intelligence-outlook-and-portability-goals.md)"
  - "[November 10 code intelligence architecture audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[Independent review and audit-author response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md)"
  - "[Canonical identity ADR](/DOCS/adr/ADR-031-canonical-identity-model.md)"
  - "[Symbol resolution and call graph ADR](/DOCS/adr/ADR-032-symbol-resolution-call-graph.md)"
  - "[Source authority and provenance ADR](/DOCS/adr/ADR-053-source-authority-provenance-model.md)"
  - "[Project status](/DOCS/status.md)"
---

# SCIP Semantic Enrichment and Evidence-Aware Graph Relationships

**Strategic discussion addendum — November 12, 2026**  
**Applies only to RAG-FOUNDRY-UNIVERSAL.**

> [!important] Status and authority
> This note captures an emerging architectural preference and investigation proposal, **not an adoption decision or implementation request**. Preserve existing issue/milestone and ADR governance. Do not alter ingestion, graph schema, deployments, or evaluation controls solely because this note exists. Validate current implementation details against the November 10 audit and current code before proposing changes.

## 1. Why this discussion arose

A proposed multilingual code-RAG architecture combined **Apache AGE + pgvector**, **Tree-sitter + SCIP**, and bounded vector-seeded graph traversal. The review separated three concerns that must not be conflated:

1. **Graph storage and query language** — whether to retain PostgreSQL-backed graph persistence or introduce another graph layer.
2. **Semantic correctness of the code graph** — whether references and targets are resolved accurately across files and languages.
3. **Retrieval and evidence delivery** — whether relevant graph relationships and source passages reach the answer within bounded resources.

The discussion judged **SCIP-assisted symbol resolution** considerably more promising than a database migration. Apache AGE could offer Cypher traversal, but a different query language does not itself repair incorrect symbol resolution, generation consistency, extraction coverage, or evidence-delivery failures. No AGE adoption is proposed.

## 2. Emerging direction: SCIP supplements Tree-sitter

**Owner-aligned architectural preference:** Investigate SCIP as an **optional semantic index** enriching the existing Tree-sitter-based extraction pipeline, not replacing Tree-sitter.

- **Tree-sitter and language extractors** supply syntax, declarations, source ranges, structural relationships, and a dependable baseline when full semantic indexing is not possible.
- **Language-specific semantic indexers emitting SCIP** can supply symbol identities, definitions, references, and certain language-aware relationships when project configuration and indexing prerequisites permit.
- **A reconciliation/adapter layer** would map validated semantic information into the existing canonical identity model and common intermediate representation (IR), without creating a second authoritative graph.
- **The existing GraphAssembler, persistence, and retrieval workflows** remain the preferred integration path unless evidence demonstrates a necessary architectural change.

Conceptual data flow:

```text
Repository source
   |------------------------------|
   v                              v
Tree-sitter / existing          Optional SCIP-producing
language extractors             semantic indexers
   |                              |
   |------- reconciliation -------|
                    |
           Common IR + canonical identity
                    |
          Existing GraphAssembler
                    |
          Existing graph persistence
                    |
       DISCOVER / ORIENT / TRACE /
            EXPLAIN / IMPACT
```

**Critical limitation:** SCIP references are not equivalent to a complete, execution-accurate `CALLS` graph. A resolved reference may or may not be a call; polymorphism, dynamic dispatch, generated code, reflection, incomplete dependencies, or unavailable build contexts can constrain resolution. Any `CALLS` derivation must preserve those distinctions.

## 3. Emerging direction: evidence-aware relationship model

The owner explicitly favored the graph **distinguishing, or at least being capable of distinguishing**, the basis on which a relationship is asserted. This is a **capability requirement**, not a mandate to deploy three kinds of instrumentation now.

For a candidate `A --CALLS--> B` relationship, the possible evidence classes are:

| Evidence class | What it supports | Illustrative producer | What it does **not** prove |
| --- | --- | --- | --- |
| **Syntactic inference** | A syntactic call site and potentially a candidate target | Tree-sitter extractor | That the candidate resolves unambiguously to B |
| **Static semantic resolution** | A reference resolves to a named symbol under a particular static analysis/indexer context | SCIP-producing indexer and adapter | That every runtime invocation dispatches to B |
| **Runtime observation** | B was observed as a target in specific executions | Future optional trace/instrumentation import | That B is the only possible target, or that unobserved paths cannot occur |

These evidence classes are **complementary rather than a simplistic ranking of truth**. For instance, a statically resolved symbol and a runtime-observed target can differ legitimately under dynamic dispatch. Conflicts must remain inspectable rather than being silently overwritten.

### Proposed conceptual model

- **One canonical repository graph**, not separate Tree-sitter, SCIP, and runtime graphs.
- **Relationship assertions or candidate relationships** are distinguishable from **evidence records** supporting, qualifying, or challenging them.
- Allow **multiple independent evidence records** for the same canonical relationship and source location where appropriate.
- Preserve **extractor/indexer identity and version**, repository/generation identity, source span, resolution status, and any relevant environment/build/run context.
- Preserve a way to represent **unresolved or ambiguous candidate targets**; never promote every syntactic candidate automatically to an authoritative `CALLS` edge.
- Any confidence label should be **interpretable and evidence-based**; do not invent numerical certainty or treat analyzer output as infallible.
- Keep the model **optional and backward compatible**: absence of SCIP or runtime data must not invalidate existing syntax-only extraction.

This is **not yet a physical schema design**. The implementation may use edge attributes, attached evidence records, or another compatible representation. First inspect existing IR, canonical-ID, edge, and provenance contracts to determine how much is already supported.

## 4. Why this might materially improve code intelligence

| Query family or capability | Expected potential value | Qualification |
| --- | --- | --- |
| **DISCOVER** | Low to moderate | Better symbol cross-references may help targeted navigation; not the primary gain |
| **ORIENT** | Low | Structural inventory already has a syntax-driven foundation |
| **TRACE** | **High potential** | Resolved definitions and references can reduce false paths and missing cross-file links |
| **EXPLAIN** | Medium to high potential | Better identification of the implementation relevant to an explanation |
| **IMPACT** | **High potential** | More accurate reference/dependency relationships can improve impact analysis |
| **Vector discovery** | Limited direct impact | Semantic indexing does not fix embedding-coverage or evidence-budget problems |
| **Runtime behavior** | Limited without traces | Static SCIP evidence does not prove concrete runtime execution |

These are **hypotheses**, not demonstrated improvements. The success metric is not simply a larger graph or more edges. It is **whether answers become more accurate, appropriately qualified, and evidence-traceable**.

## 5. Proposed investigation before any adoption decision

1. **Baseline current contracts.** Review common IR, canonical identity, `CALLS`/`IMPORTS`/`OVERRIDES` construction, generation handling, and provenance transport. Specifically reconcile with ADR-031, ADR-032, ADR-053 and the November 10 architecture audit.
2. **Choose representative repositories.** Include import aliases, cross-file references, overloaded methods, inheritance, interfaces/traits, ambiguous names, unresolved dependencies, and language-specific build/indexer limitations. Cover Python, TypeScript/JavaScript, Java, and Rust as feasible; do not assume feature parity.
3. **Run an independent SCIP experiment.** Produce indices **outside the production ingest path**, preserving baseline snapshot and evaluation isolation. Record tools, versions, setup requirements, completeness, elapsed time and peak resource usage.
4. **Evaluate semantic accuracy.** Compare current graph edges against resolved definitions/references and a reviewed ground truth. Measure precision, recall, ambiguity, false positives, missing/unsupported references, and canonical-ID mapping fidelity.
5. **Evaluate answer-level value.** Replay representative TRACE, IMPACT and EXPLAIN tasks using fixed evaluation controls. Measure correct answers, incorrect confident claims, missing evidence, evidence attribution, and regression risk.
6. **Evaluate lifecycle/operability.** Estimate incremental-update behavior, repository build requirements, failure fallback, memory/latency, supported indexer maturity, index generation binding, and version drift.
7. **Decision gate.** Adopt a minimal enrichment adapter only if demonstrated benefits exceed maintenance, dependency, and operational costs; otherwise retain the existing pipeline and document why.

**Keep existing foundational correctness work independent of this investigation.** The November 10 audit's CI-01 generation consistency, CI-03 derivation/reuse identity, CI-05 extraction-failure coverage, CI-06 effective embedding coverage, and CI-07 workload bounds are not solved by introducing SCIP or AGE.

## 6. Architectural guardrails

- **No second authoritative symbol graph** and no parallel extraction architecture without a proved requirement.
- **No graph-database migration by association.** SCIP is an interchange representation and does not mandate AGE, Neo4j or any other persistence layer.
- **No wholesale graph replacement as a shortcut.** Reconcile identity, repository snapshots, and incremental lifecycle semantics explicitly.
- **No undifferentiated `CALLS` authority.** Candidate, resolved, and observed information must not collapse silently.
- **No assumed universal SCIP availability.** Language tooling, project buildability, dependencies and index quality must be tested.
- **No ranking or confidence formula selected without evaluation.** Similarity weights, hop-decay, edge certainty and token budgets require evidence and query-family-specific reasoning.
- **No implementation without issue and milestone; no permanent policy shift without the appropriate architectural review/ADR.**

## 7. Suggested strategy wording

> **Semantic enrichment and evidence-aware graph:** Preserve Tree-sitter and existing language extractors as the reliable structural baseline. Investigate optional SCIP-based semantic indices to improve cross-file symbol resolution and enrich one canonical graph through the existing IR. Design relationship provenance so that syntactic candidates, statically resolved semantics, and future runtime observations can be distinguished, combined, or challenged without requiring all producers to exist today. Prioritize demonstrated improvements in TRACE, IMPACT, and EXPLAIN accuracy over graph size or technology adoption. Defer implementation until current contracts are inspected and a controlled evaluation demonstrates benefit.

## 8. Open architecture questions

1. Does the current IR represent **asserted relationships vs. candidate relationships**, or is a backward-compatible distinction needed?
2. Can current graph identity associate **multiple evidence records** with one relationship while remaining generation-safe?
3. How should semantic symbol IDs map to existing canonical IDs without destabilizing unchanged symbols between ingestions?
4. Which evidence should TRACE/IMPACT consume by default, and how should contradictions or incomplete resolution be disclosed to answer generation?
5. Should runtime observations remain an **optional external evidence overlay** rather than enter the repository's static graph snapshot?
6. What minimum answer-level improvement justifies the additional semantic indexing toolchain?

## 9. Relationship to prior strategy notes

This note **extends**, but does not replace:

- `20261110-full-vision-and-strategic-roadmap.md` — the broader product vision, workstreams and sequencing.
- `20261110-code-intelligence-outlook-and-portability-goals.md` — maturity planning, portability and foundational correctness priorities.
- November 10 audit and independent review — the evidence base for currently known correctness and integration gaps.

**Suggested repository destination:** `DOCS/notes/20261112-scip-semantic-enrichment-and-graph-evidence-strategy.md`.

**Review disposition:** Explore after/alongside foundational correctness investigations; formalize as an ADR and issue/milestone-backed evaluation only when the owner elects to proceed.
