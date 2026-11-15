---
title: "#359 final report: three perspectives, the smallest defensible query-time change, and the remaining architectural limitations"
date: 2026-11-14
type: test-results
status: current
summary: "#359 closes out across three separately labelled perspectives: the primary development case (POST /v1/rag), C7 (development routes, independent author) and mealie (held-out). No question passes end to end in any arm, unit or budget, and no traversal strategy or budget increase has demonstrated generalization. The recommended smallest query-time change is transparency, a PROPOSAL that is not implemented or authorized: report route-identification status and execution-chain completeness explicitly, rather than presenting partial paths as complete. It is kept separate from the architectural work on route composition and call-target resolution that would recover the missing evidence."
tags: [evaluation, results, recommendation, code-intelligence, evidence-selection, overfitting, issue-359, issue-342, issue-194]
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[#359 protocol (frozen at 45f34e1)](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)"
  - "[Primary development case results](/DOCS/test_results/2026-11-14-359-primary-development-case-results.md)"
  - "[C7 results](/DOCS/test_results/2026-11-14-359-C7-evidence-selection-results.md)"
  - "[Held-out mealie results](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[#359 engineering retrospective (historical note)](/DOCS/notes/2026-11-14-359-engineering-retrospective.md)"
---

# #359 final report and recommendation

This report completes #359's last deliverable: "a report naming the smallest
defensible query-time change, plus the unresolved architectural limitations,
before any implementation". It draws on the three frozen result sets, each
with its own evidence class. **Nothing here is implemented or authorized.**
The recommendation is a proposal for the owner.

**How to read this report.** Four kinds of statement are kept apart:

| Kind | Where | Status |
|---|---|---|
| Observed failures | §1–§3, and the "Measured effect" column of §5 | Measured in the frozen records |
| Hypothesized architectural causes | §5, "Status of the cause" column | Hypotheses unless marked measured |
| Proposed query-time transparency change | §4 | **Proposal; not implemented, not authorized, not evaluated** |
| Untested dimensions | §6 | Not measured by #359; no conclusion drawn |

## 1. Three perspectives, reported separately

| | Primary development case | C7 | `mealie` |
|---|---|---|---|
| Evidence class (ADR-054) | Development; previously studied; corpus names the chain | Development; unstudied routes; independent author | **Held-out** (§5) |
| Repository / generation | self / `8cbedbb9` | self / `8cbedbb9` | `mealie` @ `1624c22` / `611fce96` |
| Questions attempted / evaluable | 1 / 1 | 3 / 2 | 3 / 3 |
| Stage RI resolved | 1/1 | 2/3 (one `ambiguous_route`) | **0/3** (2 `unresolved_route`, 1 `no_route_node`) |
| **End to end (official)** | **0/1** | **0/2** | **0/3** |
| Functions discovered from the correct handler (G2) | 94 | 12–28 | **1–2** |
| Best G2 core support, 16 KB | 4/12 | 12/19 (C7-3), 10/13 (C7-2, ORACLE-ENTRY) | 2/16, 2/17, 5/14 (ORACLE-ENTRY) |
| Dominant loss at 16 KB | not discovered (7 core), plus budget consumed by one large function | not discovered (service hops, unreached fetchers) | **not discovered (all losses); no budget cut** |
| Minimum-evidence bound | 6,452 B | 5,591 B; 8,741–9,544 B | 5,691 B; 4,034 B; 4,218 B |
| C3 scanner | clean (exit 0) | exit 4; 4 terms owner-adjudicated false positives | exit 4; 4 terms owner-adjudicated false positives |
| Report | [primary](/DOCS/test_results/2026-11-14-359-primary-development-case-results.md) | [C7](/DOCS/test_results/2026-11-14-359-C7-evidence-selection-results.md) | [held-out](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md) |

**Familiar repository vs new repository.** In the self-repository, the graph
has had the benefit of repeated development work (#342, #354). There, route
identification works on the studied route, and discovery reaches dozens of
functions. In `mealie` it reaches only the handler. That is not a
contradiction. It is the gap between performance on a familiar repository and
generalization to a new one, and that gap is what the held-out gate exists to
expose. Even on the familiar repository, no cell reaches sufficiency.

## 2. What has not been demonstrated

- **No traversal strategy has demonstrated generalization.**
  - G0, G1 and G2 score almost identically on the development cases.
  - G3 (C5-disclosed, designed knowing the primary case's gap) gains one
    relationship on the primary case and none on an evaluable C7 question.
  - On `mealie`, all four arms are identical.
- **No evidence-budget increase has demonstrated generalization.**
  - 4 KB cannot hold the trace on 5 of the 6 evaluable questions: every
    bound except H-2's 4,034 B exceeds 4,096.
  - 16 KB never produces a pass. On `mealie` the budget is irrelevant,
    because no loss is a budget cut.
- **Today's `/v1/rag` path (A0)**, measured on the primary case only, delivers
  documentation rather than code: 0/12.

## 3. A measured gap in today's completeness signals

The deployed `/trace` (arm G0) returned `truncated: false` and
`depth_limited: false` for **every one of the seven distinct traces** run in
#359: P0, C7-1, C7-2 (from the oracle entry), C7-3, H-1, H-2 and H-3. Yet
**not one of the six evaluable questions reached sufficiency**, and H-1 and
H-3 stopped at the handler itself.

The current scope flags report only cap-based incompleteness (node cap,
depth cap). In code, the existing TRACE assessment (`assess_trace`,
`rag_orchestrator/src/retrieval/evidence_sufficiency.py`) treats a resolved
start without a required target as `satisfied`. It lists `external_gap:` codes
but does not change the status on them.

So an execution path that ends because the graph has no further resolved
edges looks the same as a complete one. This is a verified observation about
the flags. Whether users read such results as complete was not measured.

## 4. Recommendation: the smallest defensible query-time change (PROPOSAL)

**Make unresolved route identity and incomplete execution-chain evidence
explicit in the retrieval result and the sufficiency assessment, rather than
presenting a partial path as complete.**

It is "smallest" because it changes what is reported, not what is retrieved.
No traversal, ranking, budget or generation behaviour changes. It is
"defensible" because every signal below is computable at query time, without
ground truth, from information the #359 harness already observed.

| Signal | Evidence that it would have fired | Generic basis |
|---|---|---|
| **Route status**: `resolved` / `unresolved_route` (with suffix candidates, never silently substituted) / `no_route_node` / `ambiguous_route` | All 3 `mealie` routes; C7-2 | Stage RI codes (§5a.6) |
| **Chain frontier**: call sites in visited functions that end at unresolved or external targets, and an explicit **"no internal callee reached from the entry"** state | H-1, H-3 (entry only); H-2 (one class node) | Edge targets in the graph |
| **Unfollowed service hops**: HTTP calls or URL literals whose handler was not reached | Primary R14–R17; C7-3; C7-1 (diagnostic) | URL literals matched against route nodes (G3's rule, reporting only) |
| **Budget status**: requested vs delivered bytes, and discovered functions with no delivered passage | Primary: 103,788 B requested vs 16,384 delivered; `hybrid_retrieve` never delivered | Assembly bookkeeping |

Under the proposal, any of these signals present would make the assessment
`partial` (or `unknown`) with reason codes, never `satisfied`. Any generated
answer would be required to say that the path is incomplete, and where.

**What this proposal does not do or show:**
- **It recovers no missing relationship.** It improves transparency and
  trustworthiness, not sufficiency.
- **Its discrimination is unmeasured.** All six evaluable questions failed,
  so #359 contains no complete chain against which to measure false alarms.
  Raw counts will not discriminate on their own: the primary case reached 94
  functions and still suppressed 448 calls (G2).
- **Whether a generated answer honours the flags is untested.**
- Before any claim, it needs its own pre-registered evaluation, including
  questions whose chains are complete.

## 5. Remaining architectural limitations (separate work; not query-time)

These are the causes behind the measured not-discovered losses. Where the
cause is a hypothesis, it is marked as one. Fixing them changes ingestion and
graph construction, which is outside this recommendation.

| Limitation | Measured effect | Status of the cause |
|---|---|---|
| **Route composition**: router prefixes and class-based controllers | `mealie`: 2 `unresolved_route`, 1 `no_route_node`; 30 route nodes in a 1,728-file repository | Hypothesis (H report §7) |
| **Call-target resolution**: dependency-injected parameters, instance attributes (`self.service`), module-qualified imports | `mealie` handlers' onward calls end at `EXTERNAL_SYMBOL` | Measured endpoints; the cause is a hypothesis |
| **Constructor calls** bind to the class, not to `__init__` or a method | H-2's one followed edge stops at a class node | Measured; the cause is a hypothesis |
| **Deferred callbacks / background tasks** | H-1: `bg_tasks.add_task` external | Measured endpoint |
| **Dynamic dispatch** into implementations | Primary R8–R10 not discovered | Measured |
| **Cross-service HTTP hops** are not graph edges for G0–G2 | Primary R15–R17; C7-3 R13–R19 | Measured. G3's literal hop crosses some, without generalizing |
| **Ambiguous routes across services** need service context | C7-2 | Measured (RI refused, correctly) |
| **Nested-function indexing** | C7-1 R14, R15 index-missing | Measured; investigation pending |
| **Passage granularity for large functions** | Primary: `run_rag` takes 18 of 22 passages at 16 KB | Measured |
| **4 KB vs real traces** | Bounds of 4.0–9.5 KB | Measured (oracle bound) |

## 6. Untested dimensions

#359 measured deterministic discovery, selection and context assembly at two
budgets. It does **not** support conclusions about the following:

- **Larger or different generation models.**
  - No answer was generated: A0 stubbed generation, and the arms produce
    evidence only.
  - #359 says nothing about how any model, larger or smaller, would answer
    from the delivered evidence.
  - A model cannot cite implementation evidence it was never given, but
    whether a stronger model would reason better around the gaps is
    untested.
- **Stronger GPUs or other hardware.**
  - The measured outcomes come from graph traversal and offline assembly,
    so hardware does not enter them.
  - Latency, throughput and cost were not measured.
- **Larger evidence budgets.**
  - Only 4,096 and 16,384 bytes were run.
  - On `mealie` no loss was a budget cut, and the selected evidence never
    exceeded 4,179 bytes. On these frozen records, more budget would add no
    `mealie` evidence. That is an inference from the records, not a
    measurement.
  - On the primary case, discovery requested 103,788 B (P-call) against the
    16 KB cap, so budgets above 16 KB are untested there. Even then, 7 core
    relationships were never discovered and could not be delivered at any
    budget.
- **Scalability.**
  - Two repositories were used, one generation each: self, 13,458 nodes;
    `mealie`, 21,621 nodes.
  - The 300-node cap was never hit.
  - Behaviour on larger repositories, ingestion and query latency, memory,
    and concurrent load were not measured.
- **Other coverage.**
  - Only Python, and FastAPI-style routes, were tested.
  - A0 ran on the primary case only (P4).
  - `mealie`'s deployed embedding configuration is unverified. It does not
    affect graph discovery.
  - The question sets are small: 1 + 3 + 3, with two `mealie` questions
    sharing helpers.

## 7. #359 deliverables

| Deliverable | Status |
|---|---|
| Protocol committed before running | `45f34e1` (#360) |
| Diagnostic script with tests | `c6dd8a0` (#364) |
| Raw records in `raw-index.json` | C7 (#365), held-out (#368), primary (this change) |
| Report naming the smallest defensible query-time change and the unresolved architectural limitations, before any implementation | This report (§4, §5) |
| The original question (primary case at 4 KB / 16 KB) | [Primary development case results](/DOCS/test_results/2026-11-14-359-primary-development-case-results.md) |

All prior frozen results and C3 adjudications are unchanged. C7 and `mealie`
were not re-run.
