---
title: "E1 mechanism specification: named-symbol-first ordering"
date: 2026-11-09
type: experiment-specification
status: draft-pending-owner-review
tags: [held-out, adr-054, mechanism-spec, byte-allocation, named-symbol-first]
related:
  - "[Issue #323](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/323)"
  - "[Issue #275](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/275)"
  - "[Goal #294](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/294)"
  - "[Pre-registration (frozen)](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)"
  - "[Stage attribution for F1-F3](/DOCS/test_results/2026-10-31-e1-stage-attribution-f1-f3.md)"
  - "[Control baseline](/DOCS/test_results/2026-11-08-e1-held-out-control-baseline.md)"
---

# Mechanism specification: named-symbol-first ordering

Roadmap phase: Phase 6, workstream E. Tracked by #323 under goal #294.

This document turns the preregistered mechanism into an implementable specification. It
adds **no prediction, no threshold and no scoring rule**, and does not edit the
pre-registration. It authorizes no implementation and no run: implementation starts only
after the owner accepts this specification, and the one candidate execution needs a separate
approval (#323).

## 1. Provenance and what this was not derived from
Derived only from:
- the frozen [pre-registration](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)
  (the mechanism sentence and the mechanical "named" rule);
- the #275 stage-attribution note and the development cases F1-F3;
- the current runtime source (`rag_orchestrator/src/core/service.py`,
  `rag_orchestrator/src/retrieval/agent_adapter.py`).

Not used: any held-out capture, hash, pool, rank or per-case control result. The frozen
held-out manifest was visible to the author as a frozen input (it is also what the
pre-registration's "named" rule is applied to), but no choice below depends on a held-out
question, function name or outcome. Where a choice could be tuned, this document takes the
reading closest to the pre-registration's literal text and says so.

## 2. Mechanism (unchanged from the pre-registration)
When the query names an exact symbol that is present in the pre-budget candidate pool, that
symbol's chunks are placed first, before the unchanged byte allocation. Nothing else changes:
no chunking, no retrieval, no fetching, no budget, no selection of other chunks.

## 3. Placement
In `run_rag`, after `agent_chunks` is final (per-document and global chunk caps applied;
rerank and overview selection are off in the experiment) and **after**
`tokens_before_budget = assemble_context(agent_chunks, 2**63)`, and before
`prioritize_exact_sources` / `assemble_context(agent_chunks, context_budget)`.

Reason: the evaluation observer records the pre-budget pool from the unbounded
`assemble_context` call. Reordering after that call leaves the captured pool identical to the
control's, so pool membership and rank stay comparable and the only difference is the order
seen by the budgeted call. `assemble_context` is first-fit in list order and skips a passage that
does not fit; the mechanism does not alter that.

## 4. Definitions (all mechanical)
- **Label** of a chunk: its canonical id, taken as in the existing capture code (`canonical_id`
  on the chunk, else in `metadata`, else in `metadata.source_metadata`; empty string if none).
- **Code symbol label:** a label of the form `<path>#<name>` whose `<path>` ends in `.py`.
  Labels without `#`, or with another extension (documents, Markdown sections), are never
  candidates. *(Scope: the experiment is Python-only, as the statement-level contract's v1 is;
  extending the extension set is a new specification.)*
- **Symbol name:** the text after the first `#` (a function `run_rag`, a method
  `Agent.run`).
- **Named in the query:** the pre-registration's rule, verbatim: the symbol name appears in the
  query as a whole identifier token, i.e. the regular expression
  `(?<![A-Za-z0-9_])<re.escape(name)>(?![A-Za-z0-9_])` matches, case-sensitively, with no
  other normalization. The same regex that defines "named" for scoring defines it at runtime.
- **Promoted chunk:** any chunk in the pool whose label is a code symbol label named in the
  query.

## 5. Algorithm
Input: the ordered chunk list `C` and the original query string `q`. Output: an ordered list
with the same elements.
1. Compute the set `S` of distinct code-symbol labels in `C` that are named in `q`.
2. If `S` is empty, return `C` unchanged (the same list object) and record no promotion.
3. Otherwise return the stable partition: all chunks whose label is in `S`, in their original
   relative order, followed by all remaining chunks in their original relative order.

Consequences stated so they are not rediscovered as surprises:
- **Several named symbols:** all are promoted together, in original pool order; there is no
  ranking among them and no disambiguation by path. If two files define the same name, both
  are promoted.
- **Bare method names:** a symbol `Agent.run` is named only when the query contains
  `Agent.run`; the word `run` alone does not fire.
- **No length or stop-word filter:** a symbol named, say, `get` fires when the query contains
  the whole word `get` and a `get` symbol is in the pool. This follows the pre-registration's
  literal "named" rule. If that makes the mechanism fire on a not-named case, P2 is
  **refuted and reported**, not fixed (pre-registration rule 3).
- **Cap interaction:** promotion happens after the chunk caps, so it never admits a chunk the
  control would have dropped and never drops one it kept; it only changes which chunks reach the
  budgeted pass first. Chunks of other documents may be displaced from the final context
  (the pre-registration does not claim otherwise).

## 6. Interface
- A pure function `promote_named_symbol_chunks(chunks, query) -> (chunks, trace)` in a new
  module under `rag_orchestrator/src/retrieval/`, with **no access** to settings, the manifest,
  case ids or `trace_canonical_ids`.
- `run_rag(..., named_symbol_first: bool = False)`. Default off; with the default the final
  context and every existing code path are unchanged.
- When enabled, `retrieval_plan["named_symbol_first"]` records `{enabled, promoted_labels,
  promoted_chunk_count}`: diagnostic only, never read by retrieval. (A new key in the plan
  changes the response but not the context; P2 compares final-context bytes.)

## 7. Acceptance mapping (from #323)
| #323 criterion | How this specification supports it |
| --- | --- |
| 2 default off is byte-identical | the flag defaults to false and the function is not called |
| 3 only order changes | stable partition (section 5); multiset equality test |
| 3 identical when nothing is named | step 2 returns the same list |
| 4 reads no case data | signature in section 6; a test pins the parameters |
| 5 verification inputs | synthetic fixtures and the F1-F3 development pools only |

Development expectation (from the #275 note, an offline counterfactual, not a held-out result):
F1 unchanged (target chunks already first, 3 to 3), F2 and F3 target chunks 0 to 3 in the final
context. This is the only prediction used to check the implementation.

## 8. Decisions made here that the owner may overrule
1. `.py`-only code labels (section 4).
2. Name-only matching, no path disambiguation, all matching symbols promoted (section 5).
3. No minimum name length or stop-word filter, accepting that the mechanism may fire on
   natural-language cases (section 5).
4. Reordering after the unbounded pool call so the pool capture matches the control (section 3).
5. A diagnostic `retrieval_plan` key (section 6).

Each is the reading nearest the pre-registration or the one that keeps the control comparison
clean. Any change the owner requests must be made **before** this specification is hashed and
before implementation; none may be made after a candidate run without making the held-out
cases development data.

## 9. Freezing
On owner acceptance: set `status: frozen-before-implementation`, add
`mechanism-spec-named-symbol-first.sha256` (SHA-256 of the LF content) and a test that pins it,
as for the pre-registration. The implementation records this hash in its capture.
