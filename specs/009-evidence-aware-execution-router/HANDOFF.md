# Fresh-context execution handoff

Tracking: [#382](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/382),
Phase 6 / R, AG0 and AG3. Branch: `docs/evidence-aware-execution-router`.
Preparation baseline: `4366ab65fe5d186481fa0951575665db56e0c2cd`.

## Read first

Read [CLAUDE.md](/CLAUDE.md), [constitution](/.specify/memory/constitution.md),
[documentation standard](/DOCS/standards/okf-documentation.md), then
[spec](spec.md), [plan](plan.md), [tasks](tasks.md),
[proposal](/DOCS/proposals/2026-11-17-evidence-aware-execution-router.md),
[interfaces](contracts/interfaces.md) and
[protocol](/DOCS/evaluations/evidence-aware-router/protocol.md).
No prior conversation or context reset is assumed.

## Authorization and current state

Owner authorized the architecture/evaluation issue and documentation package,
including manifests, scoring and this handoff, through branch and PR. No
production router/agent, experiment harness, model calls, framework, persistent
memory, new service or deployment is authorized. Proposed architecture is not
an accepted ADR. All experiments remain unexecuted and the manifest is unfrozen.

#379 / PR #380 supply source access; #200 supplies scoped structural assessment.
#207 remains deferred with its evidence gate. Keep #282 separate. Inspect current
issue/code state before future execution; source paths and service availability
are not guaranteed by an old document. Use Phase 6 references, never milestones.

## Exact next steps after documentation review

1. If only asked to resume documentation, finish its review/publication and stop.
   Do not infer implementation permission from approval of the proposed design.
2. For an explicitly authorized experimental implementation, create/reference
   its issue and branch, settle applicable ADR requirements, and implement
   AC-01 through AC-16 fixtures before/alongside the first spike. Keep product
   paths unchanged. Start with plain Python and the four adapters; no checkout.
3. Have an evaluator prepare the missing nine case witness rubrics and seal all
   expected evidence outside model/retrieval access. Preserve H question bytes;
   label all twelve as development. Never ingest Foundry reports/answer keys as
   experimental source. Run generation/source/capability/leakage preflight.
4. Copy run-manifest.template.json to a versioned run manifest. Resolve every
   required null, choose exact A/B/C cells and repeats, pin source/generation and
   actual tools/runtime/models, freeze prompts/settings/scoring/hashes and obtain
   explicit provider/model/spend approval tied to the manifest hash receipt.
   Do not spend tokens while these gates are incomplete.
5. Execute only approved cells. Keep four matched arms, mandatory applicable
   direct-answer controls and no silent fallback. Persist all attempts and
   decisions; preserve partial findings and distinguish resource/tool failures.
6. Finalize and hash captures before evaluator access; score routing and answers
   independently using protocol definitions. Index bulky captures under
   DOCS/test_results/_raw/ using scripts/raw_index.py; report from the index.
7. Review quality, cost, latency and resource tradeoffs explicitly. A positive
   development result cannot establish generalization or authorize product work.
   Obtain fresh sealed evaluation and a separately approved product issue,
   ADR/spec as applicable and rollout scope before any production implementation.

## Known preparation limits

Budget profiles and three-action stagnation are hypotheses. Provider/model and
spend are deliberately unapproved. No current corpus generation is certified by
this package. Historical H generation is only a reference, not a reusable pin.
No document profile, graph navigation arm, grep tool, delegation, durable session
memory or restart/resume capability is specified as initially available.
