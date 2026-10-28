---
title: "E1 statement-level contract addendum: GO pass rate"
date: 2026-10-28
type: experiment-contract
status: frozen-before-candidate-results
tags: [evidence-delivery, statement-level, go-threshold, held-out, adr-054]
related:
  - "[Frozen statement-level contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
  - "[Issue #280](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/280)"
  - "[Held-out manifest issue #281](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/281)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# E1 statement-level contract addendum: GO pass rate

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by
#280. This is the single addition the frozen contract permits (its section 11, row
4b). It fixes one number and does not modify the contract.

## 1. Status and binding

- **Applies to** the frozen contract whose SHA-256 (LF content) is
  `f0f67f33d629a1253d467be40da15dfc539371703d95353f59a2e2c5bdc20a33`
  (`statement-level-contract.sha256`). A CI test checks this addendum names that exact
  value.
- **Chosen by the repository owner on 2026-10-28** from three drafted options
  (exploratory, balanced, strict; see the draft comment on #280). The owner chose the
  **balanced option (Option 2)** and **delivery-only GO**.
- **Committed before** the held-out manifest exists and before any held-out or
  candidate result exists, as the contract requires. Frozen on commit; the SHA-256 of
  this file (LF content) is in `statement-level-contract-addendum-go-rate.sha256` and a
  CI test pins it. A change needs a new dated addendum that supersedes this one,
  committed before the held-out manifest is frozen.

## 2. Definitions

- **Delivery gate (per case):** the candidate passes when S3 is complete (every frozen
  operation and dependency expression is in the final context) and S4 (faithfulness),
  S5 (structure sufficiency) and S6 (budget) hold, exactly as the contract defines.
- **Control:** the unchanged control replay of the same case with the same pins, as the
  contract requires for the held-out set.
- **k:** the number of held-out cases the candidate passes at the delivery gate.
- **Win:** a case the candidate passes at the delivery gate and the control does not.
- **Worse than control** is as defined in contract section 9 (fewer required
  operations or dependency expressions covered, or a target the control kept is lost).
- A case whose required evidence was delivered through `chunk_fallback` for any
  document holding a required operation or dependency expression is **not a
  statement-mode success**: it counts toward neither k nor wins (contract section 8).

## 3. Decision rule

This rule applies to a held-out manifest of **exactly 12 cases over 3 repositories,
4 per repository**. Any other shape needs a superseding addendum committed before the
manifest is frozen.

**NO-GO** if any of:
- S4, S5 or S6 is violated in any case;
- any case is worse than its control;
- (the contract's other NO-GO conditions, unchanged).

**GO** only if all of:
1. **k >= 10** of 12;
2. **wins >= 5**;
3. in **each** repository, at least **3 of its 4** cases pass at the delivery gate;
4. no NO-GO condition applies.

**INVESTIGATE** otherwise. This includes the case where the control fails fewer than 5
held-out cases, because wins >= 5 is then unreachable and the experiment cannot show
improvement; it is reported as uninformative about improvement, not as a failure.

Safety conditions (faithfulness, structure sufficiency, budget, generation fencing) are
mandatory and are never averaged into a rate.

## 4. What GO means

GO permits the owner to **design a larger independent evaluation**. It does not
authorize a retrieval-policy merge, a deployment, or any production change, which the
contract already states for every result under it.

**Answer correctness (S8) does not decide GO, NO-GO or INVESTIGATE.** It is recorded
and compared against the control and is the principal question for the larger
evaluation that a GO would unlock. Evidence delivery and answer quality stay separate
metrics.

## 5. What this threshold can and cannot show

Computed under the simplifying assumption that cases pass independently (cases within a
repository are correlated, so the true false-GO risk is higher than these figures):

- A mechanism that passes each case with probability 0.5 reaches k >= 10 of 12 about
  1.9% of the time; at probability 0.8, about 55.8%; at 0.9, about 88.9%. A miss is
  INVESTIGATE, so a good mechanism that misses costs a repeat, not a verdict.
- With zero losses, 5 wins has a one-sided sign-test p-value of 0.5^5, about 0.03.
- 12 cases support at most an exploratory gate. A GO is not a statistically persuasive
  generalization claim.

## 6. Consequence for the held-out manifest (#281)

The control must fail at least 5 held-out cases for the improvement condition to be
reachable. Cases are therefore stratified toward the shapes where the development
control failed (long functions, widely spread witnesses, long signatures). This is done
by the pre-declared stratification in contract section 10, **not** by looking at control
results before freezing.
