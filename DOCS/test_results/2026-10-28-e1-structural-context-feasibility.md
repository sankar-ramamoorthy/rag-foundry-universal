---
title: "E1 structural-context feasibility oracle: do source-faithful statements plus enclosing structure fit 4096 bytes?"
date: 2026-10-28
type: evaluation-report
status: oracle-complete-no-selector-evaluated
tags: [evidence-coverage, feasibility, structural-context, statement-level-delivery, oracle]
related:
  - "[Issue #276: statement-level delivery contract](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/276)"
  - "[4096-byte feasibility oracle (#264)](/DOCS/test_results/2026-10-21-e1-4096-byte-evidence-feasibility.md)"
  - "[E1 baseline results](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)"
  - "[#254 automatic coverage and grounding investigations](/DOCS/test_results/2026-10-12-issue-254-separated-investigations.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Raw results](/DOCS/test_results/code-evidence-e1/structure-oracle.json)"
---

# E1 structural-context feasibility oracle

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by
#276. Offline and deterministic; no service, database, model, retrieval policy,
context assembly or cap was touched.

## Question

The [#264 oracle](/DOCS/test_results/2026-10-21-e1-4096-byte-evidence-feasibility.md)
showed that bare witness statements fit 4096 bytes in all six frozen E1 cases.
Bare statements can mislead: a line from an `else` branch means nothing without
its condition, and a use of a variable means little without its definition. So:

**Can source-faithful statements, including the structure needed to read them
correctly, fit the unchanged 4096-byte final context?**

## Claim boundary

This is an **oracle**. It reads the frozen witness expressions from the pinned
manifest, which a query-time selector cannot know. A fit shows that a sufficient
context *exists within the cap*; it does not show that any automatic mechanism can
find it, and it is not retrieval success. The six cases are development data on
two repositories and support no generalization claim (ADR-054).

## Method

Reproduce with `./.venv/Scripts/python.exe scripts/code_evidence_structure_oracle.py --json DOCS/test_results/code-evidence-e1/structure-oracle.json`.

Each manifest source is one pinned function body. The script parses it with
Python's `ast` and builds one block per function from **verbatim source lines
only**, plus explicit `# ... lines A-B omitted` markers where code is left out
(verified: every delivered non-marker line equals the source line, 44/44 blocks).
Bytes use the production `[Source: ...]` rendering and `\n\n` separators, with the
label extended by the delivered line span (`[lines 7-141]`) so locations are kept.

| Tier | Contents (each includes the previous) |
| --- | --- |
| T0b | the witness statements only, one block per function with omission markers |
| T1 | + function signature (decorators and full parameter list) + the headers of every enclosing `if`/`elif`/`else`, loop, `with`, `try`/`except`/`else`/`finally` |
| T2 | + the nearest preceding local definition of every name the witness statements read (one hop) |
| T3 | + the transitive closure of T2 (an upper bound) |

A witness is expanded to its **whole enclosing statement** (or compound-statement
header). An earlier draft expanded forward from the matched line only, which
delivered orphaned fragments such as `"max_entity_tokens",` from the middle of a
`getattr(...)` call; that defect was found by reading a rendered block and fixed.

**Ambiguity.** A witness whose first line occurs more than once in its function is
ambiguous. Two readings are reported: `first` (the first occurrence, as #264 did)
and `all` (every occurrence, an upper bound). Ambiguous expressions: L1/L2 1, L3 2,
F2 2, F3 2, F1 0.

## Results

Bytes (slack to the 4096 cap), reading `first`; `*` = over the cap.

| Case | T0b | T1: + signature and enclosing structure | T2: + one-hop definitions | T3: + definition closure |
| --- | --- | --- | --- | --- |
| L1 | 2,633 (1,463) | **3,926 (170)** | 5,820 (-1,724) * | 6,488 (-2,392) * |
| L2 | 2,633 (1,463) | **3,926 (170)** | 5,820 (-1,724) * | 6,488 (-2,392) * |
| L3 | 1,503 (2,593) | 1,831 (2,265) | 2,116 (1,980) | 2,116 (1,980) |
| F1 | 626 (3,470) | 837 (3,259) | 854 (3,242) | 854 (3,242) |
| F2 | 851 (3,245) | 1,018 (3,078) | 1,018 (3,078) | 1,018 (3,078) |
| F3 | 1,848 (2,248) | 2,679 (1,417) | 4,674 (-578) * | 6,862 (-2,766) * |

Reading `all` changes only F2 and F3: F2 T1 1,030, F3 T1 2,987 (slack 1,109), F3 T2
5,253 (over by 1,157), F3 T3 7,230. Every fit/no-fit outcome is the same under both
readings. L1 and L2 share one evidence set and give identical rows.

For comparison, the #264 whole stored chunks (not source-faithful, no signature or
branch guarantee) cost 3,967 (L1/L2), 2,232 (L3), 754 (F1), 2,052 (F2) and 7,397
(F3) bytes.

### Where the T1 bytes go

| Case | witness statements | signature | other structure | omission markers | labels and separators | total |
| --- | --- | --- | --- | --- | --- | --- |
| L1/L2 | 2,161 | 1,052 | 83 | 434 | 199 | 3,926 |
| L3 | 1,288 | 155 | 83 | 238 | 68 | 1,831 |
| F1 | 387 | 158 | 0 | 109 | 185 | 837 |
| F2 | 580 | 115 | 28 | 191 | 105 | 1,018 |
| F3 | 1,446 | 705 | 101 | 359 | 69 | 2,679 |

## Findings

Measured:

1. **Structure alone fits all six cases.** T1 is within the cap in every case under
   both readings. Branch, loop, `with` and `try` headers are cheap (0-101 bytes per
   case). The expensive structural items are **signatures**: 1,052 bytes for L1/L2
   (27% of their total) and 705 for F3, because those functions have long annotated
   parameter lists.
2. **L1/L2 fit only marginally.** 170 bytes of slack (4% of the cap) at T1. Their
   cost is dominated by the witness statements themselves, spread over three
   functions (2,161 bytes), so structural context leaves almost nothing spare.
3. **Data-dependency context does not fit in general.** Adding the nearest
   preceding definitions (T2) exceeds the cap for L1/L2 (by 1,724) and F3 (by 578 to
   1,157); the closure (T3) exceeds it for the same three. L3, F1 and F2 fit through
   T3. So statements with their enclosing structure are affordable; statements with
   their data dependencies are affordable only in some cases.
4. **The advantage over whole chunks is case-dependent.** At T1 the verbatim,
   structure-preserving form costs about the same as whole chunks for L1/L2 (3,926
   vs 3,967), slightly more for F1 (837 vs 754), less for L3 (1,831 vs 2,232) and
   much less for F2 (1,018 vs 2,052) and F3 (2,679 vs 7,397). The gain is concentrated in
   long functions with widely spread witnesses.
5. **The #264 "exact statements" figures were optimistic for some cases.** That
   oracle expanded each witness forward from its first line, so a witness in the
   middle of a multi-line expression was counted as a fragment. Whole-statement
   expansion raises the bare-statement cost (L1: 1,971 in #264, 2,633 here; the
   two are not byte-for-byte comparable because this report uses one labelled
   block per function with markers). The conclusion that bare statements fit in all
   six cases still holds.
6. **No parse failures and no unlocated expressions.** Every frozen expression was
   located, and all seven manifest functions parsed.

Explicit omissions and uncertainty, recorded in the raw JSON per case:

- **Docstrings, comments and unselected statements** are omitted and marked.
- **Names defined outside the function** (imports, module globals, other
  functions) are never included at any tier: 5 to 31 per case at T3 (for example
  19 for L1/L2, 31 for F3). They are listed, not delivered.
- **"Nearest preceding definition" is not a sound reaching-definition analysis.**
  It ignores which branch a definition is on. Names with more than one candidate
  definition are flagged: `entity`, `relation` (L1/L2/L3), `used` (F1),
  `agent_chunks`, `llm_context`, `obligation`, `policy_document_ids` (F3). T2/T3 are
  therefore cost estimates, not certified-complete dependency sets.
- Walrus assignments, `match` statements and comprehension scoping are only
  approximated; none of them produced a recorded failure in these cases.

## Relationship to #254's earlier experiments

The [#254 investigations](/DOCS/test_results/2026-10-12-issue-254-separated-investigations.md)
reported two failure modes for an automatic AST selector: it did not preserve
`else` provenance, and nearest-preceding assignment was not branch-sensitive. This
oracle handles the first explicitly: a statement in an `else` or `elif` keeps the
governing `if` header, every earlier `elif` header and the `else:` line (unit-tested).
It does **not** solve the second; it counts and lists the ambiguous names instead.
It also does not test selection: #254's selector found 4 of 5 primary witnesses
without oracle line ranges, and nothing here supersedes that. #254 stays parked and
its candidate unmerged.

## What this means for #276 (inputs to the contract, not decisions)

Which of the three possible outcomes applies is mixed. "All six fit" holds only for
structure without data dependencies, and only marginally for L1/L2. The contract
therefore has to decide, and state, at least:

- Whether delivered structure is the full verbatim signature or a shorter,
  non-verbatim form. Signatures are the largest structural cost (up to 27%); a
  shorter form would save bytes but break the "every delivered line is source"
  guarantee.
- Which data dependencies are required, which are best-effort, and how a missing
  definition is signalled to the reader, since requiring them breaks the cap in
  3 of 6 cases.
- The omission-marker format (about 10% of T1 bytes) and whether locations belong
  in the label, the marker or both.
- That all of this describes oracle evidence; a selector that does not know the
  witnesses will pay more.

Option C (a bounded multi-step workflow) remains deferred, not a fallback. Target-first
selection (#275) is a separate question and is untouched.

## Limitations

- Oracle knowledge of witnesses; no selector was built or evaluated.
- Six development cases, two repositories, all Python, all module-level functions;
  no generalization claim, and held-out cases still have to be frozen before any
  candidate runs.
- Function-relative line numbers (the pinned bodies do not record file offsets).
- Structure and dependency rules were written before running and then corrected once
  for the mid-expression defect above; the numbers reported are from the corrected
  version only. The `first` reading reuses #264's first-occurrence choice; ambiguity
  is bounded by the `all` reading, not resolved.
- Whether a human or model can *answer correctly* from these blocks was not tested.

## Decision

No architecture, retrieval or deployment change is made. #276 proceeds to the
contract draft with the findings above. #275 remains blocked on a trustworthy
matched control replay (#270).
