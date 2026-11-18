# Experimental Specification: Evidence-aware Execution Router

**Feature Branch**: `docs/evidence-aware-execution-router`
**Created**: 2026-11-17
**Status**: Proposed experimental contract; documentation authorized, execution unfrozen
**Tracking Issue**: [#382](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/382)
**Roadmap Context**: [Phase 6 / R, AG0 and AG3](/DOCS/audit/07-Roadmap.md)
**Input**: Owner-approved architecture/evaluation documentation plan, 2026-11-17.

## Scope

Deliver the [proposal](/DOCS/proposals/2026-11-17-evidence-aware-execution-router.md),
interfaces, protocol, manifests, scoring and fresh-context handoff. These describe
future experiments. No production router, agent, experiment harness, new service,
framework, memory database, deployment or RAG behavior change is authorized.
No model expenditure is authorized by this specification.

## Requirements

- FR-01: Each request declares task family, repository, pinned source commit and
  generation, required obligations, maximum strategy, approved model and budgets.
- FR-02: Select deterministic access, retrieval/synthesis or bounded investigation
  from available evidence. Log every transition's gap, repair and reason. Require
  caller permission, available capability and resources before investigation.
- FR-03: Ambiguity ends in clarification. Generation mismatch invalidates the
  investigation. Failures and source limits remain explicit; no automatic
  escalation, silent model fallback or cross-generation continuation.
- FR-04: Controller validates actions, injects scope and enforces budgets; model
  proposals and retrieved instructions cannot change policy. Use the four tools
  and state boundaries in the [interfaces](contracts/interfaces.md).
- FR-05: Keep evidence assessment, completion classification and termination reason
  separate. Preserve supported partial findings and unresolved obligations.
- FR-06: Evaluate exact-source, Python inventory, overview and execution-trace
  tasks with the four baselines and staged experiments in the protocol.
- FR-07: Freeze inputs, scoring, prompts, model/settings and resources before runs;
  hide witnesses from the system. Apply [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)
  and score routing independently from answers.
- FR-08: Preserve existing architecture per [ADR-045](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md),
  identity per [ADR-031](/DOCS/adr/ADR-031-canonical-identity-model.md), lifecycle per
  [ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md) and source access
  per [ADR-055 supplement](/DOCS/adr/ADR-055-source-navigation-supplement.md).
  This draft selects no product architecture and creates no conflicting ADR.

## Acceptance scenarios for later implementation

These are reproducible fixture definitions, not claims of executed tests. Future
implementation must add skeletal controller/adapter tests before its first spike.

| ID | Given / action | Required observable result |
| --- | --- | --- |
| AC-01 | Two repositories contain the same path; a proposal supplies another repo ID | Reject conflicting scope before dispatch; valid proposals receive controller-injected caller scope, never the other repository; ledger is isolated. |
| AC-02 | Two interleaved sessions use different pinned generations | No shared objective, visited set, budgets or evidence; each trace retains its own scope. |
| AC-03 | Adapter returns a new generation after an initial valid read | Reject new evidence, terminate `stale_generation`, invalidate the investigation; retain old evidence only as stale diagnostic data. |
| AC-04 | Full Python source with nested, async, decorated functions and methods | Deterministic AST inventory matches the declared inclusion rule and names/lines exactly; verified completeness is limited to that file's stored representation. |
| AC-05 | Only the first source interval is available, or later read hits a scan cap | No complete-file inventory claim; preserve intervals and explicit source limit, unresolved enumeration obligation and incomplete result. |
| AC-06 | Two files match an ambiguous basename | `clarification` termination; no guessed file, investigation or implicit scope expansion. |
| AC-07 | Model requests grep, shell or an unknown tool; source service returns 503 | No unsupported dispatch; typed capability/service outcome recorded; no automatic strategy escalation. |
| AC-08 | Cancellation arrives during an adapter/model call | Cancel in-flight work where supported, dispatch nothing further, ignore late results for completion, retain incurred usage and supported findings; `cancellation` reason. |
| AC-09 | Same tool and normalized arguments are proposed twice | Exactly one adapter dispatch; second is a logged duplicate rejection; model usage still charged. |
| AC-10 | Three consecutive executed actions yield irrelevant or repeated material | `stagnation` stop; progress resets the counter; offline scoring records premature stops if repairable witnesses remain. Duplicate rejections do not count as executed actions. |
| AC-11 | Fake clock reaches deadline before dispatch or during a call | No dispatch after deadline; cancel/timeout in-flight call, record actual elapsed time and `timeout`, preserve late cost; completion is budget-limited. |
| AC-12 | Each call, token or cost cap is separately reached, including via retries/final synthesis | Reserve before dispatch, stop without overspending knowingly; distinguish tool-call, model-call, token and cost exhaustion, retain partial findings. |
| AC-13 | Every cited trace fragment is valid but a seeded cross-service relationship is omitted | Online result never claims verified completeness; offline witness coverage exposes omission independently of citation validity. |
| AC-14 | Exact path source fully satisfies request; or a trace has a material repairable gap | First finishes deterministically; second may investigate only under allowed maximum strategy/budget. Logs expose unnecessary invocation and missed permitted repair. |
| AC-15 | Source includes instructions to change model, repo or budget | Controller rejects policy modification; instructions remain data; ledger and scope unchanged. |
| AC-16 | Usage/pricing unavailable, or provider serves a different model | Unknown usage/cost is null with a reason, never zero; hard-cap enforcement uses approved conservative bounds or blocks dispatch; model mismatch invalidates matched comparison. |

## Completion contract

Evidence assessment records satisfied/missing/unknown obligations, support,
contradictions and limitations independently of the reason execution ended.

| Completion | Eligibility |
| --- | --- |
| `verified_complete` | Mechanically checkable declared requirements fully satisfied in the pinned, declared scope. |
| `evidence_supported` | Inspected supporting evidence, with no established global completeness. |
| `incomplete` | Known material obligations remain unresolved. |
| `budget_limited` | A resource cap or deadline prevented completion; expose evidence assessment and remaining obligations. |

Use budget-limited when a resource/deadline stop prevents completion; otherwise
use incomplete for known unresolved obligations. Evidence-supported does not hide
known material gaps. Clarification, unavailability and cancellation retain their
own reason regardless of completion label. Stale investigations are invalid for
current-source answers. Mechanical #200 `satisfied` remains scoped to its checks;
model judgments and valid citations cannot prove broad trace completeness.

## Success criteria and product gate

Documentation passes when every FR and AC has a protocol/interface/scoring path,
all twelve case contracts exist, freeze blockers are explicit and the handoff
requires no conversation history. Experiments need separate implementation
authorization and an approved frozen manifest. Product implementation additionally
requires benefit over the applicable simpler baseline, reviewed quality/cost/
latency/resource tradeoffs, fresh sealed evaluation and a separately approved
product issue defining scope and rollout. No invented weighted score substitutes
for that review.
