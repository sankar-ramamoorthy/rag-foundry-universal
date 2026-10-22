---
title: "E1 4096-byte evidence feasibility oracle"
date: 2026-10-21
type: evaluation-report
status: oracle-complete-no-selector-evaluated
tags: [evidence-coverage, feasibility, chunk-granularity, lightrag, baseline]
related:
  - "[E1 baseline results](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)"
  - "[Agreed decisions](/DOCS/evaluations/2026-10-14-code-evidence-experiment-decisions.md)"
  - "[Prototype contract](/DOCS/evaluations/code-evidence-e1/prototype-contract.md)"
  - "[Frozen cases](/DOCS/evaluations/code-evidence-e1/README.md)"
  - "[Raw results](/DOCS/test_results/code-evidence-e1/feasibility-oracle.json)"
---

# E1 4096-byte evidence feasibility oracle

Tracked by issue #264. Offline and deterministic; no service, database, model,
retrieval policy, context assembly or cap was touched. Reproduce with:

```powershell
./.venv/Scripts/python.exe scripts/code_evidence_feasibility.py --json DOCS/test_results/code-evidence-e1/feasibility-oracle.json
```

## Question

Is the fixed 4096-byte final context large enough for the essential evidence
of the six frozen E1 cases, and if so does the unit in which evidence is
delivered (stored chunks) let it fit?

## Oracle status: a bound, not a selector result

The oracle reads the frozen witness and dependency expressions from the pinned
manifest sources. A production selector does not know them. A fit here shows
that a sufficient context **exists within the cap**; it does not show that any
automatic mechanism can find it. Nothing below is a pass for a prototype.

## Method

- Per case, take every frozen operation and dependency expression (26 + 20
  obligations, 88 expression fragments in total).
- **Exact statements:** each fragment's line extended to its bracket-balanced
  statement, adjacent lines merged into ranges, one label per range.
- **Contiguous span:** one source span per function, first to last witness.
- **Whole stored chunks:** the real chunker (`ChunkerFactory.choose_strategy`
  on the manifest source text, the same call the pipeline makes) reproduces each
  document's chunks; the cheapest set of whole chunks that contains every
  fragment is chosen by exhaustive search over the containing chunks.
- **Contract windows:** the passage-only prototype's shape — at most three
  documents, one contiguous window of at most five chunks each — covering every
  fragment of that document.
- Bytes are exact UTF-8 of text rendered by the production `_render_chunk`
  (`[Source: <canonical_id>]\n<text>`) joined by the `\n\n` separator that
  `assemble_context` uses. Cap: 4096, unchanged.

**Chunker reproduction check:** the reproduced chunks match 8/8 stored chunk
texts from the six baseline captures that belong to a manifest source document
(0 mismatches). The sample is small because most baseline chunks come from other
documents. Chunk IDs are random per ingestion, so equality is on text; ordinals
are by reproduction order and not independently checked against the stored
`chunk_index` beyond those 8.

## Results

| Case | Exact statements | Contiguous span | Cheapest whole chunks | Contract windows (≤3 docs, ≤5 chunks each) |
| --- | --- | --- | --- | --- |
| L1 | 1,971 B fits | 3,677 B fits | 3,967 B, 9 chunks, fits | 5,049 B, 11 chunks, **over** |
| L2 | 1,971 B fits | 3,677 B fits | 3,967 B, 9 chunks, fits | 5,049 B, 11 chunks, **over** |
| L3 | 1,450 B fits | 4,552 B **over** | 2,232 B, 5 chunks, fits | 5,231 B, 11 chunks, **over** (also >5 chunks) |
| F1 | 697 B fits | 619 B fits | 754 B, 2 chunks, fits | 754 B, fits |
| F2 | 1,229 B fits | 1,328 B fits | 2,052 B, 4 chunks, fits | 2,052 B, fits |
| F3 | 1,719 B fits | 8,366 B **over** | 7,397 B, 7 chunks, **over** | 10,568 B, 10 chunks, **over** (also >5 chunks) |

L1 and L2 share one evidence set (same obligations). All 88 fragments were
located inside a single chunk each; none straddles a boundary.

Overhead: each separate range or chunk pays its own `[Source: ...]` label, so
many small excerpts cost more than one merged span when witnesses are close (F1:
697 B as separate ranges vs. 619 B as one span). Per-label overhead was not
broken out separately in the output.

## Findings

1. **The cap is sufficient for the essential evidence in all six cases** when
   it is delivered as exact statements (0.7–2.0 KB). It is not the binding
   constraint.
2. **Whole stored chunks fit in 5/6 cases at best.** F3 (`run_rag`, witnesses
   spread over most of a long function) needs 7,397 B even with perfect chunk
   choice. L1/L2 fit with only 129 B of slack (3,967 B), so a selector that
   delivers any non-required chunk fails.
3. **The passage-only contract as written is infeasible for 4/6 cases, even
   with an oracle.** Its contiguous-window rule forces the bytes between
   non-adjacent witnesses into the context (L1/L2 5,049 B, L3 5,231 B) or
   exceeds the five-chunk window (L3, F3). Only F1 and F2 can pass. A
   non-contiguous chunk choice fits L1/L2/L3 and is a change the contract would
   need: allow several windows or individually chosen chunks per document.
4. **The allocation-only contract inherits the whole-chunk limit.** Even a
   perfect allocator over complete stored chunks cannot pass F3 and has 129 B
   of slack on L1/L2. Whether the baseline candidate pool contains the needed
   chunks is not measured here — the baselines retain only post-budget chunks.
   The pre-budget pool was never captured because the control replay timed out.
5. **Chunks are not source-faithful.** The paragraph chunker splits on blank
   lines, strips each paragraph and rejoins with `\n\n`. Of the reproduced chunks
   for the target documents, 6/19 (`_apply_token_truncation`), 4/10
   (`_build_query_context`), 1/17, 1/3 and 1/7 are not verbatim substrings of
   the pinned source (lost indentation and normalized blank lines). Fixed-
   character chunking, used for text over 10,000 characters, cuts at arbitrary
   offsets. The earlier decision that excerpts must be "source-faithful, not
   rewritten" therefore already fails for chunk delivery today, and any
   statement-level mechanism must read the node body rather than chunks.
6. **Dependency semantics remain a limit.** Fragment containment is the same
   automated check E1 used; it does not prove branch pairing or ordering is
   preserved in the chosen chunks.

## Correction to my earlier estimate

A first pass in the conversation estimated whole-chunk costs by assuming
~1,000-byte chunks and 1,000-byte buckets, giving L1/L2 ≈ 6.3 KB, L3 ≈ 4.2 KB,
F3 ≈ 8.5 KB (over). Measured on the real chunks, L1/L2 are 3,967 B and L3 is
2,232 B (both fit); only F3 remains over. The conclusion changed from
"whole chunks fail in 4/6" to "whole chunks fail only in F3, but the
contract's contiguous windows fail in 4/6".

## What would have to change

- Passage-only: permit multiple non-adjacent chunks or windows per document, or
  select at statement granularity from node bodies. Neither is permitted by the
  frozen contract; changing it requires a new frozen contract, not tuning.
- F3-type questions (witnesses spread across a long function) need a bounded
  multi-step workflow or statement-level extraction; no single-context chunk
  selector fits.
- Slack is thin for L1/L2 at chunk granularity; label overhead per distinct
  chunk (tens of bytes each) matters.

## Limitations

- Oracle knowledge of witnesses; not an automatic selector.
- Only the six frozen development cases over two diagnostic repositories; no
  generalization claim.
- Chunker reproduced offline from pinned source text, validated on 8 stored
  chunks only. The deployed ingestion generation was not re-queried for its full
  chunk lists.
- Cost excludes the question, prompt and any policy text, which live outside
  the context cap per the E1 contract.
- Exact-statement ranges extend only through bracket-balanced statements; they
  are a minimal sufficient bound, not a quality judgement of the excerpts.

## Decision

No architecture change, deployment or policy change is made. The result narrows
the engineering problem to evidence granularity; the next architectural choice
(statement-level delivery vs. multi-step workflow) is open and unimplemented.
