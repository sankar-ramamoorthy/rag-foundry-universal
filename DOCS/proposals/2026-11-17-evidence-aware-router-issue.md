---
title: "Phase 6: evidence-aware execution router architecture and evaluation issue"
date: 2026-11-17
type: proposal
status: proposed
tags: [phase-6, routing, evaluation, investigation]
related:
  - "[Tracking issue #382](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/382)"
  - "[Architecture proposal](/DOCS/proposals/2026-11-17-evidence-aware-execution-router.md)"
  - "[Phase 6 roadmap](/DOCS/audit/07-Roadmap.md)"
  - "[Future-agent register](/DOCS/notes/brainstorm-20261116-future-agent-architecture.md)"
---

# Phase 6: evidence-aware execution router architecture and evaluation

Prepare a governed architecture proposal and experimental specification for
selecting deterministic lookup, retrieval plus synthesis, or bounded investigation
inside the existing orchestrator boundary. These are selectable strategies.
Natural-language wording supplies candidate anchors; escalation requires an
identifiable material evidence gap, an available repair, caller permission and
remaining budget.

## Authorized deliverables

- Architecture proposal, SDD spec/plan/tasks, interfaces and fresh-context handoff.
- Twelve development-case contracts, run-manifest template, independent scoring
  definitions and reproducible acceptance scenarios.
- Documentation branch and PR referencing this issue and **Phase 6**; no GitHub
  milestone assignment.

Production router/agent implementation, harness implementation, model runs,
deployment, service changes, new frameworks and persistent memory are excluded.
Experimental implementation requires separate explicit authorization. Model runs
also require a complete, approved, frozen manifest and approved provider/model.

## Required design and evaluation constraints

1. Separate evidence assessment, completion classification and termination reason.
   Valid citations do not establish complete execution traces; hidden witnesses
   are offline scoring evidence only. Preserve #200's scoped structural checks.
2. Specify a plain Python controller, replaceable model transport and isolated
   tools: orient, find_source, read_source, search_evidence (no generation).
   Controller policy owns scope, validation, budgets and dispatch. One investigator
   per request; isolate sessions and invalidate on generation change.
3. Compare unchanged RAG, mandatory applicable direct-answer baseline,
   evidence-aware routing and bounded investigation using matched models and
   budgets. Score routing separately from answer quality and report incomplete
   runs and resource constraints.
4. Sequence minimal Foundry-only loop, ORIENT ablation and bounded controls.
   Missing Lab grep is a tooling difference; graph navigation is a separate arm.
5. Define scope, generation, partial source, capability, cancellation, duplicate,
   stagnation, deadline, budget and false-completion acceptance checks.

## Acceptance and gates

The PR must provide a self-contained handoff, freeze requirements, accounting
rules, twelve declared development cases (including H-1/H-2/H-3), scoring rubric
and product decision gate. Apply ADR-054: revealed cases cannot support new
generalization claims. Product work requires demonstrated benefit against the
relevant simpler baseline, explicitly reviewed quality/cost/latency/resource
tradeoffs, fresh sealed evaluation and a separately approved implementation issue.

Dependencies/context: [#200](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/200)
evidence assessment; [#379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)
and [PR #380](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/380)
source access; deferred [#207](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/207).
Keep [#282](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/282)
batch/function-node access separate. This issue does not reopen those scopes or
override #207's evidence gate.
