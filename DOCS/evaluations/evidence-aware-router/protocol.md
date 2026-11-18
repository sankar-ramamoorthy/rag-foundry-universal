---
title: "Evidence-aware router: experimental protocol and scoring"
date: 2026-11-17
type: evaluation
status: proposed
tags: [phase-6, evaluation, routing, evidence, budgets]
related:
  - "[Issue #382](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/382)"
  - "[Specification](/specs/009-evidence-aware-execution-router/spec.md)"
  - "[Case manifest](cases.json)"
  - "[Run manifest template](run-manifest.template.json)"
  - "[Intent and answer-obligation experiment](/DOCS/evaluations/intent-obligations/protocol.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Experimental protocol and scoring

This protocol is proposed and unexecuted under #382. The JSON manifest is a
non-executable template. Corpus UUIDs, approved provider/model, prompt bytes,
scoring artifacts and execution approval remain unset. Complete and freeze them
before running; null values are blockers, never permission to infer defaults.

## Task contracts and isolation

[cases.json](cases.json) declares twelve development cases: three exact-source,
three Python inventories, three overviews and the original H-1/H-2/H-3 questions.
Self-repository cases use the preparation commit. Mealie traces retain the exact
public questions and source commit from [359-H/questions.json](/DOCS/evaluations/359-H/questions.json).
Do not copy expected chains into the experimental workspace. Their public
availability does not make them legitimate model input. Mount only pinned
application source and approved runtime assets, exclude Foundry evaluation,
report and handoff documents from retrieval, and disable arbitrary web/checkout
access. Independently inspect corpus ingestion coverage for answer-key leakage.
Experiments use Foundry APIs, never the implementation agent's checkout tools.

An evaluator freezes authoritative witnesses in a separate inaccessible location
and commits their hash before runs. Scorer access occurs only after run captures
are finalized and hashed. Freeze the witness denominator, core/optional labels,
acceptable equivalent evidence, supported-claim rules and adjudication procedure.
The nine new contracts require evaluator preparation; no answers are fabricated
here. H-1/H-2/H-3 were already revealed and influenced design, so all twelve cases
are development diagnostics under ADR-054. Historical held-out labels in #359
describe that earlier run, not the independence of this experiment.

For exact source, compare stored UTF-8 text/hash and expected interval semantics,
not an unqualified claim of original Git byte identity. Python inventories use
stdlib AST over the full stored module, recursively including FunctionDef and
AsyncFunctionDef, nested functions and methods; exclude lambdas. Return qualified
lexical name, sync/async kind, def line and end line; decorated functions count
once and start at the def line. Require full-source coverage and parse success.
Overviews require services, entrypoints, persistence ownership and HTTP boundaries
within the declared scope. Traces require actual implementations, ordering,
conditions, indirect/deferred calls, persistence and external boundaries from
the question. Overview/trace coverage remains offline; online completeness is
not established by finding all currently known obligations.

## Matched arms

| Arm | Contract |
| --- | --- |
| Existing RAG | Unchanged retrieval and answer generation; record actual settings and model, no router instrumentation that changes behavior. |
| Direct answer | Exact source access and deterministic processing; at most one synthesis call when explanation is required. No iterative investigation, hidden file hints or oracle entry points. Mandatory for exact-source and inventory cases; overview/trace applicability must be declared before freeze with reasons. |
| Evidence-aware router | Deterministic-first selection using declared obligations and available evidence; controlled investigation only under the spec's gap/repair/permission/resource conditions. |
| Bounded investigation | Start a single investigator directly using the same permitted tools, model and resource ceilings; isolates the value of the router's invocation decision. |

Every matched cell uses the same source/generation, model revision, prompt policy,
hardware/service configuration and profile ceilings. Arm-specific prompt bytes
may differ for their role but must be frozen and recorded. Exact-source paths
already in a question are legitimate anchors, never evaluator additions. Cases
unsuitable for direct answering are reported as predeclared not-applicable, not
silently omitted or scored as zero-cost success. Verify the actual served model;
silent fallback invalidates the matched comparison. Do not modify product
fallback defaults to accomplish this: enforce or detect it in the future harness.

## Sequence and controls

- A, minimal loop: existing Foundry capabilities only, no checkout access. Lab's
  grep capability is absent; classify the difference as tooling. Do not simulate
  grep using hidden source selection or attribute its absence to model reasoning.
- B, structural contribution: matched navigation/retrieval with and without
  ORIENT. In the ablated arm omit ORIENT outputs and calls; keep all other tools,
  prompts apart from capability declarations, settings and ceilings matched.
  Graph navigation requires a separately specified arm with frozen tools/settings;
  it is excluded from the initial four-tool experiment.
- C, bounded execution: evaluate task-specific assessments, duplicate suppression,
  three-action stagnation and resource/deadline controls, including the spec's
  deterministic acceptance fixtures. Score premature stagnation offline. Any
  threshold variation is a separately preregistered arm, not post-hoc tuning.

The run manifest selects exact cells rather than implying all combinations are
authorized. Freeze repeats, execution order/seed, warmup/cache policy and concurrency.
Proposed initial repeats: three per selected cell, serial execution, seeded
randomized order. Freeze hardware/model queue policy and record warm/cold status;
these are proposals until approved. Keep failed attempts and retries visible.

## Budget hypotheses and accounting

| Profile | Tool calls | Model calls | Aggregate model tokens | Wall time |
| --- | ---: | ---: | ---: | ---: |
| Small | 8 | 10 | 32,000 | 60 seconds |
| Medium | 20 | 22 | 160,000 | 180 seconds |
| Large | 40 | 42 | 1,000,000 | 600 seconds |

These are uncalibrated hypotheses. Freeze an explicit monetary cap per cell and
total approved spend ceiling as well. Count all dispatched tool/model attempts,
retries, assessments, cached/repeated input tokens, output tokens and final
generation. Duplicate proposals incur their model usage but no tool dispatch.
Capture tokens by input/output/cache category and count aggregate usage once;
cached input is included in total input, not double-counted as an extra category.
Local inference still consumes tokens and elapsed resources even if no provider
charge applies. Unknown price/usage is null with reason, never zero. State how
conservative reservation enforces hard caps; block dispatch if it cannot.

Wall time begins at request admission and ends after final result capture;
startup/queue time is included when observable. Set per-operation timeout to
remaining deadline and reserve final-answer resources. Record tool time, model
time, startup/queue effects and unclassified overhead separately. Do not infer
unobservable queue time or subtract it from the primary wall-time result. A slow
local model exhausting Small is a resource constraint, not automatically a
reasoning or routing defect. No automatic larger-profile retry or provider swap.

## Independent routing score

Adjudicate each decision from its recorded information, without using future
evidence to assume the controller knew an answer. Freeze a decision rubric:

| Dimension | Failure rule |
| --- | --- |
| Unnecessary investigation | Lower strategy had sufficient declared evidence or an applicable deterministic operation could satisfy it without an investigation. |
| Unsupported escalation | No material gap, available repair, caller permission or sufficient resource reservation at transition. Record which condition failed. |
| Missed repair | Identifiable material gap and available permitted repair with budget remained, but controller stopped without a justified constraint. |
| Excessive lower-strategy work | Redundant actions despite a recorded unresolved gap whose necessary strategy was already evident; adjudicator cites the decision and better permitted action. |

Label each decision appropriate, inappropriate or indeterminate with rationale.
Report counts/rates with eligible denominators and indeterminate counts. Report
per-request presence of each failure and unnecessary investigator invocation
rate. Different legitimate strategies may both be appropriate. No retrospective
minimum-strategy oracle derived from hidden answers is used. A correct expensive
answer does not erase a routing failure.

## Answer and investigation score

Score final captures independently of routing; report components, not a weighted
score. For each case report required/core/optional witnesses supported, unsupported
claims, contradictions, correct findings, uncertainty and completion-label accuracy.
Witness coverage = supported required witnesses / valid frozen required witnesses;
also report core and optional coverage separately. A cited source must support the
relationship/condition asserted; merely citing both symbols is insufficient.
Unsupported-claim rate = unsupported substantive claims / substantive claims;
zero claims gives not-applicable, never perfect correctness. Record incorrect
claims separately and distinguish absent evidence from an explicit false claim.

Exact source: report hash/text agreement and complete/partial coverage. Inventory:
report missing and extra entries plus name/kind/line mismatches; verified complete
requires exact agreement and source completeness. Overview/trace: report required
finding/relationship coverage and unsupported assertions; do not award verified
complete merely for complete rubric coverage. Record false-completion count and
honest acknowledgement of unresolved obligations. Freeze claim segmentation and
equivalence rules before execution. Human scoring records scorer identity,
disagreements and adjudication; advisory model scoring cannot be the sole judge.

## Run records and report

Each selected cell records manifest/case/prompt/tool/scoring hashes, runtime and
source commits, repo/generation, actual model identity, responses, every decision
and tool outcome, evidence ledger, assessment, completion, termination, validity,
resource reservations and usage. Include available database work (queries, scan
bytes, service counters), using null for unexposed metrics. Correlate request IDs;
do not invent SQL-work estimates from response size. Keep bulky captures in
[the raw artifact area](/DOCS/test_results/raw-index.json) with index hashes per
repository guidance; concise reports link the index.

Report every attempted cell, including incomplete, budget-limited, timed-out,
tool-unavailable, cancelled and invalid-setup runs. Give per-family/profile/arm
quality and coverage distributions, completion confusion counts, routing errors,
escalation, latency, model spend, tokens, tool/model calls and available database
work. Show all-attempt denominators and separately labeled completed-run summaries;
never hide failures in success-only averages. Separate routing, tooling, retrieval,
reasoning and execution constraints with evidence; allow multiple causes and
unknown attribution. Compare the relevant simpler baseline for each claimed gain.

## Freeze and promotion gates

Before any model call, all manifest fields marked required must be concrete,
artifact hashes verified, scope/leakage/capability preflight passed, model/provider
and spend explicitly approved, and protocol/scoring/cases/prompts/settings frozen
at a named commit. Approval records identify approver, timestamp and exact manifest
hash. Hash approval via a separate receipt to avoid a self-referential manifest
hash. Any change creates a new version and renewed approval; preserve failed runs.

No generalization claim follows these development cases. Product work requires a
fresh independently sealed evaluation under ADR-054, demonstrated benefit over
the relevant simpler baseline, explicitly reviewed quality/cost/latency/resource
tradeoffs and a separately approved product implementation issue defining rollout.
Positive results do not authorize production work.
