# Proposed experiment interfaces

Tracking: [#382](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/382),
[specification](../spec.md). These are prospective records, not implemented APIs.

## Request and actions

`RequestContract`: request_id, family (`exact_source`, `python_inventory`,
`overview`, `execution_trace`), question, repo_id, source_commit, generation_id,
declared_scope, obligations, maximum_strategy, provider/model/revision,
budget_profile, concrete_caps, deadline, cancellation handle, frozen_manifest_hash.
Maximum strategy is a permission ceiling, not an instruction to use that strategy.

`ActionProposal`: action_id, tool, arguments, obligation_ids, evidence_gap,
expected_repair. Scope is injected by the controller. Reject conflicting scope,
unknown fields/tools and invalid arguments before dispatch. Normalize defaults,
path syntax and argument order for an action key of tool + scope + normalized
arguments. Do not collapse materially different line ranges or queries. Record
rejections, consume model budgets and enforce deadline/model-call caps even if
the model repeats only rejected proposals.

| Tool | Arguments beyond injected scope | Result / candidate adapter seam |
| --- | --- | --- |
| `orient` | declared facets | Existing ORIENT structural evidence, gaps and provenance through evidence_service's HTTP adapter. |
| `find_source` | pattern, limit, cursor | #379 file identities, availability and continuation; exhaust pagination when claiming inventory of matching stored files. |
| `read_source` | exact path, optional start/end lines | #379 exact stored text, returned-text hash, full-file flag, next line and source provenance; preserve null full-file hash. |
| `search_evidence` | question-derived query/anchors, bounded result count | Retrieval-only evidence from a future adapter around existing retrieval seams; no generation, hidden source hints or implied grep capability. |

Respect actual [source API bounds](/DOCS/architecture/source-navigation-api.md);
the controller cannot raise service caps. Retrieval results are discovery
material; only inspected supporting content supports a final claim. ORIENT
records can support inventory facts, not inferred runtime behavior. Any graph
navigation adapter requires its own separately frozen arm and tool schema.

`ToolOutcome`: action_id, repo_id, generation_id, status, evidence[],
continuation, limitations[], stable_error_code, elapsed_ms, available_work_metrics.
Statuses distinguish ok, ambiguous, unavailable capability, source unavailable,
source limit, service failure, stale generation, cancellation and timeout. Preserve
the service's original error code, including scan/range/deadline failures.

`EvidenceReference`: evidence_id, repo_id, generation_id, source_commit (nullable
if service cannot supply it, verified separately in corpus pin), canonical_id,
document_id, path, inclusive line bounds, representation, returned_text_sha256,
full_text_sha256 (nullable), complete_file, supporting_claim_ids, action_id.
Never relabel normalized stored text as original Git bytes. Full-file assembly
needs contiguous nonoverlapping coverage through EOF, coherent identity and
generation, retained per-interval hashes and a computed assembled-text hash.

## Controller and model transport

Conceptual interfaces: `ModelTransport.propose(context, schema, remaining)` and
`synthesize(evidence, remaining)` return content plus actual model identity,
usage, timing, request ID and error. `ToolAdapter.execute(validated_action,
scope, remaining_deadline)` returns ToolOutcome. Both support cancellation and
bounded timeouts. Controller state is injected explicitly, never global mutable
session state. Final synthesis cannot add evidence or discharge obligations by
assertion. Unavailable provenance invalidates matched-model scoring.

Before each operation, validate scope/generation/permission, duplicate key,
capability and remaining resources. Reserve worst-case feasible tokens/cost and
output allowance; release unused reservations using actual usage. Include retries,
assessments and final generation. If reliable hard-cap reservation cannot be made,
block dispatch rather than treat unknown usage as free. Record any unavoidable
late usage/overshoot. No silent provider/model fallback in experiments; this does
not change existing product fallback behavior.

## State, events and final result

`InvestigationState`: request contract, objective, obligations with evidence
assessment, visited paths/intervals/actions, evidence ledger, uncertainties,
contradictions, decision events, stagnation counter, reserved/incurred resources.
Persistence is evaluation capture only; no resume, learned memory or delegation.

`DecisionEvent`: sequence, timestamp, strategy_before/after, evidence_ids,
obligation_ids, gap, proposed_repair, selection_reason, capability/permission,
remaining/reserved budget, dispatch/rejection and outcome. Capture what was
available at the decision to permit independent routing adjudication.

`FinalResult`: scope, supported findings and citations, unresolved obligations,
contradictions, evidence_assessment, completion, termination_reason,
validity (`current`, `stale`, `invalid_setup`), model identities, resource totals,
trace artifact references. Termination reasons include completed, no_useful_repair,
clarification, tool_unavailability, source_access_limit, service_failure,
tool_call_exhaustion, model_call_exhaustion, token_exhaustion, cost_exhaustion,
timeout, stagnation, cancellation and stale_generation. Multiple coincident
conditions retain secondary reasons; primary is the first stopping event in
event order. Unknown telemetry is null with a reason.
