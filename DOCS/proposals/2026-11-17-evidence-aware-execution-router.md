---
title: "Evidence-aware execution router: architecture proposal"
date: 2026-11-17
type: proposal
status: proposed
tags: [phase-6, architecture, routing, evidence, investigation]
related:
  - "[Tracking issue #382](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/382)"
  - "[Issue preparation record](/DOCS/proposals/2026-11-17-evidence-aware-router-issue.md)"
  - "[Experimental specification](/specs/009-evidence-aware-execution-router/spec.md)"
  - "[Evaluation protocol](/DOCS/evaluations/evidence-aware-router/protocol.md)"
  - "[Source navigation contract](/DOCS/architecture/source-navigation-api.md)"
  - "[Future-agent register](/DOCS/notes/brainstorm-20261116-future-agent-architecture.md)"
---

# Evidence-aware execution router

This proposes an architecture for evaluation under #382, Phase 6 / R and AG3,
with AG0 source-access prerequisites. Approval of the documentation work does
not adopt this architecture or authorize a router, investigator or harness.
The code profile is evaluated first. Sharing infrastructure with document
investigation remains an unvalidated hypothesis.

## Existing seams and ownership

At preparation commit `4366ab65fe5d186481fa0951575665db56e0c2cd`, inspected
[service.py](/rag_orchestrator/src/core/service.py) coordinates the current RAG
path, including generation resolution; [execute_plan.py](/rag_orchestrator/src/retrieval/execute_plan.py)
exposes retrieval execution separately. These are candidate adapter seams,
not proof of a ready model-tool API. [evidence_service.py](/rag_orchestrator/src/core/evidence_service.py),
[evidence_workflow.py](/rag_orchestrator/src/retrieval/evidence_workflow.py) and
[evidence_sufficiency.py](/rag_orchestrator/src/retrieval/evidence_sufficiency.py)
implement #200's bounded structural assessment. Its `satisfied` result retains
the meaning of its declared checks; it cannot establish an arbitrary answer's
global completeness. Model assessments are advisory.

[#379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)
and [PR #380](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/380)
provide deterministic file discovery and stored-source access. Preserve
[ADR-055's supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md),
[ADR-031](/DOCS/adr/ADR-031-canonical-identity-model.md) and
[ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md).
[#282](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/282)
remains separate batch/function-node work. This proposal does not supersede
[ADR-045](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md): current RAG is unchanged.
Any later production architecture needs an accepted ADR addressing that change.

## Selection and transitions

Start from caller-declared obligations and existing evidence. Select among
`deterministic`, `retrieval_synthesis` and `investigation`, subject to the caller's
maximum strategy. Try exact access where applicable. A mechanically satisfied
source/inventory request may finish without a model call. Explanation may need
one synthesis call. An overview may start with structural inventory and targeted
retrieval; there is no requirement to traverse every strategy.

Every transition records the current obligations and evidence, material gap,
proposed action, expected repair, permission, remaining resources and reason.
Investigation is permitted only when a material gap is identifiable and an
available action could address it. Query wording alone cannot trigger escalation.
Unavailable tools, failed services and source limits produce explicit outcomes.
They do not automatically justify a more expensive strategy. Multiple plausible
anchors require clarification; do not guess. Generation changes invalidate the
investigation; a new request must start from a newly pinned scope.

## Controller proposal

A plain Python controller inside the orchestrator boundary would own policy,
budget reservation, dispatch, generation fencing and evidence recording. A
replaceable model transport proposes structured actions. Isolated HTTP adapters
execute validated operations against existing services; the controller has no
database access. The prospective [interfaces](/specs/009-evidence-aware-execution-router/contracts/interfaces.md)
define scope injection, typed failures and result records. No dependency on an
agent framework or new service is proposed.

Allow only `orient`, `find_source`, `read_source`, `search_evidence` initially.
The last wraps retrieval without answer generation. No checkout, shell, grep,
web, delegation or arbitrary HTTP tool is exposed. Retrieved instructions are
untrusted source data and cannot modify controller policy, scope or budgets.

Keep one investigation-scoped objective, obligations, visited-material map,
evidence ledger, uncertainties, contradictions, remaining resources and decision
history. Each evidence reference retains identity, generation, source location,
hashes and the claims it supports. Track partial intervals explicitly; a source
hash proves content identity, not semantic support or complete discovery.

Use one investigator per request and isolate independent sessions. No learned
cross-session memory, restart resumability or memory database is proposed.
Research traces may persist as evaluation artifacts, never authoritative memory.

Reject identical normalized actions without redispatch; count their model cost
and record the rejection. Test stopping after three executed actions that add
no material evidence and resolve no obligation. New content alone is not material
progress: it must support/refute a claim, expose a relevant uncertainty or change
an obligation. Reset the consecutive counter on material progress. Treat the
threshold as a hypothesis and score premature stops using offline witnesses.

## Completion and limits

The specification separates evidence assessment from termination reason and
completion label. `Verified complete` requires mechanically checkable declared
requirements and full coverage within the declared scope. `Evidence-supported`
means findings have inspected support without established global completeness.
`Incomplete` exposes unresolved material obligations. `Budget-limited` records a
resource/deadline stop and preserves supported findings and open obligations.

A broad execution trace cannot become verified complete because its citations
are valid or a model sees no remaining gaps. Without the answer, the controller
cannot detect every omitted relationship. Hidden witnesses are available only
to offline scoring. They must never enter prompts, adapters or online completion
logic. Report contradictions and known limitations even when the controller
terminates normally.

## Decisions still requiring evidence

The [protocol](/DOCS/evaluations/evidence-aware-router/protocol.md) tests whether
correct source access already solves deterministic tasks, when ORIENT helps,
whether adaptive repair adds value and whether stopping controls are premature.
The [handoff](/specs/009-evidence-aware-execution-router/HANDOFF.md) specifies gates.
[#207](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/207)
remains deferred: evaluation design does not override its requirement to show
that simpler bounded repair fails. Positive experimental results alone cannot
authorize product implementation.
