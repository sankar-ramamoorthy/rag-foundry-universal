---
title: "Code Intelligence Outlook and Portability Goals"
date: 2026-11-10
created: 2026-11-10
type: planning-note
status: exploratory
scope: rag-foundry-universal
review_period: "January 2027"
source: "Owner-supplied ChatGPT planning discussion, captured on 2026-11-10"
authority: "Strategic discussion; estimates and directional goals, not an approved implementation roadmap, ADR, or execution authorization"
verification_status: "Planning claims preserved from supplied discussion; no fresh product comparison, time-tracking analysis, benchmark, or deployment verification"
aliases:
  - "Code Intelligence Outlook 2026-2027"
  - "Cloud, macOS, and Model Portability Goals"
tags:
  - code-intelligence
  - strategy
  - roadmap
  - cloud-deployment
  - macos
  - model-evaluation
  - portability
related:
  - "[Full vision and strategic roadmap](/DOCS/notes/20261110-full-vision-and-strategic-roadmap.md)"
  - "[November 10 code intelligence audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[Independent review and audit-author response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md)"
  - "[Audit overview](/DOCS/audit/00-Audit-Overview.md)"
  - "[Current project status](/DOCS/status.md)"
  - "[Agent execution and verification boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[Production Docker Compose guidance](/DOCS/deployment/production-docker-compose.md)"
  - "[Evaluation isolation and generalization](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Code Intelligence Outlook and Portability Goals

**Planning discussion captured November 10, 2026. Review in January 2027.**

> [!abstract] Purpose and authority
> Preserve the supplied discussion's reasoning about Code Intelligence maturity,
> competitive aspirations, cloud deployment, macOS validation and model experiments.
> Dates are estimates and directional targets. This note records thinking; it
> does not approve implementation, deployment, new issues, milestones, or experiments.
> [Project status](/DOCS/status.md) remains the current-state ledger.

This is an organized capture of the supplied discussion, rather than a verbatim
transcript. Copied favicon/citation fragments have been omitted. In particular,
the original discussion said it had checked competitors' current offerings, but
supplied no usable supporting page citations. Those comparisons are retained below
as the discussion's dated characterizations, not independently verified market facts.

The discussion follows the [November 10 audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)
and its [independent review and response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md).
It records convergence around focused investigations:

- **CI-01:** Bind graph exports and caches to one consistent repository generation.
- **CI-06:** Measure source coverage in effective embedding inputs.
- **CI-03:** Define reuse correctness separately for extracted artifacts, stored
  passages, and vectors.
- **CI-02 / CI-04:** Investigate the smaller structural API correctness issues
  alongside the foundational work.

DISCOVER, ORIENT, TRACE, EXPLAIN and IMPACT are question families with different
evidence requirements, rather than mandatory stages for every query. The proposed
next step is focused investigation, beginning with CI-01 and CI-06, rather than
another general architecture audit. This convergence is discussion-level agreement,
not proof that the findings have been repaired or an implementation plan approved.

## 1. Competitive outlook, 2026-2027

### Forecast and effort assumptions

The supplied forecast estimates a compelling Code Intelligence system in **3-4
months**, and competitiveness on selected leading-product capabilities in **6-12
months**. It does not expect overall parity with Sourcegraph, Augment Code or
Greptile within a year.

| Milestone | Planning estimate from November 10 | Intended meaning |
| --- | --- | --- |
| Trustworthy foundation | 4-8 weeks | Resolve the principal correctness and evidence-contract gaps. |
| Compelling system | 3-4 months | Reliable repository explanations and useful context for existing agents. |
| Selected SOTA capability | 6-12 months | Demonstrate competitiveness on deliberately chosen capabilities. |
| Full commercial-product parity | Not expected within 12 months | Breadth, precision, integrations and operational maturity remain substantially larger goals. |

These estimates assume continued agent-assisted development and roughly **10-20
focused engineering hours per week**, with the current scope controlled. They are
judgments, not measured forecasts. The discussion suggests roughly doubling calendar
duration at five hours per week; that is a rough heuristic, not a linear capacity model.

### Why the discussion considered this plausible

The July-November history shows substantial progress from graph correctness and
ingestion scalability problems toward a language-neutral IR and Python,
TypeScript/JavaScript, Rust and Java extractors; transactional persistence and
bounded embedding; inventory, provenance and generation-aware retrieval; and
deterministic structural workflows and evidence-survival diagnostics.

The recurring constraint is that implementing a capability takes less time than
establishing its reliability. Graph expansion can find an artifact whose essential
evidence is subsequently lost. A generation-aware cache can still lack snapshot
binding. Incremental reuse can exist without a sufficiently complete derivation
identity. These examples explain why architectural progress does not immediately
translate into trustworthy answers.

The supplied estimate allocates perhaps **one-third to one-half** of elapsed
engineering effort to implementation, with evaluation, debugging, integration and
hardening taking the remainder. This is an experience-based judgment, not a
time-tracking statistic.

### Qualitative six-month outlook

This table preserves the discussion's assessment; it is not a fresh source audit
or a measured competitive scorecard.

| Capability | Position described in the discussion | Six-month aspiration |
| --- | --- | --- |
| Repository structural inventory | Strong foundation | Potentially comparable on selected inventory tasks. |
| Symbol/call/import graph | Functional, approximate semantics | Useful, but below precise semantic indexers. |
| Provenance and auditability | Promising architecture | Potential differentiator. |
| Cross-file explanation | Improving, insufficiently validated | Potentially competitive on bounded tasks. |
| Architecture understanding | Structural primitives exist | Useful, bounded explanations. |
| Behavioral reasoning | Early evidence contracts | Moderate and uneven capability. |
| Change impact analysis | Candidate relationships supported | Useful, not comprehensive. |
| Large enterprise repositories | Insufficiently benchmarked | Likely behind market leaders. |
| IDE integration and user experience | Early-stage | Likely behind market leaders. |

### Product comparisons preserved from the discussion

**Sourcegraph: structural precision benchmark.** The supplied discussion describes
SCIP and language-specific indexers, including compiler-derived information where
available, as supporting precise navigation across references, implementations,
dependencies and repositories. Our static extraction and heuristic graph resolution
are not equivalent to compiler-semantic precision. The forecast does not expect
matching that coverage in six months. A more plausible comparison is repository-wide
explanation combining structural evidence, exact source and provenance.

**Augment Code: context-delivery comparison.** The discussion describes its Context
Engine as indexing repository and organizational knowledge, supplying agent context
through MCP, and supporting cross-repository context and synchronization. This is
close to the desired role of RAG-FOUNDRY-UNIVERSAL. Transparent retrieval, local
deployment and inspectable evidence could support a useful targeted alternative.
The aspiration is narrow task competitiveness, rather than matching the complete
Context Engine or its context-efficiency and task-completion optimization.

**Greptile: a broader, moving product target.** The original discussion claims
code review, codebase context, PR testing and interaction with running applications,
including October 2026 computer-use testing releases. These specific dated claims
were not verified during capture and need authoritative sources before reuse as
facts. The proposed comparison is evidence-backed structural analysis and impact
assessment; replicating a complete review and runtime-testing product would expand
scope substantially.

**DeepWiki: repository-understanding comparison.** Repository explanations,
architecture descriptions and diagrams are considered a more approachable near-term
benchmark. Inventory and service-topology primitives could support a credible
experience in three to four months, provided explanations are source-grounded.
Comparable breadth and user experience would require separate evaluation and work.

**Claude Code and Codex: agent-alone baselines.** The proposal is to augment capable
coding agents and test the incremental value of persistent repository intelligence.
The same agent without this subsystem is an essential comparison, rather than
assuming a sophisticated retrieval architecture necessarily improves agent results.

### Projected development sequence

| Proposed period | Focus | Examples from the discussion |
| --- | --- | --- |
| Weeks 1-6 | Trustworthy foundations | CI-01, CI-06, CI-03, CI-05; small structural correctness checks and focused validation. |
| Weeks 7-12 | Useful code intelligence | Exact source delivery, bounded behavioral explanation, TRACE/IMPACT quality and a thin agent-facing MCP interface. |
| Months 4-6 | Competitive evaluation | Unfamiliar repositories, agent-alone versus agent-plus-RAG comparisons, performance and semantic-resolution improvements. |
| Months 7-12 | Selected advanced capabilities | Cross-service evidence, revision-aware impact, greater scale and repeatable workflows. |

These are proposed planning groupings, not approved phases with exit dates.
A thin MCP interface is suggested early because it could test value with existing
agents without requiring a new agent implementation. Its scope and acceptance
criteria still require a decision.

### Success criterion and forecast confidence

The strongest proposed identity is a **trustworthy, persistent, graph-aware
repository intelligence engine supplying verifiable evidence to capable agents**.
Its testable value proposition is whether the same agent answers more accurately,
uses fewer tool calls, makes fewer unsupported claims, or achieves lower latency
when equipped with this engine across unfamiliar repositories.

| Forecast in the supplied discussion | Stated confidence |
| --- | --- |
| Principal audit correctness gaps resolved in 4-8 weeks | Moderately high |
| Compelling demonstration within four months | Moderate to high |
| Measurable agent advantage within six months | Moderate |
| Selected SOTA capabilities within twelve months | Moderate |
| Leading-product breadth, accuracy and operational maturity within twelve months | Low |

The calendar aspirations were **March 2027** for a strong demonstration, **May
2027** for a useful agent-connected engine, and **November 2027** for competitiveness
in selected areas. Competitive success must be supported by independently measured
performance. The suggested reference points are Augment-style context delivery
and Sourcegraph-style evidence precision, with realistic scope for each.

## 2. Near-term infrastructure goals

The directional goal is a working cloud deployment around **December 15-20, 2026**,
outside the existing Linux environment. The objective is to learn whether the current
architecture can be deployed, ingest a repository, answer a query and be operated
in a different environment. It is not a claim of production readiness.

The original discussion proposed the following options, without a hosting selection,
cost comparison or capacity validation:

| Option | Proposed role | Question to resolve |
| --- | --- | --- |
| AWS EC2 | Primary candidate, retaining Docker Compose on a modest instance | What application resources and inference arrangement are sufficient? |
| RunPod | Alternative if GPU inference is the principal obstacle | Is GPU hosting the limiting requirement rather than application hosting? |
| DigitalOcean | Simpler alternative, especially with separate inference | Can application and model hosting remain operationally simple? |

Retain the existing service architecture for this exploration. Kubernetes and a
deployment redesign are outside the proposed goal. Cloud exploration should expose
environmental assumptions and distinguish them from architectural dependencies.

Any later execution must follow the existing
[operator-owned deployment boundaries](/DOCS/deployment/agent-execution-and-verification.md)
and [deployment guidance](/DOCS/deployment/production-docker-compose.md).
This note does not authorize provisioning, spending, deployment or ingestion.

## 3. macOS and model experiments

The proposed **December 2026-January 2027** exploration is parallel to the cloud
goal and depends on available hardware. It asks whether the application works
reliably on macOS, whether Apple Silicon provides useful local inference, and how
stronger embedding and generation models affect results.

The supplied discussion names `mxbai-embed-large` and a Qwen3-based generation
baseline. These names describe its assumed baseline; the exact effective model
identities, revisions, settings and hardware must be recorded before comparison.
No new candidate model selection is made by this note.

Compare a small selection of code-capable embedding models and larger generation
models using controlled, reproducible development evaluations. Assess retrieval
changes separately from generation changes: a stronger LLM may improve answers
without repairing missing evidence. Embedding changes may also require deliberate
index/reuse decisions rather than swapping a model label against existing vectors.

| Target window | Objective | Proposed success criterion |
| --- | --- | --- |
| Mid-December 2026 | Cloud portability | Working end-to-end ingestion and RAG query in a separate environment. |
| December 2026-January 2027 | macOS portability | Core services and inference validated on the available hardware. |
| December 2026-January 2027 | Model comparison | Reproducible comparison against an explicitly recorded baseline. |
| Q1 2027 | Architectural learning | Document deployment assumptions and provider/model portability limits. |

The purpose is to test portability and architectural flexibility. These goals
should remain bounded parallel explorations rather than prerequisites for CI-01
and CI-06 or a large infrastructure program. Model-provider abstraction should
earn a portability claim through actual validation.

## 4. Assumptions, uncertainty and review points

### Principal risks to the forecast

1. **Static resolution:** Tree-sitter extraction and heuristic resolution do not
   always reproduce compiler understanding. SCIP or language-server enrichment
   may eventually merit investigation; neither is selected here.
2. **Behavioral reasoning:** Finding code is easier than correctly explaining
   branches, exceptions, state transitions and service-boundary behavior.
3. **Generalization:** Success on this repository is insufficient. Use unfamiliar
   repositories, varied architectural styles and properly separated evaluations.
4. **Scope expansion:** Simultaneous new agents, databases, languages, major UI work
   and enterprise deployment would materially extend the schedule.
5. **Moving comparisons:** Commercial tools and frontier agents will continue to
   evolve. Reproducing a dated feature list is not a durable success criterion.
6. **Effort and hardware:** Available focused hours, memory, inference throughput,
   platform support and hosting cost remain constraints rather than verified inputs.

The [evaluation isolation rules](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)
continue to apply. This planning discussion does not permit tuning against frozen
held-out cases or imply authorization for candidate execution.

### January 2027 review

Revisit this dated snapshot in **January 2027**, without silently rewriting the
original forecast. Record what actually happened and revise expectations explicitly:

- Were the cloud and macOS goals attempted, and what was independently verified?
- Which CI-01/CI-06 investigations reached decisions, and which guarantees remain open?
- What do controlled model comparisons establish about discovery, delivery and answers?
- Does unfamiliar-repository evaluation support an advantage over the same agent alone?
- Did actual effort and hardening time match the 10-20-hour/week assumption?
- Do the March, May and November 2027 aspirations still fit the evidence and scope?
- Which product comparisons need refreshed primary-source verification?

### Record ownership and reference copies

The repository Markdown note is the intended canonical record of this planning
discussion. A copy in ChatGPT Project Sources was recommended for convenient future
reference. Such a copy would be a dated snapshot and would not automatically
synchronize with GitHub. Saving this file does not establish that a Project Sources
upload occurred; no upload or synchronization has been performed here.

The broader destination remains the
[full strategic vision](/DOCS/notes/20261110-full-vision-and-strategic-roadmap.md):
reliable evidence and repository understanding supporting bounded investigation.
These forecasts and portability goals add context to that vision without creating
new implementation commitments.
