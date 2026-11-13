---
title: "Repository intelligence strategy: proposed falsification experiments"
date: 2026-11-12
type: evaluation
status: proposed
summary: "Unexecuted protocol draft; task fixtures, budgets and acceptance gates require freeze before use"
tags: [evaluation, code-intelligence, agent-tools, retrieval, architecture]
authority: "Proposed experiment design; no implementation or benchmark execution authorization"
related:
  - "[Architectural challenge](/DOCS/notes/2026-11-12-strategy-notes/2026-11-12-repository-intelligence-architecture-challenge.md)"
  - "[Strategy discussion index](/DOCS/notes/2026-11-12-strategy-notes/00-Strategy-Discussion-Index.md)"
  - "[Evaluation isolation ADR](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Existing E1 statement-level contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
---

# Repository intelligence strategy: proposed falsification experiments

> **Scope correction, November 12:** This product-level protocol is deferred as
> the immediate plan. The owner requested mechanism diagnosis on the known
> LightRAG and self-repository failures first. Initial measured comparisons and
> the next engineering questions are recorded in the
> [retrieval-mechanism diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md).
> Coding-agent utility is not a prerequisite for investigating those failures.

## Decision target and status

Primary outcome, explicitly selected by the owner: **better coding-agent task completion**. Standalone repository Q&A is an important secondary objective. A higher recall score, more graph edges or a fluent explanation is insufficient for architecture selection.

This protocol is proposed and unexecuted. There are no measured winners, frozen new fixtures or approved numerical thresholds. The values below are concrete starting proposals for review. Implementation of experiment harnesses or prototypes requires an explicit decision and a GitHub issue assigned to a milestone. Live production access and re-ingestion are not part of this document's authorization.

## Hypotheses and rejection conditions

| ID | Hypothesis | Experiment | Evidence against it |
| --- | --- | --- | --- |
| H1 | Independent discovery channels and source reads remove most current failures | Fixed workflow versus current retrieval | Little improvement in final evidence or successful tasks despite increased recall |
| H2 | Adaptive selection of follow-ups adds value | Adaptive versus fixed workflow using the same primitives and resource caps | Equal-budget fixed workflow matches it, or gains vanish after accounting for extra reads/model calls |
| H3 | Repository tools help a coding agent | Same agent with and without tools | No credible success gain or comparable-success cost reduction |
| H4 | Better graph semantics are a priority | Disable graph, use current graph, then supply reviewed missing links | Removing graph does not hurt and oracle repairs do not help |
| H5 | Selection, rather than reasoning, dominates failure | Fixed generator with reviewed evidence versus retrieved evidence | Generator still fails with sufficient reviewed source |
| H6 | File-first discovery is competitive with chunk-first discovery | Same task and budget, different localization unit | Broad file reads waste budget without improving success |
| H7 | Committed snapshots are sufficient for agent work | Frozen snapshot tasks plus changed-working-tree tasks | Useful results become misleading or unusable after edits |

Rejecting one hypothesis does not automatically accept another. A result can be inconclusive, or expose a more basic source-access problem.

## Dataset separation and scoring preparation

Use the November 11 questions on this repository and LightRAG as diagnostic/regression cases. Do not call them held-out. Do not tune this strategy on the existing E1 held-out fixtures; preserve their frozen contract and independence accounting under [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md).

Proposed development pilot: 12 tasks across at least three repositories, combining six historical issue tasks at pre-fix commits and six understanding tasks. Include named anchors, broad workflows without anchors, error/configuration diagnosis, cross-module changes, branch/state dependencies, and one rationale/test-evidence control. Include at least two changed-working-tree variants as explicitly labeled diagnostic variants rather than independent tasks.

Proposed independent confirmation: 24 new tasks across at least six previously unused repositories, half issue tasks and half understanding tasks. Stratify by anchor availability and task complexity; represent Python, TypeScript/JavaScript, Rust and Java where runnable fixtures can be prepared. With this size, per-language results are descriptive, not proof of universal support. If resources require fewer languages, narrow the claims rather than treating languages as interchangeable.

An independent fixture curator should pin source commits, issue text and environment, and prepare the evaluator-only evidence rubric. Remove solution PRs, later commits, solution-bearing issue comments and hidden tests from the agent workspace and search index. Keep external web access identical across arms, preferably disabled during scored runs. Historical task contamination cannot be ruled out; record it and include fresh locally constructed or prospective checks before broad claims.

Ground truth is an acceptable-behavior rubric, not the reference patch's exact file list. Permit alternative correct fixes and equivalent evidence. For traces, specify required transitions, their conditions, direct versus HTTP/event boundaries, and acceptable uncertainty. For diagnosis, require the mechanism connecting symptom to cause and evidence distinguishing plausible alternatives. Validate references against the pinned source rather than copying DeepWiki answers.

## Stage 0: establish a usable experimental surface

Before scoring, freeze runtime commit, repository commit, index generation, embedding contract/model, generator and agent model identifiers, prompts, tool schemas, retrieval settings, tokenizer/counting method, environment and budget caps. Record corpus coverage and source availability. Reproduce old failures only where their captured state is actually available; do not substitute a new generation and label it a replay.

Use one verified current corpus for matched candidate comparisons. Preserve historical captures separately. A before/after re-ingestion comparison can diagnose representation changes, but changing embedding inputs, index generation and retrieval policy together cannot isolate architecture.

Verify that experiment tools return actual source text and coherent revision identity. ADR-055 records an accepted source-text design, not proof that a deployed endpoint exists. Missing source access is a prerequisite to resolve through the normal issue process, not a reason to silently simulate a production capability. Offline source reads are valid in mechanism experiments if disclosed consistently across all arms.

Stop if generation identity, source fidelity or test environments cannot be established. This is an invalid experiment setup, not an architecture failure.

## Stage 1: cheap headroom tests before building a planner

Perform these first on development fixtures, using saved evidence or reviewed source where possible. Oracle means evaluator-supplied evidence, never agent access to hidden answer keys.

| Test | Controlled comparison | What it resolves |
| --- | --- | --- |
| Discovery oracle | Actual candidates versus reviewed target candidates; unchanged selection/generator | Whether missing candidates explain failures |
| Delivery oracle | Same candidates; actual final context versus reviewed sufficient source passages | Whether context selection is the binding limit |
| Generator oracle | Same reviewed source; baseline versus stronger model | Whether retrieval alone has plausible headroom |
| Navigation oracle | Current versus disabled versus repaired task-critical graph links | Whether semantic enrichment deserves investment |
| Context control | Same ranked source pool at 4k and 16k evidence-token caps, if supported | Whether a larger window is a simpler effective intervention |
| File-first control | Map/file localization versus passage localization | Whether fragmentation is the larger discovery problem |

Keep oracle passages within the same evidence cap for matched comparisons. If sufficient evidence does not fit, mark that as a capacity finding and test a separately labeled larger-cap arm. Human selection is a diagnostic aid, not an automated candidate or a fair deployable cost comparison.

Do not run every combination. Select the dominant bottleneck, make one mechanistic comparison, and stop branches with little headroom. For example, no costly SCIP integration if repaired navigation does not improve downstream outcomes.

## Stage 2: separate retrieval policy from loop ownership

Use a common source/evidence interface for these mechanism arms:

- **R0:** captured current retrieval behavior, where reproducible; otherwise a clearly labeled current-runtime baseline.
- **R1:** fixed multi-channel discovery, optional bounded navigation, and source selection. No model-directed follow-up search.
- **R2:** adaptive follow-up selection using the same primitives, source access and final-evidence budget as R1.
- **R3:** fixed file-first localization and reading. No semantic index or persistent call graph required.

R1 must be a credible baseline, not the existing top-five vector search renamed. Include independent lexical/definition discovery. R2 must choose at least some subsequent actions from observed results; fixed repeated queries are not evidence of adaptation.

Proposed mechanism budgets: 16k cumulative returned source tokens, 4k final evidence tokens, at most 12 retrieval operations, and at most three follow-up rounds for R2. Record planner tokens and latency separately and include them in total cost. Also compare at equal end-to-end cost: R1 may spend the allowance R2 uses on planning on additional retrieval/reranking. Freeze exact operation semantics, limits and prices before running; tool-call count alone is not a resource equivalence.

Mechanism results explain where gains arise. They cannot select the primary product architecture without agent-task results.

## Stage 3: measure incremental coding-agent value

All arms receive the same base agent, workspace, tools, issue prompt, model, test access and total budget. The service remains read-only; edits and execution belong to the agent's isolated task workspace.

| Arm | Additional access beyond ordinary tools | Question |
| --- | --- | --- |
| A0 | None: search, file reads, navigation already available to that agent, shell/tests | How strong is the actual baseline? |
| A1 | Current RAG answer endpoint | Does the current product help or distract? |
| A2 | Best fixed evidence operation from Stage 2 | Can one good operation deliver most of the value? |
| A3 | Small primitive search/navigation/read toolset | Does external loop ownership improve task success? |
| A4 | Optional bounded internal investigator | Does delegated investigation beat A2/A3? |

Use A0 and A1 for diagnosis, then advance at most two challengers from development results. This avoids a large confirmatory search over many architectures. Compare graph-enabled and graph-disabled variants within the promising tool arm during development; otherwise a tool-interface win could be misattributed to graph quality.

Proposed task cap: 20 minutes wall time and 80k total model tokens across agent plus service calls, whichever is exhausted first. These are pilot values, to be revised for hardware/task feasibility before freezing. Count cached-token charges, planner calls, failures, tool payloads and service inference. Report cold indexing/setup separately and amortized at 1, 10 and 100 queries per snapshot; do not hide ingestion costs behind a warm-cache comparison.

Run three independent trials per task/arm where feasible, reset workspaces and histories, randomize execution order, and use paired seeds when the provider supports them. Score the first submitted patch in each trial, not the best of several outputs. A timeout is a failure under the chosen budget. Environment failures follow a predeclared symmetric rerun rule and remain reported.

Changed-working-tree variants should reveal whether tools can detect stale source and fall back appropriately. A tool that confidently navigates the wrong revision fails the task even if its frozen-snapshot result was accurate.

## Outcomes and adjudication

**Primary outcome:** issue resolution rate per independent trial: the patch passes held-out behavioral checks and the designated regression suite, with reviewer confirmation that it addresses the issue rather than weakening tests or hardcoding fixtures. Report diagnosis-only tasks separately; file localization does not count as a fixed issue.

**Secondary outcomes:** grounded diagnosis, complete and correctly qualified repository explanations, time and total cost, and rate of materially wrong source-backed claims. For a Q&A task, a pass requires all mandatory behaviors/conditions and valid supporting citations; justified abstention is scored separately from successful understanding.

**Diagnostic measures:** target-evidence recall, definition versus mention retrieval, verified transition coverage, final-context evidence survival, redundant bytes, source reads, unresolved ambiguity and wasted follow-ups. Do not optimize these as substitutes for task success.

Freeze a task-level scoring rubric before candidate results. Have two reviewers score blinded outputs where possible, resolve disagreements with source/test evidence, and report disagreement rates. LLM judging may assist triage but is not the sole acceptance authority. Curator/evaluator artifacts must stay outside agent-visible and service-indexed content.

Report paired per-task outcomes and per-repository summaries. Use uncertainty intervals that account for repeated trials and repository clustering; three runs of one issue are not three independent issues. With a small pilot, large intervals mean “inconclusive,” not “equivalent.” Retain all failures and all predeclared strata.

## Proposed decision gates

The following effect sizes are review proposals, not approved policy or statistically justified sample-size claims. Use pilot variance and cost to size confirmation before examining independent results.

| Decision | Proposed practical threshold | Stop or reconsider when |
| --- | --- | --- |
| Advance a repository-tool candidate | At least 10 percentage points higher issue success than A0, or at least 20% lower total cost with success non-inferior within 5 points | No practical advantage after counting setup and service calls |
| Add internal adaptation | At least 10 points additional success on predeclared evidence-dependent tasks over best fixed/tool challenger, within agreed cost cap | Gains require simply more budget, or primitive tools match them |
| Prioritize semantic indexing | Oracle link repair yields material task gains and a selective real index reproduces useful gains with measured setup costs | Edge counts improve without task benefit |
| Preserve Q&A quality | No more than 5 points loss on the secondary suite, and no increase in materially unsupported claims | Agent gains depend on a damaging shared selection policy |

Threshold point estimates trigger consideration, not automatic acceptance. For a positive confirmation, require paired uncertainty to exclude no improvement; for the cost-saving route, require the lower confidence bound on success difference to clear the proposed -5-point non-inferiority margin. If the sample cannot support that conclusion, report uncertainty and either expand under a newly frozen plan or limit the decision to a reversible pilot.

Any newly observed wrong-revision result or confident fabricated critical relationship triggers diagnosis before promotion. These are concrete correctness defects, not reasons to demand perfect coverage on all tasks.

## Execution record and governance handoff

For each run retain task ID, arm, source/runtime/model pins, settings, tool transcript, returned source identities, final evidence, answer or patch, test outcomes, timings/costs, adjudication and failure category. Store bulky captures under the existing ignored raw-results convention and index them; publish a concise result document under `DOCS/test_results/` linked to this protocol.

Recommended sequence:

1. Owner and independent reviewer challenge this design and choose the first headroom question.
2. Reconcile #342, E1, ADR-055 and related work so the experiment does not duplicate or contaminate existing efforts. No GitHub state was queried for this desk review; issue/milestone suitability must be verified at that step.
3. Record the explicit investigation decision and select/create a GitHub issue with a milestone before implementing any harness or prototype. Amend an ADR or write a spec where required by the scope.
4. Freeze development fixtures and the selected experiment contract; execute only that authorized scope.
5. Use development findings to choose at most two candidates; freeze an independent confirmation set before running it.
6. Record results, including null results. Make the architecture decision explicitly. Only then create the approved implementation work and milestone sequence.

No stage is an automatic authorization for the next. A finding that ordinary agent tools suffice is a successful investigation outcome.
