---
title: "RAG-FOUNDRY-UNIVERSAL: The Full Vision and Strategic Roadmap"
date: 2026-11-10
created: 2026-11-10
type: brainstorm
status: raw
aliases:
  - "The Full Vision and Strategic Roadmap"
  - "Strategic Vision — Auditor Discussion Guide"
tags:
  - strategic-vision
  - roadmap
  - auditor-guide
  - repository-intelligence
  - document-intelligence
  - evidence-grounding
  - brainstorm
source: "User-supplied strategic discussion, captured from chat on 2026-11-10"
audience: [owner, auditor, architecture-reviewer]
authority: "Discussion input; not an accepted roadmap, ADR, evaluation report, or execution authorization"
verification_status: "Original claims preserved; selected local documentation cross-references checked, no fresh implementation or live-system audit"
related:
  - "[Code Intelligence Outlook and Portability Goals](/DOCS/notes/20261110-code-intelligence-outlook-and-portability-goals.md)"
  - "[Documentation Index](/DOCS/index.md)"
  - "[Project Status](/DOCS/status.md)"
  - "[Product Vision](/README_VISION.md)"
  - "[Audit Overview](/DOCS/audit/00-Audit-Overview.md)"
  - "[Sequenced Roadmap](/DOCS/audit/07-Roadmap.md)"
  - "[Retrieval Technique Decision Gates](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md)"
  - "[ADR-054: Evaluation Isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[ADR-055: Node-Text Read Endpoint](/DOCS/adr/ADR-055-node-text-read-endpoint.md)"
  - "[E1 Control Baseline](/DOCS/test_results/2026-11-08-e1-held-out-control-baseline.md)"
  - "[E1 Handoff and Experiment Separation](/DOCS/notes/20261108-e1-control-baseline-and-candidate-handoff.md)"
---

# RAG-FOUNDRY-UNIVERSAL: The Full Vision and Strategic Roadmap

**Strategic discussion — November 10, 2026. Captured as input for a future auditor.**

The companion [Code Intelligence Outlook and Portability Goals](/DOCS/notes/20261110-code-intelligence-outlook-and-portability-goals.md)
records the dated maturity forecasts, competitive aspirations, and cloud/macOS/model
explorations, with a January 2027 review point.

## Trigger

The user supplied a broader strategic discussion after earlier planning had been
framed too narrowly around E1 Track A and Track B. The purpose of this note is to
preserve that thinking and give an auditor a route into the existing decisions,
roadmap and evidence before proposing more implementation.

## Auditor reading guide

> [!important] Authority and scope
> The discussion below is preserved as supplied, with heading levels normalized
> for this note. Its six layers, 13 workstreams, four horizons and preferred
> Vision C-through-B progression are proposed organizing views, not newly adopted
> architecture or release commitments. Read linked documents' own statuses and
> evidence before relying on historical or implementation claims. This note
> authorizes no implementation, deployment, corpus mutation or experiment run.

> [!warning] Claims requiring reconciliation
> The supplied text describes E1 Track A as completed and reports one extra
> primary delivery, no primary-delivery regressions and a changed natural-language
> context. No supporting candidate-results report was found in the local
> documentation inspected while saving this note. The preceding session verified
> the harness-remediation merge, not a candidate execution. Preserve these as
> user-supplied claims pending a dated result report, candidate commit, capture
> provenance and P1–P3 assessment; do not infer a completed or authorized run.
>
> The supplied status table describes multi-language support as partial, mentioning
> TypeScript. [Project Status](/DOCS/status.md) documents shipped extraction for
> Python, TypeScript/JavaScript, Rust and Java. Extraction support and demonstrated
> structural/query parity are different claims; an auditor should reconcile them.

Start with [Project Status](/DOCS/status.md) for the evolving implementation
snapshot, the [Audit Overview](/DOCS/audit/00-Audit-Overview.md) for the existing
program, and the [Sequenced Roadmap](/DOCS/audit/07-Roadmap.md) for work-package and
issue history. The 13-way grouping in this discussion must be mapped to that
roadmap rather than treated as its replacement. In particular, the older roadmap
also uses “Track A” and “Track B” for other work; the labels below refer to E1.

| Discussion area | Existing sources to inspect | Audit purpose |
| --- | --- | --- |
| Foundation, canonical graph and relationships (1) | [Graph Depth Analysis](/DOCS/audit/02-Graph-Depth-Analysis.md), [Canonical Identity](/DOCS/adr/ADR-031-canonical-identity-model.md), [Symbol Resolution](/DOCS/adr/ADR-032-symbol-resolution-call-graph.md) | Separate intended graph semantics from demonstrated correctness. |
| Multi-language understanding (2) | [Multi-Language Graph Plan](/DOCS/audit/03-Multi-Language-Graph-Plan.md), [Project Status](/DOCS/status.md) | Distinguish supported extraction from cross-language query parity. |
| Incremental ingestion and lifecycle (3) | [Roadmap](/DOCS/audit/07-Roadmap.md), [Ingestion Ownership](/DOCS/adr/ADR-049-ingestion-ownership-recovery.md), [Repository Lifecycle](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md), [Generation-Aware Cache](/DOCS/adr/ADR-051-generation-aware-graph-cache.md) | Check generation, activation, deletion and recovery guarantees without assuming staged publication. |
| ORIENT, TRACE, IMPACT and architecture views (4, 5, 9) | [Roadmap](/DOCS/audit/07-Roadmap.md), [Architecture Documentation](/DOCS/index.md#architecture-deep-dives), [Overview Production Verification](/DOCS/test_results/2026-10-11-issue-254-257-production-verification.md) | Identify what is implemented, what is evaluated, and which inferred relationships remain uncertain. |
| Provenance and authority (6) | [ADR-053](/DOCS/adr/ADR-053-source-authority-provenance-model.md), [Project Status](/DOCS/status.md) | Distinguish proposed classification policy, transported metadata and question-specific authority behavior. |
| Discovery, delivery and sufficiency (7, 8) | [Hybrid Retrieval](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md), [Evidence Delivery](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md), [Decision Gates](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md), [E1 Stage Attribution](/DOCS/test_results/2026-10-31-e1-stage-attribution-f1-f3.md) | Diagnose the failed stage before adding or promoting a mechanism. |
| E1 Track A and Track B | [Experiment Separation Handoff](/DOCS/notes/20261108-e1-control-baseline-and-candidate-handoff.md), [Control Baseline](/DOCS/test_results/2026-11-08-e1-held-out-control-baseline.md), [Frozen Predictions](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md), [Frozen Mechanism](/DOCS/evaluations/code-evidence-held-out/mechanism-spec-named-symbol-first.md), [Statement-Level Contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md), [ADR-055](/DOCS/adr/ADR-055-node-text-read-endpoint.md) | Keep chunk-ordering predictions separate from the statement-level gate; verify run provenance and held-out eligibility before interpreting results. |
| Document intelligence (10) | [D0 Document Baseline](/DOCS/evaluations/2026-10-12-document-rag-baseline.md), [Local Ingestion Blocker](/DOCS/test_results/2026-10-12-document-rag-local-ingestion-blocker.md), [Post-Deployment Preflight](/DOCS/test_results/2026-10-12-document-rag-post-deploy-preflight.md) | Distinguish extraction capability from demonstrated end-to-end document quality. |
| Scale and reliable execution (11) | [Scalability Plan](/DOCS/audit/04-Scalability-Plan.md), [Bounded-Memory Specification](/specs/004-bounded-ingestion-memory/spec.md), [Production Correctness Specification](/specs/005-production-correctness/spec.md) | Check boundedness, durability and consistency against measured workloads. |
| Bounded repair and adaptive investigation (12) | [Roadmap](/DOCS/audit/07-Roadmap.md), [Issue #200](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/200), [Issue #207](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/207) | Preserve the dependency between demonstrated sufficiency and more adaptive investigation. |
| Enterprise product and operations (13) | [Enterprise Platform Plan](/DOCS/audit/05-Enterprise-Platform-Plan.md), [LLM Provider Plan](/DOCS/audit/06-LLM-Provider-LiteLLM-Plan.md), [Execution Boundaries](/DOCS/deployment/agent-execution-and-verification.md) | Separate product aspirations from shipped controls and operator-owned deployment. |

Links identify relevant source documents, not blanket corroboration of every
claim in the supplied discussion. No external issue state or live deployment was
checked for this capture. Standard Markdown links are used throughout: they work
in Obsidian and follow the [repository's OKF linking rule](/DOCS/standards/okf-documentation.md).

## Raw Input

### RAG-FOUNDRY-UNIVERSAL: The Full Vision and Strategic Roadmap

**Strategic discussion — November 10, 2026**

The earlier answer was too narrow. **Track A and Track B are two experiments within a much larger program.** They are not the two overarching tracks of RAG-FOUNDRY-UNIVERSAL.

We have been building toward something substantially more ambitious than a conventional RAG application:

> **A graph-aware repository and document intelligence platform that can investigate complex information, understand structural relationships, retrieve authoritative evidence, explain its conclusions with traceable sources, and eventually support impact analysis and multi-step investigations.**

The distinction matters.

A conventional RAG system primarily answers:

> *What information in my documents is relevant to this question?*

Our intended platform should eventually answer:

> *What exists in this repository? How does it work? What calls it? What depends on it? What would change if I modified it? What evidence supports that conclusion? And what information is still missing?*

That requires much more than embeddings, vector retrieval, or adding a graph.

### 1. The architectural vision

I would describe the platform as having **six layers of intelligence**.

| Layer | Capability | Fundamental question |
|---|---|---|
| 1. Knowledge acquisition | Repository/document ingestion, parsing, extraction, incremental updates | What information do we have? |
| 2. Structural intelligence | Symbols, imports, calls, inheritance, dependencies, relationships | How is the information connected? |
| 3. Evidence discovery | Vector, lexical, metadata, graph and structural retrieval | Where is the relevant evidence? |
| 4. Evidence delivery and sufficiency | Context selection, source fidelity, authority, completeness | Have we assembled enough trustworthy evidence? |
| 5. Investigation and reasoning | ORIENT, TRACE, IMPACT, bounded retrieval repair and later adaptive investigation | How do we answer complex questions reliably? |
| 6. Product and operational intelligence | Lifecycle, scale, security, providers, integrations, UX, observability | Can people reliably use and operate this platform? |

The most important architectural principle is:

**The LLM should reason over a trustworthy evidence system—not compensate for an unreliable one.**

That is the organizing idea behind much of the work we have undertaken since September.

The graph, vector index, repository inventory, provenance metadata and LLM should have distinct responsibilities. We should be able to diagnose each boundary independently rather than treating every wrong answer as a generic model-quality problem.

---

### 2. The complete program: 13 workstreams

The roadmap has evolved beyond the original five-phase July audit. Our subsequent Phase 6 planning introduced a more detailed sequence covering repository intelligence, evidence reliability, scaling, document intelligence and adaptive investigation.

The following is the consolidated program—not a claim that every workstream is still unfinished.

| # | Workstream | Intended outcome | Position in the vision |
|---|---|---|---|
| **1** | Foundation and graph correctness | Deterministic, structurally correct ingestion and indexing | Foundational |
| **2** | Multi-language repository understanding | Python, TypeScript/JavaScript, Rust, Java and shared structural representation | Foundational |
| **3** | Incremental ingestion and corpus lifecycle | Efficient updates, fingerprints, versioned generations, consistency and deletion | Foundational / operational |
| **4** | ORIENT: repository inventory | Authoritative deterministic understanding of repository contents | Repository intelligence |
| **5** | TRACE and IMPACT | Navigate dependencies, execution relationships and change impact | Repository intelligence |
| **6** | Source provenance and authority | Distinguish current implementation from historical, speculative and test evidence | Evidence reliability |
| **7** | Retrieval quality and evidence discovery | Find relevant source material through measured retrieval strategies | Evidence reliability |
| **8** | Evidence delivery and sufficiency | Preserve sufficient, faithful evidence in the final LLM context | Evidence reliability |
| **9** | Architecture intelligence and derived views | Generate explainable architecture descriptions and dependency views | Higher-level intelligence |
| **10** | Document intelligence and selective OCR | Understand PDFs, tables, scans and mixed-format documents efficiently | Broader knowledge acquisition |
| **11** | Large-corpus scalability and reliable execution | Bounded memory, durable jobs, recovery, graph/query performance | Operational maturity |
| **12** | Adaptive investigation | Plan, retrieve, assess gaps, repair and investigate across multiple steps | Advanced intelligence |
| **13** | Enterprise platform and product experience | Authentication, integrations, interfaces, observability and deployment | Product maturity |

These are **workstreams, not 13 sequential implementation phases**. Several are already partially or substantially implemented, and some can proceed independently.

The ordering is governed by dependencies and measured gaps.

---

### 3. What each workstream is supposed to achieve

#### Workstreams 1–3: Build a trustworthy knowledge foundation

The platform must first understand what it has ingested.

**1. Foundation and graph correctness**

This covers correct node identity, imports, function calls, inheritance, graph traversal, deterministic extraction and indexing. The original audit identified significant correctness and ingestion-performance problems.

A key architectural decision was to retain deterministic canonical identities and avoid using an LLM to construct the source-of-truth graph.

**2. Multi-language repository understanding**

The intended architecture uses language-specific extractors feeding a common intermediate representation.

That allows Python, TypeScript/JavaScript, Rust and Java to participate in a shared graph model rather than developing four unrelated implementations.

The long-term objective is not merely parsing more languages; it is supporting consistent cross-language structural queries.

**3. Incremental ingestion and lifecycle**

The system needs to understand what changed between repository versions and update the corresponding artifacts without unnecessarily rebuilding everything.

This includes content fingerprints, commit or snapshot lineage, generation identity, correct deletion behavior and safe activation of updated indexes.

We have already completed substantial work in this area. The remaining question is how well these mechanisms perform under larger, more varied workloads.

#### Workstreams 4–5: Repository intelligence

These are central to what differentiates RAG-FOUNDRY-UNIVERSAL from a document chatbot.

**4. ORIENT — What is this repository?**

ORIENT produces deterministic structural inventory: packages, modules, symbols, language coverage and other repository facts.

For example:

> "Explain the major components of this repository."

That question should be grounded in the actual repository inventory—not answered by whichever README or historical design document happens to rank highest.

We have already implemented and refined ORIENT-related functionality, including generation-aware inventory and repository-overview authority handling.

**5. TRACE and IMPACT — How is it connected, and what changes?**

TRACE investigates relationships:

> "How does an incoming request reach this function?"

IMPACT asks:

> "What might be affected if I change this interface?"

This is where the graph becomes especially useful.

An important distinction is that structural reachability is not necessarily runtime reachability. A graph can identify probable dependencies, but dynamic dispatch, configuration and unresolved external calls may limit certainty.

The platform should report those limitations rather than invent complete execution paths.

#### Workstreams 6–8: Evidence reliability

This is where most of our recent research has been concentrated.

**6. Source provenance and authority**

We must distinguish between:

- Current source implementation and configuration.
- Tests and fixtures.
- Historical design documents.
- Evaluation artifacts.
- Proposals, examples and generated material.

These sources can all be useful, but they should not carry equal authority for every question.

We have already implemented important provenance transport and repository-overview authority controls.

**7. Evidence discovery**

This workstream asks whether the retrieval system can locate the correct information.

It encompasses vector retrieval, structural search, graph expansion, hybrid strategies, filters, candidate selection and potentially reranking.

Our principle is to **measure where retrieval fails before adding another retrieval technique**.

An earlier evaluation showed that graph-aware retrieval could improve evidence recall. More recent held-out testing exposed cases where the primary function never entered the candidate pool.

Those are genuine discovery failures; no context-reordering mechanism can repair them.

**8. Evidence delivery and sufficiency**

This is our immediate research frontier.

There are actually several distinct questions:

| Stage | Question |
|---|---|
| Discovery | Did we retrieve the relevant source? |
| Selection | Did we retain the right document or chunk? |
| Passage preservation | Did we preserve the lines that explain the behavior? |
| Context delivery | Did the required evidence reach the LLM? |
| Sufficiency | Does that evidence completely support the requested answer? |
| Answer correctness | Did the LLM interpret the evidence accurately? |

Our completed **E1 Track A** experiment belongs within this workstream.

It tested whether deterministic named-symbol promotion improved final-context delivery. It yielded one additional primary-function delivery across 12 cases, with no primary-delivery regressions, but exposed an unwanted natural-language context change.

That is why it is not recommended as a general production policy.

**Track B**, associated with issue #276 and ADR-055, investigates the deeper problem: statement-level evidence delivery, including complete operations and dependency descriptions.

The strategic direction is not simply to reorder chunks more cleverly.

It is to develop an evidence-delivery architecture that understands what must survive into the final context.

---

### 4. Beyond retrieval: Workstreams 9–10

#### 9. Architecture intelligence and derived views

This is an important long-term differentiator.

Imagine asking:

> "Explain this application's architecture, including its main components, service boundaries and external dependencies."

The platform should combine deterministic inventory, structural relationships, configuration and relevant documentation.

Eventually, it could produce architecture diagrams and navigable dependency views.

However, **diagrams should be projections of verified structural facts**, not attractive pictures invented by an LLM.

This workstream connects ORIENT, TRACE, IMPACT and evidence sufficiency.

#### 10. Document intelligence

Our project is not intended to understand source code alone.

The broader vision includes PDFs, scanned documents, tables, diagrams and other formats.

We have already explored OCR and vision-based document extraction.

A future direction is **selective or just-in-time OCR**, where inexpensive extraction and layout analysis identify what requires deeper processing.

This could avoid performing expensive OCR on every page when a query will use only a small portion of a document collection.

But this remains a research direction. We should benchmark extraction quality, indexing completeness, latency and cost before changing the pipeline.

---

### 5. Operational maturity: Workstream 11

There are three distinct requirements here.

**Scalability:** ingestion and query execution must remain bounded as repository and document collections grow.

**Durability:** a failed ingestion job must not leave the active corpus inconsistent or require an expensive manual restart.

**Consistency:** retrieval results, graph relationships and structural inventory should correspond to the same activated corpus generation.

Our earlier work already addressed important memory, locking, recovery and lifecycle problems.

The longer-term objectives include durable workers, bounded queues, incremental graph maintenance, transactional activation and performance measurements against genuinely large repositories.

We should not interpret a working Docker deployment as proof of enterprise-scale capacity.

---

### 6. Advanced intelligence: Workstream 12

#### From retrieval orchestration to adaptive investigation

This is where I see the most substantial long-term opportunity.

Today, many RAG systems follow essentially this process:

```text
Question
   ↓
Retrieve
   ↓
Construct context
   ↓
LLM
   ↓
Answer
```

Our more ambitious architecture is:

```text
Question
   ↓
Understand intent
   ↓
Choose investigation strategy
   ↓
Retrieve evidence
   ↓
Assess evidence sufficiency
   │
   ├── Sufficient ────────→ Generate supported answer
   │
   └── Insufficient
          ↓
      Identify the gap
          ↓
      Select targeted repair
          ↓
      Retrieve additional evidence
          ↓
      Reassess
```

This introduces a meaningful difference between **an agent that keeps searching** and **a system that understands why additional evidence is required**.

The earlier roadmap deliberately separated two capabilities:

**Bounded evidence repair — issue #200:** retrieve, assess, perform at most a controlled targeted repair, and reassess.

**Adaptive multi-step investigation — issue #207:** investigate broader questions requiring multiple related queries and intermediate conclusions.

The second should follow evidence that the first is inadequate.

I would preserve that ordering.

We should not introduce generalized agent behavior simply because it is technologically fashionable.

---

### 7. Enterprise product: Workstream 13

The original roadmap envisioned a self-hosted, multi-user enterprise platform.

Its proposed capabilities included authentication and authorization, private repository integration, tenant isolation, auditability, operational monitoring, deployment tooling and a richer web interface.

A particularly compelling eventual workflow is:

```text
Developer opens pull request
           ↓
Repository changes identified
           ↓
Incremental ingestion
           ↓
Structural dependency analysis
           ↓
Potentially impacted components identified
           ↓
Evidence-backed impact report
           ↓
Developer investigates through interactive UI
```

This would turn the platform from a question-answering tool into a repository intelligence service integrated with engineering workflows.

But it must inherit the reliability of the underlying analysis.

A polished interface displaying incorrect dependency claims would not constitute a successful product.

---

### 8. Where we stand now

Here is my assessment, distinguishing established progress from work that still needs investigation. This is based on our documented development history, **not a fresh verification of the live repository**.

| Area | Assessment | Next strategic consideration |
|---|---|---|
| Core graph-aware RAG | Established implementation | Improve measured correctness, not rebuild |
| Multi-language extraction | Partially implemented, with TypeScript support | Verify coverage and structural parity |
| Incremental ingestion | Significant implementation completed | Validate scale and reliability |
| ORIENT | Implemented and refined | Expand confidence in authoritative answers |
| TRACE / IMPACT | Part of the planned intelligence layer | Establish demonstrated end-to-end correctness |
| Provenance | Significant implementation completed | Make authority handling consistent across question types |
| Evidence discovery | Functional, with documented misses | Diagnose source-specific discovery failures |
| Evidence delivery | Actively researched | Investigate statement-level preservation |
| Evidence sufficiency | Contracts and evaluation strategy exist | Establish a successful measured mechanism |
| Architecture intelligence | Planned direction | Derive views from verified facts |
| Document intelligence | OCR capabilities explored and integrated | Compare selective extraction strategies |
| Scale and operations | Major hardening completed | Large-corpus reliability testing |
| Adaptive investigation | Deferred | Introduce only after bounded sufficiency works |
| Enterprise platform | Long-term roadmap | Prioritize once core intelligence is demonstrably reliable |

There is no need to reopen every area merely because it appears in the roadmap.

---

### 9. How I would organize the remaining work

Rather than organize everything around individual GitHub issues, I would use **four strategic horizons**.

These are my proposed planning groupings, not previously approved release commitments.

| Horizon | Strategic objective | Critical capabilities |
|---|---|---|
| **H1 — Evidence correctness** | Make answers reliable and explainable | Discovery, final-context delivery, sufficiency, provenance |
| **H2 — Repository intelligence** | Move beyond document retrieval into structural understanding | ORIENT, TRACE, IMPACT, architecture explanations |
| **H3 — Broader intelligence and scale** | Handle larger repositories, mixed-format knowledge and more complex questions | Large-corpus validation, document intelligence, bounded investigation |
| **H4 — Productization** | Make the system useful to teams and organizations | Security, integrations, UX, observability, deployment |

These horizons may overlap, but their dependencies should remain explicit.

#### H1 is especially important

We cannot reliably perform architecture investigation or impact analysis if the required source statements fail to reach the reasoning layer.

That is why the work on evidence preservation is strategically more significant than the modest numerical improvement measured in Track A.

Conversely, we should not spend indefinitely optimizing context assembly if evidence discovery is the real bottleneck.

We now have enough diagnostic separation to investigate those problems independently.

---

### 10. The research questions that should guide us

I would frame future architecture decisions around six questions.

| Question | Why it matters |
|---|---|
| **1. Can we reliably discover the right evidence?** | Establishes the capability of retrieval and structural search. |
| **2. Can we preserve exactly the evidence needed?** | Establishes the quality of context assembly. |
| **3. Can we determine when evidence is insufficient?** | Enables bounded repair and reduces unsupported conclusions. |
| **4. Can we answer questions that span multiple symbols and relationships?** | Separates repository intelligence from ordinary document RAG. |
| **5. Can we explain an answer's supporting evidence and uncertainty?** | Creates trust and auditability. |
| **6. Can we accomplish all of this at scale, with acceptable latency and cost?** | Determines whether the architecture can become a useful product. |

Every substantial new mechanism should address at least one of these questions and have a measurable acceptance criterion.

This also helps avoid architectural accumulation: a new graph database, reranker, orchestration framework or agent framework should earn its place through demonstrated benefits.

---

### 11. The vision I think we should discuss

There are three possible ways to define what RAG-FOUNDRY-UNIVERSAL ultimately becomes.

#### Vision A — A better graph-aware RAG engine

A dependable RAG platform combining structural relationships, hybrid retrieval, provenance and pluggable models.

This is achievable and useful, but comparatively narrow.

#### Vision B — A repository and document intelligence platform

An evidence-grounded system that understands repository structure, traces relationships, explains implementation behavior, analyzes dependencies and incorporates relevant documents.

This is materially more differentiated than conventional RAG.

#### Vision C — An evidence-grounded investigation platform

A generalizable system that can investigate a knowledge corpus, identify what it knows, discover what it does not know, select bounded investigative actions, evaluate evidence sufficiency and generate auditable conclusions.

Repository intelligence would be its first mature domain.

This is the most ambitious vision, and it implies more substantial research into planning, evidence assessment and investigation behavior.

Importantly, **Vision C does not require us to build a large autonomous agent framework immediately**. It is an architectural destination, not an implementation prescription.

#### My proposed direction: Vision C, delivered through Vision B

I would treat **repository intelligence as our proving ground** for a broader evidence-grounded investigation architecture.

That gives us a disciplined progression:

**Reliable retrieval → trustworthy evidence → structural understanding → bounded investigation → adaptive investigation.**

Each capability should be independently demonstrable before we depend on it for the next.

And I would retain one strict rule from our established development approach:

> **No significant mechanism gets promoted into the architecture without a measured improvement against a frozen evaluation and an explicit understanding of its regressions.**

This gives the project a coherent research agenda rather than an expanding collection of RAG features.

---

### 12. What I would discuss before approving more implementation

I would first settle three architectural decisions:

**First: What is our primary product identity?** A graph-aware RAG engine, a repository intelligence platform, or an evidence-grounded investigation platform? My preference is the third, with the second as the initial concrete application.

**Second: What is the fundamental unit of evidence?** Today we often reason about chunks, symbols and documents. But questions about behavior may require statements, code regions, relationships or coherent collections of these. Our E1 results make this an important design question.

**Third: Where should intelligence reside?** How much should be deterministic in structural extraction and retrieval, how much should be handled by evidence-sufficiency policies, and how much should be delegated to an LLM-driven investigator?

These decisions affect the next several workstreams, not merely Track B.

#### Bottom line

**We have 13 major workstreams across a six-layer architecture.** The immediate evidence-delivery effort contains two experimental tracks, but those are only one part of the larger roadmap.

The long-term opportunity is to create a system that **does not merely retrieve information, but can investigate complex repositories and documents, establish relationships, recognize insufficient evidence and produce source-grounded explanations**.

That is the vision I believe is worth evaluating before we initiate more GitHub issues.

## Observations

- The supplied discussion separates the platform's strategic destination from
  individual E1 experiments and from currently demonstrated implementation.
- The six-layer model, 13-workstream grouping and four horizons are useful
  proposed lenses for an audit; they do not establish completion or priority.
- The [existing E1 handoff](/DOCS/notes/20261108-e1-control-baseline-and-candidate-handoff.md)
  explicitly separates named-symbol ordering from statement-level delivery.
  Primary-function presence does not establish statement-level gate success.
- This capture records strategic thinking. It does not replace the single
  [Project Status](/DOCS/status.md) snapshot or independently verify the claims
  preserved in the Raw Input section.

## Ideas

- Use repository and document intelligence as the concrete proving ground for an
  evidence-grounded investigation platform.
- Evaluate acquisition, structure, discovery, delivery, sufficiency and answer
  generation separately so fixes address the failed boundary.
- Require measured benefits and explicit regression analysis before adopting a
  new retrieval, context-selection or investigation mechanism.
- Use an auditor's capability-to-evidence map to distinguish implemented,
  evaluated, proposed and deferred capabilities across the 13 workstreams.

## Questions

- Which product identity should the owner explicitly adopt: Vision A, B or C?
- What is the unit of sufficient evidence: a chunk, symbol, source region,
  statement, relationship or coherent set of those?
- Which responsibilities must remain deterministic, and which may be delegated
  to evidence policies or an LLM-driven investigator?
- What dated report and provenance establish the supplied Track A result claims?
- Which capabilities have end-to-end evidence, rather than only an implementation
  or a planned roadmap item?
- What evaluation isolation and owner decision are required before Track B,
  given the [existing disclosure of seen control outcomes](/DOCS/notes/20261108-e1-control-baseline-and-candidate-handoff.md)?

## Concerns

- Treating this strategic synthesis as an accepted specification would promote
  unverified status claims and proposed groupings into repository authority.
- Structural reachability does not prove runtime reachability; supported parsing
  does not prove full structural or query parity across languages.
- Candidate primary-delivery metrics do not substitute for source fidelity,
  complete statement coverage, sufficiency or answer correctness.
- Existing generation/lifecycle guarantees do not imply transactional staged
  activation, large-corpus capacity or enterprise readiness.
- Reading held-out results must not become a basis for tuning while still
  describing the same cases as untouched held-out data; follow
  [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md).
- Strategy discussion does not grant permission to mutate production or run
  experiments; follow [execution boundaries](/DOCS/deployment/agent-execution-and-verification.md).

## Possible Next Outputs

- An auditor's evidence map linking each strategic capability to source,
  acceptance criteria, tests and evaluation reports.
- Reconciliation of the original status claims against dated evidence.
- An owner discussion of the three product/evidence/responsibility decisions.
- A later proposal or ADR only if separately requested and explicitly accepted.

No issues, implementation plans, canonical-page changes or execution approvals
are created by capturing this note.
