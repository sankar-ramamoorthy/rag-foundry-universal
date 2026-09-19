---
title: "Phase 6 Claude handoff: bounded sufficiency, authority, then semantic checks"
date: 2026-09-19
type: implementation-plan
status: proposed
tags: [phase-6, handoff, evidence, sufficiency, provenance]
related:
  - "[Code findings](/DOCS/notes/2026-09-19-phase-6-sufficiency-findings.md)"
  - "[Phase 6 roadmap](/DOCS/audit/07-Roadmap.md)"
  - "[Architecture audit](/DOCS/audit/2026-09-07-repository-intelligence-architecture-audit.md)"
  - "[Evidence delivery ADR](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)"
---

# Start here, Claude

The owner requested a detailed implementation handoff, with findings saved as
work progressed. This session completed planning only. Implement in this order:

1. **#200**: bounded evidence-sufficiency loop using current mechanical signals.
2. **#199**: source authority / subject / provenance, propagated end to end.
3. **#200 follow-up**: authority/provenance-aware sufficiency using #199's contract.

These are the owner's original item **#5, #4, then #5 again**. The roadmap has
already reordered the numbered list; issue IDs are the unambiguous references.
Do not combine all three into one implementation or make #199 a prerequisite for
the first useful #200 release. Do not implement the deferred general investigator
(#207), a new retrieval framework, or an LLM judge under this plan.

Baseline inspected: `65ccd096e3ea525c351ae32d7f60e44c0e701bb2`.
See the [findings](/DOCS/notes/2026-09-19-phase-6-sufficiency-findings.md) for
verified entry points and limitations. All new names, fields, defaults and PR
boundaries below are **proposals**, not claims about existing APIs or approved ADRs.

## First actions in the next session

- Read [CLAUDE.md](/CLAUDE.md), [constitution](/.specify/memory/constitution.md),
  [status](/DOCS/status.md), the findings, and this plan. Check HEAD and dirty
  files before editing. Preserve this planning work and unrelated user changes.
- Read current issue #200 and #199 bodies and associated discussion; reconcile
  scope differences explicitly. They were not fetched in the planning session.
- Confirm available spec numbering before creating specs; do not overwrite 006.
  Keep #200 and #199 separately traceable. A later #200 follow-up needs an issue
  reference; if #200 is already closed, prepare a linked follow-up issue draft.
- Establish the current baseline tests and freeze evaluation cases before
  changing retrieval behavior. Save results and blockers as they occur.
- Reference applicable ADRs rather than copying their rules into a new spec:
  [030](/DOCS/adr/ADR-030-unified-artifact-graph.md),
  [031](/DOCS/adr/ADR-031-canonical-identity-model.md),
  [038](/DOCS/adr/ADR-038-pipeline-construction-ownership.md),
  [045](/DOCS/adr/ADR-045-hybrid-vector-graph-rag.md),
  [050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md),
  [051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md), and
  [052](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md).
  Read each fully before changing its governed behavior. Record genuinely new
  decisions in a new ADR using the next available number.

# Stage A: #200, mechanical sufficiency

## Deliverable and API boundary

A deterministic workflow executes an initial retrieval, checks explicit evidence
obligations, performs at most **one targeted follow-up**, then returns evidence
with a satisfied/partial/needs-clarification result and reasons. A later increase
in retry count requires evaluation; initial pass + one follow-up = two passes.
It can report an honest gap even when no additional retrieval can repair it.

Recommended public surface: an additive orchestrator
`POST /v1/repos/{repo_id}/evidence` workflow endpoint with explicit mode
`orient | trace | impact`. Keep existing structural GET endpoints available as
single-pass primitives. Use service functions directly rather than HTTP calls
from the orchestrator back to itself. The POST performs read-only queries.

Proposed request: mode, optional start canonical ID/symbol (required for TRACE
and IMPACT), relation types/direction where supported, explicit scope/depth,
optional required facets or target canonical IDs, and optional explanation query.
Server owns all work ceilings. Validate mode-specific inputs and supported
obligations; reject contradictory/unsupported combinations. Never guess a symbol
from arbitrary prose or equate an unrestricted question with a provable obligation.

First implement structured evidence responses without generation. Then add an
optional explanation adapter through the existing generation path, with one
generation phase after checking the final selected context. This remains within
Stage A so evidence-to-prompt survival is actually covered. Do not call `run_rag`
repeatedly: that would repeat embedding, retrieval and generation and discard
the controller's state. Preserve provider/fallback observability.

Generic `/v1/rag` and `/v1/rag/simple` keep existing behavior unless explicit
workflow integration is separately evaluated. Do not add a natural-language
mode router as a hidden part of #200. Confirm the endpoint choice in the spec
against the actual issue before coding; it is a recommended implementation choice.

## Proposed internal contracts

Use small typed records and a pure assessor, with I/O isolated in adapters.

| Record | Minimum information |
|---|---|
| EvidenceRequest | mode, repo, explicit scope, resolved start or ambiguity, obligations |
| EvidenceItem | stable identity, generation, artifact/chunk or structural fact, supporting edge/path, content hash when available |
| EvidenceState | retained items, observed gaps, retrieval limits, selected payload/manifest, satisfied obligation IDs |
| EvidenceAssessment | policy version, status, per-obligation satisfied/missing/unknown, reason codes, optional next action |
| WorkBudget | remaining passes, tool calls, visited work, fetched documents/chunks/bytes, deadline, context allowance |
| StepRecord | action, reason, counts before/after, new identities, budget spent, generation, outcome |

Use the existing retrieval/manifest representations internally where practical;
do not create a second authoritative chunk identity system. Normalize evidence
once at adapter boundaries. Return an additive assessment envelope with
`policy_version`, `status`, `stop_reason`, `scope`, `generation_id`, `steps`,
`missing_obligations`, and `limitations`. Keep time-varying telemetry separate
from deterministic assessments. Stable ordering is mandatory for repeatability.

For final-context checks, distinguish artifact presence from relevant passage
presence: retain chunk IDs and hashes. A different chunk from the same document
must not satisfy an obligation targeting a specific passage. Structural facts
need stable fact identities and citations in the exact serialized output/context.

## Mode-specific obligations and honest limits

| Mode/signal | Mechanical check | Allowed response/action |
|---|---|---|
| ORIENT | requested facet has supported records or an explicit inventory gap | return known facets; missing unsupported extraction stays a gap |
| TRACE | unique start, requested target/path if supplied, per-hop basis, external gaps, bounded scope | extend one incomplete frontier within caps; unresolved external stays unknown |
| IMPACT | unique start, each candidate has basis, declared relation/depth scope and truncation | bounded extension if budget permits; always describe candidate effects |
| Duplicate evidence | identity/content-aware distinct support | duplicates cannot increase obligation coverage |
| Context delivery | required exact items occur in selected payload/manifest | one bounded selection repair using already-fetched or targeted evidence |
| Mechanical conflict | incompatible structured values for the same explicitly identified fact/scope | report conflict with both supports; never silently choose |
| General prose contradiction | no reliable existing detector | report assessment unsupported/unknown, not contradiction-free |

No universal minimum chunk count: a uniquely supported fact may need one item;
many unrelated chunks may satisfy none. “Sufficient” means **satisfies declared
obligations within this indexed scope**, never “proves the answer is true.”
Unspecified completeness obligations must not be invented from a low chunk count.
An empty candidate set can be valid within the indexed graph; it cannot prove
there are no runtime callers, external users, or unindexed dependencies.

TRACE currently does not flag depth exhaustion as truncation. Add explicit
coverage-limit metadata for workflow use, distinguishing depth limit, node limit,
unresolved external and exhausted indexed frontier. Inspect only bounded frontier
work; do not enumerate the omitted graph to report its size. IMPACT's current
per-relation traversal is its scope; cross-relation paths are a separate change.

## Control loop and bounded actions

```text
validate request and server ceilings
resolve ready generation and establish request-wide generation fence
execute initial mode plan under shared budget
deduplicate evidence; select response/context evidence
assess declared obligations
if satisfied: finish
if ambiguous: return needs_clarification without choosing a start
if one permitted, useful, untried repair fits remaining budget:
    execute repair; merge/deduplicate; reselect; reassess once
verify generation consistency before final delivery
return evidence + assessment + gaps; optionally explain supported subset once
```

Allowed repairs are selected by a fixed priority table, not an LLM:

1. Fetch an explicitly missing, already-resolved artifact/passage using the
   existing canonical lookup and generation-scoped query-relevant passage fetch.
2. Extend a TRACE/IMPACT frontier to the next permitted depth where initial
   execution deliberately used a smaller scope than the server ceiling.
3. Reassemble context to retain required already-fetched items, displacing only
   optional material and keeping the same context allowance.

If ORIENT exposes no suitable targeted fact-fetch capability, report its gap;
do not manufacture a new extractor or semantic fallback to make every mode loop.
Do not silently change requested direction, relation scope, subject or target.
Do not retry an ambiguous symbol, an unindexed external, or the same action with
the same inputs. Stop on satisfied, no useful action, no progress, exhausted
budget/deadline, conflict, or unavailable/changed generation. Record distinct
reason codes, rather than hiding all failures under “insufficient.”

Define progress as new obligation-relevant identities, a newly covered obligation,
or repair of required context survival; raw item-count growth is insufficient.
Charge repeated traversal/fetch work even if the results deduplicate. If traversal
is rerun rather than resumed, its full work counts against the same request budget.

Proposed defaults: `MAX_PASSES=2`, `MAX_REPAIR_ACTIONS=1`; existing TRACE/IMPACT
depth/node ceilings remain upper bounds. Initial depth 1 is a candidate only for
requests allowing extension; an explicitly depth-1 request stays depth-1 scoped.
Define finite call, fetched-byte, edge-visit and total elapsed ceilings in config
before implementation. Calibrate their values with frozen workloads; request
parameters may lower limits but never raise the server maxima. Count generation
checks and passage-fetch fan-out, not just the high-level repair command.

Existing graph loading materializes a whole repository. This plan bounds added
workflow work, not total cold-cache graph memory. Report graph-load cost separately;
do not claim #206's bounded graph-service scaling is solved. Synchronous graph
work must not block the async event loop; timeouts must prevent further scheduled
work and handle in-flight I/O. Thread cancellation alone is not a CPU-work bound.

## Generation fence: required in Stage A

Reuse the ready-generation behavior in `service.py` and ADR-052. All passes,
canonical mappings, graph evidence, passage fetches and returned manifests must
agree on one ingestion ID. A change/build during execution yields the existing
appropriate conflict/unavailable behavior, rather than merging generations.

Audit `get_cached_graph` and graph HTTP loading specifically: checking current
generation before a repo-only fetch is not itself atomic pinning. Add verified
generation identity to the graph load/envelope or perform before/after fencing
that rejects changes. Make the same check for ORIENT's returned ingestion ID.
Do not promise querying an old generation after rebuild: historical materialized
graph snapshots are not supplied by the current schema. No silent restart into
a newer generation outside the hard pass budget.

## Implementation slices and files

| Slice | Work and likely entry points | Completion evidence |
|---|---|---|
| A0 | spec, fixtures, frozen questions, new ADR if needed | explicit obligations and failure baseline |
| A1 | proposed `retrieval/evidence_sufficiency.py` with contracts/assessor; `trace_impact.py` limit semantics | pure tests: sufficient, missing, unknown, ambiguity, truncation |
| A2 | proposed workflow controller/adapters; `core/config.py`; `codebase_utils.py`/`codebase_queries.py` generation fence | one useful repair, strict aggregate caps, race/error tests |
| A3 | `api/v1/models.py`, `routes.py`; structural result serialization | endpoint tests, unchanged legacy endpoints |
| A4 | extract reusable retrieval/selection/generation seams from `core/service.py`; `agent_adapter.py`, `evidence_trace.py` | exact selected payload and manifest match, one generation phase |
| A5 | live paired evaluation and documentation | quality gate below; default remains opt-in until passed |

Write acceptance tests before or alongside each first implementation spike.
Refactor only the seams needed by the controller; avoid rewriting the large
service module while introducing behavior. Do not change embedding/reranker
defaults or grow context to conceal failed sufficiency.

## Stage A acceptance matrix

- A resolved supported request terminates after its initial pass with no repair.
- A named recoverable missing target is fetched once and satisfies its obligation;
  selected evidence and explanation cite the retrieved source, not guessed text.
- Missing/ambiguous starts remain explicit; no arbitrary candidate wins.
- External gaps, depth exhaustion, node truncation and missing ORIENT inventory
  remain distinguishable and never yield a global-completeness claim.
- Repeated/irrelevant chunks do not cause sufficiency; no-progress stops.
- Oversized required passages that cannot fit cause an explicit context gap;
  another passage in the same document cannot counterfeit survival.
- Generation changes during initial load, follow-up, or final assembly never
  produce a mixed-generation success. Missing generation and upstream timeout
  are distinguishable from insufficient evidence.
- Exhausted pass/call/byte/work/deadline budgets schedule no additional work.
  Tests count actual lower-level calls, including fan-out and generation checks.
- Same input/evidence/config gives the same decision and selected identities.
- Explanation generation sees only the finalized supported context and gaps;
  absent evidence returns an explicit gap response. Partial answers clearly
  expose limitations. Existing model/fallback response metadata survives.

# Stage B: #199, source authority / subject / provenance

## Deliverable and semantic distinctions

Introduce a versioned evidence provenance contract, persist it through existing
artifact infrastructure, and expose it through retrieval/context. Implement
deterministic classifications with explicit unknown/mixed states; do not invoke
an LLM during ingestion. Authority is relative to the requested claim, not a
global numeric score and not simply vector similarity or `doc_type`.

| Dimension | Proposed fields / interpretation |
|---|---|
| Origin | repo_id, canonical_id, relative path, available source span, serving ingestion_id, available commit/file hash |
| Role | implementation, configuration, test, design, documentation, example/fixture, evaluation, historical, unknown/mixed |
| Subject | selected repository, explicitly identified embedded subject, external subject, unknown/mixed; classification basis |
| Derivation | source, deterministic projection, generated summary; input artifact/fact IDs and transform version where known |
| Validity | declared document status/supersession if available; distinguish declared status from verified implementation truth |
| Classification | schema version, classifier version, rule/basis and scope (artifact/section/span); uncertainty |

Separate the serving generation from original production/derivation inputs.
Reused vectors can belong to the current generation while containing unchanged
text originally embedded earlier. A Git HEAD SHA for a dirty local tree is not
proof of exact content: retain file hash and unknown/dirty information when
available. Missing SHA stays unknown, never filled using the evaluator's checkout.

Selected `repo_id` binds the default subject. Text inside a fixture that describes
another application cannot redefine that subject. Explicit fixture/example
questions can select that embedded subject and should still work.

## Persist and transport the contract

Recommended schema direction: a versioned nullable JSON metadata/provenance field
on existing DocumentNode plus narrowly typed fields only where validated query
needs justify indexing. Decide the final shape in an ADR after examining current
models and migration conventions. Do not create per-role artifact tables or
change canonical IDs. Preserve relationship evidence independently.

Trace one real record through every step before broad rollout:

```text
extractor / structural inventory / document parser
 -> IR node or fact metadata
 -> graph persistence field mapping and incremental update/reuse
 -> stored node + relevant edge metadata
 -> embedding/chunk metadata -> vector write and read API
 -> graph/document API -> retrieval types -> agent adapter
 -> selected manifest + source labels -> actual LLM payload -> response
```

Likely files: `shared/models/document_node.py`, Alembic migration,
`ingestion_service/src/core/codebase/codebase_persistence.py`,
`ingestion_service/src/api/v1/codebase_ingest.py`, extractor/IR and structural
inventory producers, ingestion graph/chunk serializers, vector request/response
models and store metadata handling, `rag_orchestrator/src/retrieval/types.py`,
`codebase_queries.py`, `agent_adapter.py`, `core/service.py`, and the LLM request
model/prompt builder. Locate actual owners rather than assuming the shared
VectorChunk ORM represents every vector-store path. Orchestrator stays DB-free.

Source spans are optional and must be true to what the parser knows. A mixed
Markdown section must remain mixed/unknown unless a real subsection/span boundary
is available; do not classify all content solely from its parent directory.
Start with artifact/section metadata and existing chunk boundaries. New semantic
chunk splitting is separately evaluated, not an implicit dependency.

Deterministic path/frontmatter hints require an auditable versioned rule set.
Tests describe asserted behavior; accepted ADRs describe decisions; implementation
and configuration describe implemented structure within the indexed snapshot.
Do not label indexed code as a verified production runtime state. Explicit
overrides, if introduced, need trusted configuration and recorded provenance;
untrusted source prose cannot grant itself authority.

## Incremental ingestion and migration rollout

1. Add compatible nullable storage/read fields; old rows decode as unknown.
2. Add producers and preserve metadata through full ingestion and retrieval.
3. Handle incremental reuse: unchanged bytes do not imply unchanged classification
   when policy version, path context or declared status changes. Recompute/update
   metadata without unnecessary embedding where safe; version/invalidate reuse
   when a representation change actually requires reprocessing.
4. Test forced-full versus incremental equivalence including provenance, unchanged
   document reuse, deleted artifacts and current generation tags.
5. Backfill only derivable fields or re-ingest; never invent historical subject,
   derivation or snapshot facts. Document migration and re-ingestion requirements.
6. Expose metadata before turning on authority-sensitive selection. Legacy clients
   ignore additive fields; older corpora remain queryable with explicit unknowns.
7. Roll back policy use via feature flag without destructive schema downgrade.
   Exercise migration upgrade and compatibility in the isolated test database.

## Acceptance and PR slices

- B0: contract + ADR + fixture classifications and API compatibility expectations.
- B1: migration, deterministic producers, persistence, reuse/version handling.
- B2: complete transport to actual context and manifest, with integration tests.
- B3: measured subject/role evaluation and evidence-backed rollout.

Required cases: actual implementation, accepted/superseded ADR, test assertion,
embedded example, evaluation question text, archived material, mixed-subject
section, generated summary with known/unknown inputs, absent metadata, and
unchanged-file reuse after a classifier-version change. Verify metadata through
both vector and graph paths and both seed and expanded passage fetching. Test
valid design/test/fixture questions so the model does not become a blanket filter.

Stage B is complete only when provenance reaches the exact selected context,
not merely the database or vector metadata. Do not claim all semantic
contradictions are detectable because roles and subjects are present.

# Stage C: revisit #200 with authority-aware sufficiency

Keep the controller, action ceiling and mechanical checks from Stage A. Add a
versioned policy implementation consuming Stage B metadata. Suggested additional
obligations/reasons:

| Check | Failure or unknown state | Bounded response |
|---|---|---|
| Subject fit | embedded example substituted for selected repo | targeted same-subject lookup or explicit gap |
| Claim-relative role fit | design/eval/summary offered as current implementation | fetch permitted source support, not a larger generic top-k |
| Snapshot consistency | incompatible generation/input lineage | reject mixed support; never average versions |
| Derivation support | generated claim has no resolvable inputs | mark unsupported derivation; fetch known inputs if available |
| Declared validity | superseded/history used for current claim | expose status; seek current support within existing budget |
| Required context | correct authority found but dropped before generation | bounded selection repair, then recheck exact manifest |
| Unknown classification | metadata absent or mixed | retain useful evidence but do not assert authority-qualified sufficiency |

Historical/comparison and explicitly embedded-subject requests need an explicit
scope; do not categorically reject all different-time evidence. If the storage
cannot supply requested historical snapshots, return unsupported capability.
Authority checks do not remove the Stage A generation fence; they strengthen
subject/role/derivation meaning, not basic race handling.

Use explicit request claim types such as implemented behavior, design rationale,
test contract, or repository overview where the user/workflow supplies them.
For unconstrained natural-language intent use a conservative unknown classification
rather than introducing an LLM router. Mechanical success and authority-qualified
success must be separately visible in diagnostics.

Conflict detection remains limited to normalized comparable facts. A supported
design/runtime disagreement may be informative, not an error requiring one source
to be deleted. Retain both sources and explain their roles when the question
asks for comparison. Unknown metadata must not silently count as high authority.

Acceptance: the same fixture must pass Stage A mechanical coverage but fail
Stage C authority-qualified sufficiency when all support concerns an embedded
example; a valid explicitly requested example must still pass. Also test a
superseded ADR, unsupported generated summary, implementation/design conflict,
mixed snapshot, and correct source dropped by the context budget. Reuse all
Stage A work-budget/error tests unchanged. Disable semantic policy independently
to roll back to measured Stage A behavior.

# Evaluation, release gates and handoff discipline

## Frozen paired evaluation

Follow the [quality methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)
and [decision gates](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md).
Before tuning, freeze roughly 12-16 cases spanning:

- sufficient first pass; named recoverable missing evidence; duplicate-only/no
  progress; ambiguity; external boundary; node/depth truncation;
- ORIENT missing facet; IMPACT bounded negative result; context-dropped passage;
- selected repo versus fixture; implementation versus historical/design text;
  a valid design question; a valid fixture/test question; unknown provenance.

Use this repository and a differently organized repository. Keep ground-truth
obligations/answers outside the ingested evaluation corpus so planning and eval
notes cannot become answer evidence. Label structural ground truth by reading
source/config directly; do not use the system's own output as the oracle.

Compare A with the single-pass baseline, then C with A on identical pinned corpus
snapshots. Evaluate B's transport separately from policy changes. Pin runtime
revision, ingested source revision/generation and evaluation revision independently;
record model/provider/fallback, configuration and context budget. Keep total
retrieval-work ceilings matched where feasible and separately report the added
follow-up cost; do not call unequal-work gains an algorithm-only improvement.

Record per case: correct sufficiency/partial decision, false-sufficient outcome,
obligation coverage, useful versus unnecessary repair, exact evidence survival,
subject/authority correctness, answer support, calls/work/bytes, latency, and
stop reason. For small samples show per-case results; do not overstate p95 or
statistical significance. Separate structural evidence mechanics from stochastic
answer generation, and repeat generation controls as the methodology requires.

Proposed release gate: zero observed false-sufficient or budget/generation
violations on the frozen required cases; reproducible useful recovery on at least
two independent recoverable-gap cases; no regression on already-sufficient,
design, fixture and test controls. Stage C must additionally reduce the specified
authority/subject failures relative to A. If cases do not reproduce or sample
size is inadequate, record inconclusive and keep the new behavior opt-in.

## Verification commands and existing tests

Run from each service directory as required by its pytest configuration. Do not
assume every existing file has a `unit` marker; name focused regression files:

```powershell
# Working directory: rag_orchestrator
uv run pytest tests/test_trace_impact.py tests/test_trace_impact_routes.py tests/test_orient_passthrough.py
uv run pytest tests/test_graph_cache_generation.py tests/test_repo_generation_lookup.py
uv run pytest tests/test_wp_r4_context.py tests/test_wp_r4_payload.py tests/test_wp_t1d_final_context_manifest.py tests/test_wp_t1c_chunk_token_survival.py
# Add new assessor/controller/API tests, then the affected service suite.

# Working directory: ingestion_service (Stage B)
uv run pytest tests/codebase/test_structural_inventory.py tests/api/test_repo_generation_lineage.py
# Add provenance round-trip/reuse tests and actual DB tests after migrations.

# Working directory: repository root, as repository guidance specifies
uv run ruff check .
uv run pyright .
uv run pre-commit run --all-files
```

Check CI/service configs for the exact integration setup. Use
`docker-compose.test.yml` and the isolated test database for migrations, not the
production database. Run vector-store and LLM payload tests when their contracts
change. Record pre-existing failures separately from regressions. Unit success
does not replace live HTTP verification or the measured quality gate.

## Completion checklist for each stage

- Issue-linked spec/ADR decisions; observable acceptance tests; focused mechanics
  tests and impacted service integration checks pass, or exact blockers recorded.
- Live read-only verification against the frozen corpus, with saved requests,
  responses, actual selected manifests and provenance/configuration fingerprints.
- Independent mechanics review using available review workflow; evaluation report
  states pass/fail/inconclusive without conflating local tests and production.
- Save evidence under `DOCS/test_results/`, questions under `DOCS/evaluations/`,
  and update `DOCS/status.md` in place plus roadmap checkboxes only when warranted.
- Default-on behavior waits for its quality gate. Deployment is a separate action
  under the repository's release process; a merged PR is not proof of deployment.

## Save-as-you-go continuation record

At every completed slice, append to the implementation handoff/spec task log:
current HEAD/branch, edited files, decisions, commands and results, evaluation
artifact paths, remaining blockers, and the exact next step. Keep the findings
note factual; update proposed decisions here or in the eventual accepted spec.

Current checkpoint: planning and local code inspection complete; no implementation
or tests run. Next executable step is A0: reconcile #200's issue contract, establish
baseline/frozen cases, and create its spec and acceptance skeleton. Stage B and C
remain sequenced work after A's measured release gate.
