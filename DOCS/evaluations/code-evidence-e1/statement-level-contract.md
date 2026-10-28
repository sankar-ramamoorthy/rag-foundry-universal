---
title: "E1 statement-level evidence delivery contract (Option B)"
date: 2026-10-28
type: experiment-contract
status: proposed-not-frozen
tags: [evidence-delivery, statement-level, structural-context, held-out, adr-054]
related:
  - "[Issue #276](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/276)"
  - "[Structural-context feasibility oracle](/DOCS/test_results/2026-10-28-e1-structural-context-feasibility.md)"
  - "[4096-byte feasibility oracle (#264)](/DOCS/test_results/2026-10-21-e1-4096-byte-evidence-feasibility.md)"
  - "[ADR-055: node-text read endpoint (proposed)](/DOCS/adr/ADR-055-node-text-read-endpoint.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[ADR-052: passage selection and provenance](/DOCS/adr/ADR-052-evidence-delivery-context-selection.md)"
  - "[E1 isolated prototype contract](/DOCS/evaluations/code-evidence-e1/prototype-contract.md)"
  - "[E1 frozen cases](/DOCS/evaluations/code-evidence-e1/README.md)"
---

# E1 statement-level evidence delivery contract (Option B)

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)).
Tracked by #276. **This is a specification for a future experiment.** It
authorizes no implementation, no endpoint, no retrieval-policy merge and no
deployment. #275 (target-first selection) is a separate question and is not
addressed here.

## 1. Status and how it becomes frozen

Status is `proposed-not-frozen`. It becomes binding only when the repository owner
accepts it. Freezing means: change `status` to `frozen-before-candidate-results`,
record the SHA-256 of this file in `statement-level-contract.sha256` (the same
convention as `manifest.sha256`), and commit both before any candidate
implementation exists. After that, changes need a new dated contract, not an edit.

Section 11 lists decisions the owner must make before freezing.

## 2. Why this contract exists

The [#264 oracle](/DOCS/test_results/2026-10-21-e1-4096-byte-evidence-feasibility.md)
and the [structural-context oracle](/DOCS/test_results/2026-10-28-e1-structural-context-feasibility.md)
(both oracle-selected, so bounds and not selector results) established, for the six
development cases:

- The 4096-byte cap is not the binding constraint: whole statements plus signature
  and enclosing control-flow headers fit in all six cases, but L1/L2 only marginally
  (3,926 bytes, 170 bytes of slack).
- Adding the local definitions those statements read exceeds the cap in three of
  six cases (L1, L2, F3).
- Stored chunks are not source-faithful (stripped indentation, normalized blank
  lines, arbitrary cuts above 10,000 characters) and the passage-only prototype's
  contiguous windows are infeasible in 4 of 6 cases.

What is unknown, and is the subject of any future experiment under this contract:
whether a selector that does **not** know the witnesses can find and deliver such
evidence, and whether that improves the answers.

## 3. Scope

- **In v1:** Python function and method nodes (the language the oracle's `ast`
  handling covers). Required content is *statements plus enclosing structure*
  (section 5). Data definitions are **out of v1** (section 6).
- **Fixed, unchanged:** the 4096-byte final-context cap and what it counts, the
  models and prompts, top-K and the 20-document cap, discovery and graph expansion,
  reranking off, the answer-review rubric. Only the unit and construction of the
  delivered passages for selected function nodes changes.
- **Not in scope:** target-first selection (#275), changing chunking or embeddings,
  non-Python languages, documents, a multi-step workflow (Option C remains deferred
  and is not an automatic fallback), the endpoint's implementation (ADR-055), and
  anything on the production deployment.

## 4. Delivered block format (normative)

For every function node delivered in statement mode the final context contains one
block, rendered by the existing `[Source: ...]` mechanism and joined with the
existing separator:

1. **Label.** `[Source: <canonical_id> [lines A-B]]`, where A-B are the first and
   last delivered lines, 1-based **within the node body** (the pinned node text;
   file offsets are not recorded for node bodies).
2. **Lines.** Verbatim lines of the pinned node text, in original order, with
   original indentation and no reflow, normalization, truncation or rewriting.
3. **Omission markers.** Wherever non-blank source is omitted between or after
   delivered lines, exactly one line `<indent># ... lines A-B omitted` (or
   `<indent># ... line N omitted`), where `<indent>` is the indentation of the next
   delivered line (of the last delivered line for a trailing marker) and A-B are
   1-based within the node body. Gaps made only of blank lines produce no marker.
4. **No other synthetic text.** Markers are the only text that is not a verbatim
   source line. No summaries, explanations or annotations are added.
5. **Whole statements.** A selected statement is delivered entirely (every physical
   line of the simple statement, or every header line of a compound statement). A
   fragment from the middle of an expression is never delivered.

## 5. Required structure (v1, normative)

Delivering a statement requires delivering what is needed to read it correctly.
For every delivered statement the block must also contain, verbatim:

| Rule | Required lines |
| --- | --- |
| R1 Signature | all decorators and the full `def` header including every parameter and annotation |
| R2 Branches | for a statement in an `if` body: that `if` header. In an `elif`: the `if` header, every earlier `elif` header, and this `elif` header. In an `else`: the `if` header, every `elif` header, and the `else:` line |
| R3 Loops | the `for`/`while` header; for a statement in a loop `else:`, also that `else:` line |
| R4 Context managers | the `with` header |
| R5 Exceptions | the `try:` line and, for a statement in a handler, the `except ...:` header; in `else:`/`finally:`, that keyword line |
| R6 Nested definitions | the header (with decorators) of each enclosing nested `def` or `class` |
| R7 Header witnesses | a statement that is itself a compound-statement header needs only the rules above for its ancestors |

The structural-context oracle (`scripts/code_evidence_structure_oracle.py`) is the
executable reference for R1-R7 on the development functions. It is an **oracle, not
a selector**: it knows the witnesses. Its rule implementation may be reused to build
and to check blocks, but a selector may not use its witness inputs.

`match` statements, walrus assignments and comprehension scoping are approximated by
the reference and must be reported as unsupported if a held-out function uses them
in a witness position (section 9).

## 6. Data dependencies (separate experimental variable)

Names read by delivered statements may be defined elsewhere in the function. In the
development cases, including them overflowed the cap in three of six.
"Nearest preceding assignment" is not a sound reaching-definition analysis, and
#254's separated investigations recorded the same limit. Therefore:

- **v1 requires no data definitions.** A candidate under this contract delivers R1-R7
  structure and statements only.
- Local definitions are a **separate, later variable** (v1.1), tested only after v1
  has a recorded result. If a later contract adds them, each delivered definition
  carries its own R1-R7 structure, and a name with more than one candidate
  definition is reported rather than guessed.
- Names defined outside the function (imports, module globals, other functions) are
  never delivered by this contract.

## 7. Selector boundary

**Allowed inputs:** the query text; the retrieval candidates and graph neighbours the
control already produces; node bodies obtained through the ADR-055 endpoint for the
control's selected document set; the AST of those bodies; the 4096-byte budget.

**Forbidden inputs:** the manifest's `operations` and `dependencies` expressions,
witness line ranges, oracle outputs, case ids, expected answers, rubric text, or any
source text not obtained through the governed path. The manifest is used only to
score outputs (as in the prototype contract). The candidate selector's code and
parameters are frozen and hashed before the first scored run, and are not tuned on
the cases they are scored on.

## 8. Budget, ordering, failure behaviour

- **Budget.** Labels, separators, markers and all lines count inside the 4096 bytes
  with the existing byte-counting function. A statement is never truncated: if it
  does not fit it is dropped, together with structure that only it required.
  Structure required by a kept statement is never dropped to make room.
- **Order.** Blocks are ordered by the selector's priority, ties broken by
  canonical id; within a block lines keep source order.
- **Fencing and provenance.** Node text is requested for the control's ready
  generation; a generation mismatch is an error, not a silent mix (ADR-052/ADR-055).
  Each block records generation id, canonical id, node-text SHA-256 and delivered
  line spans in the final-context manifest.
- **Fallback.** If a node body is unavailable, cannot be parsed, or its required
  structure for even the highest-priority statement exceeds the budget, that
  document is delivered by the control's existing chunk passages and the manifest
  records `delivery_mode: chunk_fallback` with the reason. Fallbacks are counted and
  reported per case; they are never silent and are not counted as statement-mode
  successes.

## 9. Scoring and decisions

Scores are reported separately and never merged into one number:

| Score | Definition |
| --- | --- |
| S1 Discovery | unchanged from the baseline protocol |
| S2 Target survival | unchanged: target document present after document selection and in the final context |
| S3 Operation and dependency coverage | frozen operation and dependency expressions present in the final context, as in the E1 baseline |
| S4 Faithfulness | every non-marker delivered line equals a line of the pinned node text, in order; automated; must be 100% |
| S5 Structure sufficiency | automated: for every delivered statement, all lines required by R1-R7 are present; must be 100% |
| S6 Budget | final context at most 4096 bytes including labels, separators and markers |
| S7 Fallbacks | count and reasons of `chunk_fallback` documents |
| S8 Answer review | manual, per-case rubric, correctness / attribution / grounding separately, recorded separately from delivery |

A case **passes the delivery gate** when S3 is complete, and S4, S5 and S6 hold.
Answer quality (S8) is recorded but does not decide the delivery gate.

Decisions use the roadmap's three outcomes:

- **GO** (to propose a production change): requires a frozen candidate that passes
  the delivery gate on the held-out set (section 10) at a rate fixed in advance by
  the owner (section 11), with no case worse than its own unchanged control. The
  development cases cannot produce GO.
- **NO-GO:** the candidate violates S4, S5 or S6 in any case, or is worse than its
  unchanged control on a held-out case. "Worse" means it covers fewer of that case's
  required operations or dependency expressions (S3) than the control, or loses a
  target the control kept (S2).
- **INVESTIGATE:** anything else; record the next experiment, do not expand scope.

No result under this contract authorizes a retrieval-policy merge or deployment.

## 10. Held-out evaluation plan (ADR-054)

The six E1 cases (LightRAG and this repository) are **development data**. Together
with `py-coding-agent`, these three repositories are excluded from held-out use.

**Eligibility of a held-out repository.** Never used for development or diagnosis in
this project; Python; license allows storing the pinned function bodies in a
manifest; pinned by commit SHA; ingestible by the unchanged pipeline to a ready
generation. The repository and commit are chosen before any retrieval or candidate
output on it is seen.

**Stratification, declared before selection.** Cases are chosen to cover the spread
observed in development, using these measurable properties of the target
function(s): body length in lines; parameter-list length in lines (signature cost);
depth of control-flow nesting at the witnesses; spread of the witness lines;
number of functions the answer needs (1-3); presence of `else`/`elif`/`try`.
At least one case must resemble each development extreme: a long signature with
witnesses in several functions (L1-like), one long function with widely spread
witnesses (F3-like), and a small function (F1-like).

**Authoring and freezing.**
1. A case author writes the question and the required operation and dependency
   expressions from the source only, before any retrieval or candidate run.
2. A second reviewer confirms each expression is unambiguous in its function (its
   first line occurs once, or the line is pinned) and answers the question as
   written.
3. Questions, expressions, pinned source bodies, repository and commit are written
   into a manifest with a SHA-256 and committed before the candidate selector's code
   is frozen. Nothing in it is edited afterwards.

**Use rules.**
- The unchanged control runs on the held-out cases too, and control drift is reported.
- Each frozen candidate version is run on the held-out set once. A failed
  held-out case is not retried or fixed in place; after any held-out result is used
  to change a candidate, those cases become development data and a **new** held-out
  set must be frozen for the next version.
- Results are reported per case and never pooled with development results.

**Size (proposal, owner to confirm in section 11).** At least 12 cases across at
least 3 repositories (4 per repository). At that size only large differences are
detectable; no rate estimate or generalization claim beyond "did or did not hold on
these cases" is made.

## 11. Decisions required from the owner before freezing

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | Signature: full verbatim (R1) or a shorter non-verbatim form | Verbatim. A shorter form saves up to 27% of a case (L1/L2 signatures cost 1,052 of 3,926 bytes) but breaks the "every delivered line is source" guarantee that S4 relies on. Revisit only if v1 fails for budget reasons |
| 2 | Marker format and where line positions live | As in section 4: function-relative positions in the label and markers; about 10% of block bytes |
| 3 | Data definitions (v1.1) | Out of v1; decide after v1 has a result |
| 4 | Held-out size and the rate required for GO | 12 cases over 3 repositories; GO rate to be set by the owner before the held-out manifest is frozen, not after |
| 5 | Language scope | Python only for v1 (extractors exist for TS/JS, Rust and Java but the reference rules were validated on Python only, and only on module-level functions; methods and nested functions are unvalidated until a held-out case uses them) |
| 6 | ADR-055 (node-text endpoint) | Accept before any implementation issue; implementation is a separate, later issue |

## 12. Preconditions before any candidate run

1. This contract accepted and frozen (section 1) and ADR-055 accepted.
2. A trustworthy matched control replay that also records the pre-budget candidate
   pool (#270; the graph-load timeout is unexplained and PR #272 is merged but not
   deployed or shown to cure it).
3. The held-out manifest frozen (section 10).
4. Target-first selection (#275) kept as a separate experiment: if the target is not
   in the control's selected document set, statement-level delivery cannot help and
   the case is reported as a selection failure, not a delivery failure.

## 13. What this contract does not claim

Feasibility is oracle evidence on six Python development cases in two repositories.
It does not show that a selector can find the evidence, that models answer better
from it, or that the approach generalizes. Option B is not yet justified over fixing
target selection; it is a candidate to be tested.
