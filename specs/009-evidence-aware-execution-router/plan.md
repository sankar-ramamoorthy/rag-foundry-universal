# Documentation and experimental preparation plan

**Branch**: `docs/evidence-aware-execution-router` | **Date**: 2026-11-17
**Tracking issue**: [#382](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/382)
**Roadmap**: Phase 6 / R, AG0 and AG3
**Input**: [spec.md](spec.md), owner-approved documentation plan.

## Deliverable and technical context

Deliver documentation and JSON manifests only. Proposed experimental controller:
plain Python, isolated HTTP adapters and replaceable model transport. There is no
implemented runtime, dependency addition, storage change or deployment in this PR.
The initial code profile tests four tool contracts; document profiles remain a
hypothesis. Source baseline is `4366ab65fe5d186481fa0951575665db56e0c2cd`.

## Constitution check, before and after design

| Principle | Result and evidence |
| --- | --- |
| I, identity/ingestion | PASS: documentation only; reference ADR-031 in spec, no ingestion changes. |
| II, ownership | PASS: proposed controller stays in orchestrator, HTTP adapters only; no DB access added. |
| III, evidence before architecture | PASS: experimental design with simpler baselines; no architecture adoption or production changes. |
| IV, model provenance | PASS: current model-routing behavior unchanged; future matched runs must verify actual model and reject silent fallback. |
| V, embedding lifecycle | N/A: no index/model/embedding changes. Future run records actual index configuration. |
| VI, issue traceability | PASS: #382 created before spec/plan; Phase 6 in issue, no GitHub milestone. |
| VII, ADR references | PASS: spec links governing ADRs without redefining their rules. Later product router needs an ADR addressing ADR-045. |
| VIII, TGD/evaluation | PASS for documentation: AC-01 through AC-16 precede any future implementation. No executable spike; future authorization requires skeletal tests and frozen quality protocol. |

Rechecked after design: same results; no exceptions requested. Acceptance of this
experimental documentation is distinct from approval of later implementation.

## Work sequence and boundaries

1. Create tracking issue and documentation branch.
2. Write proposal, requirements, acceptance fixtures and proposed interfaces.
3. Define twelve cases, baselines, experiments, scoring and manifest freeze gates.
4. Write handoff/tasks, add navigation/status/documentation-log links.
5. Validate JSON, frontmatter, local links, case counts/pins and question fidelity,
   whitespace and scope of changed files; publish branch and PR citing #382.

No runtime changes means service unit/integration/model tests are not applicable
to this change. Perform content checks locally and record exact results in PR.
Do not run the stack or contact production to validate a proposed experiment.

## Future execution gates

G1: owner accepts experimental design and separately authorizes a scoped harness/
prototype issue; #207's simpler-repair evidence gate remains intact.
G2: implement acceptance fixtures first under that authorization; validate adapter
capabilities, corpus provenance and isolation without model expenditure.
G3: complete and approve frozen run manifest with provider/model, budgets, prompts,
scoring and sealed evaluator artifacts; only then execute selected experiments.
G4: report all attempts, limitations and separate routing/answer scores.
G5: fresh sealed generalization evidence and explicit product scope/ADR/rollout
approval before product implementation. No gate implicitly authorizes the next.
