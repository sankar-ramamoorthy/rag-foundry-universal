---
title: "Future Agent Architecture: Open Design Questions"
date: 2026-11-16
created: 2026-11-16
type: note
status: proposed
summary: "Exploratory decision register captured from the owner's ChatGPT discussion. No agent architecture is selected or implementation authorized; return to #379 after capture."
tags: [brainstorm, agent-architecture, investigation, memory, sessions, delegation]
source: "Owner-pasted ChatGPT discussion, captured after the #379 database assessment; the discussion itself preceded those results."
related:
  - "[Source Navigation API #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[ADR-055 source-navigation supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md)"
  - "[#379 PostgreSQL assessment](/DOCS/test_results/2026-11-16-379-postgresql-source-ranges.md)"
  - "[Direction after #375 and #377](/DOCS/notes/20261116-direction-after-375-377-agent-over-local-index.md)"
  - "[Deferred investigator #207](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/207)"
---

# Future Agent Architecture: Open Design Questions

**Exploratory. No implementation commitment.** This records questions and initial
hypotheses for a dedicated architecture discussion before any agent controller
is implemented. It is not an ADR or a selected design. The questions apply to
both code intelligence and document intelligence in RAG-FOUNDRY-UNIVERSAL.

## Trigger

The owner discussed future agent architecture with ChatGPT before receiving
Codex's #379 PostgreSQL assessment. They then asked Codex to capture the details
and instructions before returning to #379. The completed database assessment is
linked for chronology; this note neither reopens that diagnostic nor expands
#379 into agent work. Use Foundry's existing `DOCS/notes/` for this repository
capture rather than introducing a separate wiki directory.

## Raw Input

The owner's pasted discussion follows. Only formatting artifacts were cleaned.

```markdown
Agreed. These are architectural decisions we should make before implementing an agent controller, rather than discovering later that we've built ourselves into a particular design.

And I would add one more question to your list: What constitutes an investigation session, and what state survives after it ends?

For RAG-FOUNDRY-UNIVERSAL, I'd distinguish four design decisions:

1. One agent or two? Should code and document intelligence use separate agents, or a common investigation engine with different tools and instructions?
2. Agentic memory: What should persist within an investigation, between questions, and across sessions?
3. Single-agent versus multi-agent: When does delegating to another investigator actually improve completeness, latency, or cost?
4. Investigation lifecycle: How do we bound execution, resume interrupted work, detect stale evidence, and know when to stop?

These are related, but they don't need to be decided together.

## My initial architectural preference

One shared agent execution engine, with specialized investigation profiles for code and documents.

That is different from insisting on one universal agent prompt.

Foundry Orchestrator

Routes standard RAG or investigation requests

Shared Agent Execution Engine

Model calls · Tool dispatch · State · Budgets · Termination · Tracing

Code investigation profile

File navigation, symbols, graph relationships, ORIENT, source evidence

Document investigation profile

Sections, page navigation, tables, OCR, citations, document evidence

Foundry Evidence Services

Existing indexed and persisted repository/document content

The benefit is that we implement the difficult orchestration machinery once, while preserving domain-specific behavior.

For example, a code investigator may follow imports, callbacks and dependency injection. A document investigator may follow headings, cross-references, tables and page references. Their tools and evidence-verification rules differ, even if the controller loop is identical.

## Agentic memory needs its own design

I'd separate memory into four categories.

| Memory | Example | Initial recommendation |
| --- | --- | --- |
| Working memory | Tool calls, observations, current reasoning context | Required |
| Investigation memory | Files visited, evidence found, unresolved questions, coverage | Probably required |
| Session memory | Previous questions and findings in a continuing conversation | Limited, explicit |
| Long-term learned memory | Reusable findings across investigations | Defer |

A key distinction: memory of an investigation is not authoritative source evidence.

If an agent remembers that function A calls function B, that finding must still be associated with the repository generation that supported it. A subsequent ingestion may invalidate it.

I would initially keep memory scoped to an investigation, with structured evidence references, and avoid adding a general-purpose agent memory database.

## Should Foundry spawn multiple agents?

Eventually, possibly. But I wouldn't make that the starting architecture.

Consider a code question involving an API route, database persistence and background workers. We could theoretically have three investigators examining separate parts of the execution path.

That sounds attractive, but it introduces new problems:

- Who divides the work?
- Can the investigators share evidence without duplicating discovery?
- Who reconciles contradictory findings?
- How do we know that an investigator missed something?
- Does parallelism justify additional context and model calls?

On local hardware, multiple model workers could also compete for the same constrained GPU resources. We shouldn't assume that spawning three agents means three times the throughput.

My starting point would be one agent per investigation, able to make multiple tool calls. The architecture should permit future delegation, but we should not implement it before demonstrating a need.

## An important distinction about memory and persistence

We should not conflate three things:

- Source persistence: The repository or document content Foundry ingested.
- Investigation state: What the agent has examined and what remains unresolved.
- Learned memory: Conclusions carried into future investigations.

These have different lifecycles and different validity requirements.

I consider that separation especially important given Foundry's existing generation-aware design.

## What we should record now

I would create a short future agent architecture decision register in Foundry, rather than an ADR committing us to a particular design.

## Future Agent Architecture — Open Design Questions

Status: Exploratory. No implementation commitment.

Scope: Agentic investigation for both code intelligence and document intelligence in RAG-FOUNDRY-UNIVERSAL.

### Decisions to evaluate

1. Shared agent execution engine versus separate code and document agents.
2. Domain-specific toolsets, instructions, and evidence-verification policies.
3. Working memory, structured investigation state, session memory, and long-term memory.
4. Single-agent execution versus controlled delegation to multiple agents.
5. Execution budgets, context limits, stopping conditions, cancellation, and resumability.
6. Repository/document identity, generation consistency, and invalidation of remembered findings.
7. Agent evaluation: evidence coverage, correctness, latency, model cost, and resource consumption.

### Initial hypotheses

- A shared execution engine with specialized investigation profiles may minimize duplicated infrastructure.
- Structured, generation-bound investigation state should precede long-term learned memory.
- A bounded single-agent implementation should establish the baseline before introducing multi-agent delegation.
- Existing Foundry evidence services should remain the authoritative source of investigation material.

These are hypotheses to test, not selected design decisions.

### Prerequisites

Complete the Source Navigation API work under #379, establish appropriate document-navigation capabilities, and benchmark single-agent investigations before committing to a broader architecture.

One final point: I would design the engine to be capable of handling multiple independent investigation sessions without assuming that each session needs multiple agents. Those are different scalability problems.

For now, let's complete #379. But before we begin agent implementation, I think we should have a dedicated architecture discussion covering these questions. We have enough evidence from the recent investigations to make that discussion substantive rather than speculative.
```

## Observations

The discussion separates source retention, deterministic evidence access and
agent-driven evidence discovery. It also separates three lifecycles: ingested
source, an investigation's progress/state, and findings reused by later work.
Memory of a finding is not independent authority for the underlying fact.

The proposed engine/profile split is a hypothesis about reusing orchestration,
not a requirement for a universal prompt. Multiple independent sessions and
multiple agents within one session are separate scalability questions.

The current generation-bound source design is relevant to any future state:
an evidence reference must retain repository/document identity and the snapshot
that supported it. A re-ingestion can make remembered conclusions stale. This
note does not promise historical source availability or a new memory store.

## Ideas

One possible arrangement, still unselected:

- Foundry orchestrator routes standard RAG or investigation requests.
- A shared execution engine handles model calls, tool dispatch, state, budgets,
  termination and tracing.
- A code profile supplies code-navigation tools, instructions and verification
  rules; it may follow imports, callbacks and dependency injection.
- A document profile supplies document-navigation tools, instructions and
  verification rules; it may follow sections, pages, tables and cross-references.
- Existing Foundry evidence services remain the authority for source material.

Tool examples in the pasted discussion are prospective capabilities, not claims
that all corresponding APIs exist. In particular, #379 still defers symbol
lookup and agent/model-tool integration.

| Memory category | Initial position to evaluate |
| --- | --- |
| Working memory | Required within a run: tool calls, observations and active task context. |
| Structured investigation state | Probably required: visited material, evidence references, unresolved questions and coverage. |
| Session memory | Limited and explicit across continuing questions; define scope and expiry. |
| Long-term learned memory | Defer; do not add a general-purpose agent memory database initially. |

Start evaluation with one investigator per investigation, capable of multiple
tool calls. Keep future delegation possible without building it before evidence
shows a benefit. Keep structured state generation-bound before considering
cross-investigation learned memory.

## Questions

All entries below remain open; none is a selected product architecture.

| Decision | Questions for the dedicated architecture discussion |
| --- | --- |
| Shared engine or separate agents | What controller behavior can be shared between code and document investigations? What must remain profile-specific? |
| Domain specialization | Which tools, instructions and evidence-verification policies differ? What navigation capabilities are prerequisites? |
| Memory boundaries | What persists within an investigation, between questions and across sessions? How is structured state distinguished from authoritative evidence and learned memory? |
| Delegation | When does another investigator improve coverage, latency or cost? How are work division, duplicate discovery, contradiction reconciliation and missed evidence assessed? |
| Investigation lifecycle | What starts and ends an investigation session? What survives completion, cancellation or interruption? What are execution/context budgets, stopping rules, cancellation and resume semantics? |
| Identity and invalidation | How do repository/document identities and generations bind evidence? How are stale findings detected and revalidated during continuation or resume? |
| Evaluation | How are evidence coverage, correctness, latency, model cost and resource use measured against a bounded single-agent baseline? |

Also evaluate independent-session concurrency separately from delegation inside
one investigation. The session concept, durable state, concurrency model and
whether work is resumable are unresolved, not implied by the word "agent."

## Concerns

- A convenient shared controller could hide materially different domain needs;
  shared infrastructure does not establish that one prompt or policy is enough.
- Investigation memory can become stale or misleading if detached from its
  source identity and generation. Persisted conclusions are not source evidence.
- Delegation adds coordination, reconciliation, repeated context and model-call
  costs. Missing evidence does not become detectable merely by adding agents.
- Local workers may compete for limited model/GPU capacity; more workers need
  not increase throughput. Treat this as a measurement question.
- Avoid committing early to a controller framework, a memory database,
  long-term learned memory, a multi-agent design or historical snapshot storage.
- The architectural questions are related but can be evaluated separately;
  do not turn the register into an oversized prerequisite for completing #379.

## Possible Next Outputs

Instructions for subsequent Codex work, preserved from the owner's request:

1. **Return to #379 after this capture.** Finish the deterministic source-access
   foundation without adding an agent controller, model tools, symbol search,
   code search or a memory subsystem to that issue.
2. Before agent implementation, hold a dedicated architecture discussion using
   this register and the recent source-navigation investigations as evidence.
3. Establish suitable document-navigation capabilities and measure a bounded
   single-agent baseline before committing to a broader architecture.
4. Evaluate shared engine/profiles, memory categories, delegation, lifecycle,
   evidence invalidation and independent-session concurrency explicitly.
5. Promote actual selected decisions through the normal Foundry issue/ADR
   process later. This capture creates no issue, ADR, implementation plan or
   implementation authorization; the hypotheses remain exploratory.
