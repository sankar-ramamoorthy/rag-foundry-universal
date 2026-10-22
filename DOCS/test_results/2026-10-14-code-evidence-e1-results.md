---
title: "E1 code-evidence baseline: six captured cases and prototype control timeout"
date: 2026-10-14
type: evaluation-report
status: baseline-complete-prototype-evaluation-incomplete
tags: [evidence-coverage, baseline, lightrag, development-regression]
related:
  - "[Agreed decisions](/DOCS/evaluations/2026-10-14-code-evidence-experiment-decisions.md)"
  - "[Frozen cases](/DOCS/evaluations/code-evidence-e1/README.md)"
  - "[Baseline audit](/DOCS/test_results/code-evidence-e1/baseline-audit.json)"
  - "[Execution contract](/DOCS/evaluations/code-evidence-e1/execution-contract.json)"
  - "[Prototype contract](/DOCS/evaluations/code-evidence-e1/prototype-contract.md)"
  - "[Earlier availability record](/DOCS/test_results/2026-10-14-code-evidence-e1-baseline.md)"
---

# E1 code-evidence baseline

## Outcome

All six frozen baseline cases completed on October 14 local time (UTC capture
timestamps October 15, approximately 01:44-01:50). Each used unchanged local
orchestrator code against existing remote services. This is actual local
generation-payload evidence, not original UI or deployed-orchestrator wire
capture. No application code, policy, source generation, prompt or budget was
changed.

Discovery succeeded in **6/6**, document survival in **5/6**, and the target
appeared in final context in **3/6**. Only **6/26 required operations** and
**6/20 dependency expression obligations** reached final context. No case had
complete mandatory implementation evidence; source-based answer review accepted
**0/6 full answers**.

The three prototype definitions and local runner are prepared, but **none was
evaluated**: the first unchanged control replay timed out downloading the full
LightRAG graph before any candidate selector ran. This is an execution failure,
not evidence that a candidate algorithm passed or failed. No mechanisms were
combined, no adoption/control suite was claimed complete, and no prototype
payload was sent to the model.

## Frozen settings and integrity checks

Source commits and ready generations match the frozen manifest for both
repositories. Four services self-report runtime commit
`109f12d83ab83a306318423be618c195f8c4e6ea`. This is not independent image/config
attestation. Query model is `ollama/Qwen3:4b`, with no fallback in any response;
the execution contract records available model digests. The deployed prompt
file hash is not independently exposed; the local prompt hash is recorded.

Top K remains 20, expanded-document cap 20, ranked passage fetch three per
document, adapter limits five per document/50 total, reranking off and overview
controls off. The actual final cap is **4096 UTF-8 bytes**, including labels
and separators. No evidence was moved into another prompt field to bypass it.

The offline audit checks all six cases for:

- Exact frozen question and manifest checksum.
- Generation stability before/after and scoped repository/generation metadata
  on all returned vector-service records.
- Expected runtime self-reports and requested answer model with no fallback.
- Final manifest/chunk ID and text-hash correspondence.
- Exact reconstruction of the generation context from selected chunks/labels.
- Equality of reconstructed, assembled and submitted context bytes and counts.

These checks pass. The largest delivered context is 4065 bytes. Eleven focused
unit tests, Ruff and Pyright checks validate local harness/prototype invariants;
they do not establish selector quality.

## Per-case evidence baseline

| Case | Discovered | Survives document selection | Target in final context | Operations | Dependency expressions | Context bytes |
| --- | --- | --- | --- | --- | --- | --- |
| L1: explicit graph-context implementation | Yes | Yes | Yes | 0/4 | 0/4 | 3960 |
| L2: natural-language context discovery | Yes | No | No | 0/4 | 0/4 | 3940 |
| L3: independent graph token limits | Yes | Yes | Yes | 3/4 | 3/3 | 4065 |
| F1: oversized-passage skip/byte counter | Yes | Yes | Yes | 3/4 | 3/3 | 4038 |
| F2: generation-aware cache | Yes | Yes | No | 0/5 | 0/3 | 4050 |
| F3: retrieval-to-generation pipeline | Yes | Yes | No | 0/5 | 0/3 | 3963 |

L1 reproduces the historical context hash exactly. L2 loses the target at the
document cap; the audit retains its actual expanded rank. L3 lacks the entity
truncation invocation while retaining relationship truncation and both cleanup
branches. F1 retains the assembler but lacks the UTF-8 counting helper. F2
delivers caller/ADR/test material instead of the target body. F3 delivers archived
handover/cheat-sheet text; its ADR-052 passage contains only the heading.

Dependency scores check frozen conditions/state expressions against source
identity. They are **not proof of complete branch semantics**: disjoint snippets
and lost ordering still require review. No case passes the joint evidence gate
regardless of this limitation.

## Efficiency measurements and limits

| Case | Labels/separators | Bytes matching frozen symbols, proxy | Exact expression bytes in fully satisfied operations |
| --- | --- | --- | --- |
| L1 | 234 | 1702 | 0 |
| L2 | 324 | 0 | 0 |
| L3 | 323 | 1589 | 224 |
| F1 | 692 | 489 | 113 |
| F2 | 940 | 0 | 0 |
| F3 | 1000 | 0 | 0 |

The source-membership proxy counts unique unambiguous nontrivial lines inside
the frozen target/helper bodies, excluding indentation/whitespace and ambiguous
short lines. It includes signatures, setup and comments, so it is **not a
semantic relevance score or a lower bound on useful implementation evidence**.
Existing raw fields named `unique_relevant_bytes_lower_bound` refer to this
limited counting method. Do not interpret them as demonstrating useful coverage.

The last column separately counts unique nonwhitespace bytes of the exact
frozen expressions belonging to fully satisfied operations. It excludes other
useful surrounding code and is not a complete semantic efficiency score either.
This clarification precedes candidate evaluation; no passing efficiency gate is
claimed from either proxy. Full semantic relevance/redundancy assessment remains
pending. Labels/separators are measured exactly from the actual payload.

F2 and F3 spend approximately 23% and 25% of their delivered bytes on citation
overhead while satisfying no mandatory operations. This is a measured allocation
cost, not evidence that citations should be removed or their accounting ignored.

## Answer review: separate correctness, attribution and grounding

This is manual qualitative review against the frozen source and delivered text,
not an unregistered numerical fact/actor aggregate or keyword-based pass rule.
Per-case assessments are retained in the audit JSON.

| Case | Factual correctness | Actor attribution / grounding |
| --- | --- | --- |
| L1 | Omits required operations and incorrectly suggests final context cannot exceed the limit | Names the builder/Stage 4 helper but lacks the responsible truncation and arithmetic evidence |
| L2 | Identifies public `aquery`, then abstains on budget interaction | Example entry-point call does not establish responsibility for internal construction |
| L3 | Core independent limits and removed fields are correct | Entity call is inferred despite absent delivery; utility is incorrectly located in `operate.py`; partial excerpts cannot prove function-wide absence of a total cap |
| F1 | Correct skip/separator explanation; incorrect token-estimate description of byte counting | Correct assembler attribution, missing byte-helper implementation |
| F2 | Wrong no-ready-generation behavior, denies `force_reload`, omits LRU bound | Treats caller/ADR evidence as the implementation and overstates zero-staleness guarantees |
| F3 | Claims byte budgeting is unimplemented and uses word counts; misses manifest/payload handoff | Uses archived design material as current authority and confuses adapter output with final context |

Correct facts inferred from incomplete context are not evidence-delivery passes.
Likewise, F3's wrong product description is influenced by actually delivered
historical text; this is not proof of model failure under complete current code.
C1's separate historical-grounding classification is unchanged.

## Prototype execution boundary

After baseline capture, a new local process attempted unchanged control retrieval
before applying any prototype. Cached vector responses and the original query
embedding were available, but the graph cache was cold. Progress records show
the generation check completed at `01:54:13.542690 UTC`, then the full graph GET
started at `01:54:13.545327 UTC`:

```text
GET /v1/graph/repos/4f76a36f-caf8-5532-9ee2-977ec412ed6c
```

The response-body read exceeded the diagnostic 120-second timeout and raised
`requests.exceptions.ConnectionError`. A subsequent small version request also
reset. The incomplete control record and request events are retained. There is
no completed control or candidate score, and no prototype model invocation.
This identifies where this attempt stopped, but does not establish OOM,
container restart, network fault or that the graph request caused the outage.

Stop additional full-graph retries until service stability is understood. Preserve
the six valid baseline captures: they do not need to be discarded because a
later process failed. Resume the prepared isolated experiments only after a
matched unchanged control completes. No baseline evidence or source must be
silently replaced to bypass this prerequisite.

## Decision

Evidence-delivery losses extend beyond the original LightRAG question in these
two development repositories. They do not establish held-out generalization.
Keep discovery, passage selection, context allocation and reasoning scores
separate. No candidate has evidence supporting adoption. #254 stays parked,
its candidate unmerged, and #243 untouched. No commit, policy merge, database
write, re-ingestion or deployment was performed.
