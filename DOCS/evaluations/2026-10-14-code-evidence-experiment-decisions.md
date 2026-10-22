---
title: "Code evidence delivery: agreed decisions and baseline protocol"
date: 2026-10-14
type: evaluation-decision
status: accepted-experiment-scope
tags: [retrieval, evidence-coverage, lightrag, baseline, local-experiment]
related:
  - "[LightRAG forensics](/DOCS/test_results/2026-10-13-lightrag-implementation-forensics.md)"
  - "[Direct PostgreSQL results](/DOCS/test_results/2026-10-13-lightrag-direct-sql.json)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Issue #254 deferral](/DOCS/notes/2026-10-12-issue-254-deferred.md)"
  - "[Project status](/DOCS/status.md)"
---

# Code evidence delivery: agreed decisions and baseline protocol

## Decision and authorization

The user authorized experiment design, baseline capture and local prototypes.
No production deployment or retrieval-policy merge is authorized for this work.
This records an evaluation decision; it does not adopt a production architecture
or selection algorithm. Existing runtime code and the unmerged #254 candidate
remain unchanged while the baseline is established.

Measure three capabilities independently: discovery of the implementation,
delivery of sufficient implementation evidence, and faithful interpretation by
the model. A discovered symbol, a citation ID, or a correctly formatted answer
does not establish success at the later stages.

Keep #254 deliberately deferred with its failed acceptance gate open. Preserve
its unmerged candidate and diagnostic reports. C1 remains a separate historical
grounding defect. Leave #243's held-out evaluation untouched. LightRAG is now a
diagnostic corpus, not independent held-out evidence.

## Established evidence and current execution state

Direct PostgreSQL verification is complete for `_build_query_context`,
`_apply_token_truncation` and `_build_context_str` in LightRAG generation
`128c494e-0aae-4e1d-81d0-b7e52f2006b1`, source commit
`4d0afc1bc36e6a34d4a5895b68efe9413748627a`. Their 10, 19 and 17 chunks match
the API inventory exactly; full node bodies match pinned source ignoring
whitespace. All 46 inspected vectors have 1024 dimensions, with no inspected
identity/generation mismatches or missing vectors. This finding is scoped to
those records, not an audit of every repository record.

Existing diagnostic replays establish passage-fetch and final-budget losses.
They also identify a separate natural-language discovery-survival failure.
Original UI settings and original server-side request logs remain unverified.
Database integrity verification is complete; retrieval-quality remediation is
open.

The [E1 case manifest](/DOCS/evaluations/code-evidence-e1/README.md) is now frozen.
The [completed baseline](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)
captures all six cases: discovery 6/6, document survival 5/6, operation coverage
6/26 and dependency expression coverage 6/20. Full semantic efficiency review
and prototype quality results remain **pending**. The first unchanged prototype
control stopped at a full-graph response timeout before any selector arm ran.
No compact automatic strategy is claimed to pass.

## Freeze before tuning

Select additional cases by control-flow shape before examining their baseline
answers: long functions, nested branches, cross-file helpers and state
initialization. Use multiple repositories outside #243's reserved corpus. Known
development repositories may supply regression cases, but cannot support an
independent generalization claim. Preserve the original #254 questions; do not
resume tuning its failing agent-loop case under this workstream.

For every case, record the exact question, repository/source commit, ready
ingestion generation, target canonical IDs, mandatory operation witnesses,
branch/caller/state dependencies, authoritative source spans and text hashes.
Freeze expected evidence from source before reading baseline answers. Source
spans are scoring oracles; prototype selectors must not receive manual witness
line ranges, case-specific answers or special handling for LightRAG names.

Record local code commit and working-tree changes, service-reported runtime
versions, model identity, exposed provider/model settings, retrieval settings,
reranker state, document/fetch caps and exact final context budget. Mark any
unexposed configuration unknown. Record request payloads and settings before and
after capture; a changed source generation invalidates a matched comparison.

No database writes, re-ingestion or migrations are part of this experiment.
Missing source access must be reported, not replaced with an assumption that
the live retrieval path provides entire files or function bodies.

## Baseline metrics and scoring

| Metric | Definition |
| --- | --- |
| Target discovery | Presence of the expected canonical symbol in initial retrieval or graph expansion before document selection; report the stage and rank. |
| Target survival | Presence after document selection; report both per-case success and survival conditional on discovery. |
| Required operation coverage | Number of mandatory source operations present in actual final context divided by the frozen number required. |
| Dependency coverage | Number of frozen branch, caller and state-dependency obligations satisfied in actual final context divided by the number required. |
| Evidence efficiency | Unique relevant source bytes delivered divided by the fixed 4096-byte cap; also report their fraction of actual delivered bytes. |
| Answer faithfulness | Separately score factual correctness, responsible component attribution, citation support and unsupported claims against delivered evidence. |

Missing traces or unavailable final payloads are unverified, not zero scores.
For a zero-obligation denominator report not applicable. Publish raw numerators,
denominators and per-case results alongside aggregate results so partial gains
cannot conceal failed cases.

An operation witness must include the actual source expression and enough
surrounding code to identify its actor and relevant conditions. Keyword mentions,
signatures or a source ID alone do not count. A branch excerpt that loses its
paired branch or changes the apparent condition fails the relevant dependency.
Concise excerpts are allowed; fabricated pseudocode or rewritten source is not.

For efficiency, map relevant ranges back to pinned source and count each source
range once per case, even when duplicated across file and symbol chunks. Count
UTF-8 bytes, not characters or tokens. Report actual payload bytes, citation-label
and separator overhead, duplicated source bytes, and irrelevant source bytes
separately. High efficiency without complete mandatory coverage is not a pass.

Record exact delivered text and its hash; reconcile them with the manifest and
the observed generation request. Report whether observations came from the live
service or a local replay. A local payload matching a live manifest does not
become an original live wire capture.

## LightRAG mandatory witnesses

For the existing explicit implementation question, the evidence gate requires:

1. `_build_query_context`'s Stage 2 call to `_apply_token_truncation`.
2. The entity truncation operation and its `max_entity_tokens` limit.
3. The relationship truncation operation and its `max_relation_tokens` limit.
4. `_build_context_str`'s combined-budget calculation and the operation using
   that remainder as the text-chunk allowance.

Freeze dependencies connecting the selected entity/relation results to context
construction. Score an explanation of the remainder's scope separately from
evidence presence: the answer must not invent a final whole-prompt clamp.

Before prototype selection, establish whether source-faithful witnesses plus
their required dependencies and citation overhead can fit inside 4096 bytes.
A manually assembled feasibility check is an oracle control, not proof of an
automatic selector. If they do not fit, record the limitation and stop adoption
of this approach rather than silently increasing the budget or weakening gates.

## Execution order and isolation

| Phase | Allowed experimental change | Held fixed |
| --- | --- | --- |
| 0: freeze and baseline | No selection change; capture cases, traces, payloads and scores | Current runtime policy and all comparison settings |
| 1: discovery survival | Candidate ordering before the existing document cap, using explicit symbol matches and relevant graph relationships | Passage fetching, assembly, document cap and final budget |
| 2: passage coverage | Source-coherent continuation/callee selection using available retrieval interfaces | Frozen selected document set, document cap, assembly and final budget |
| 3: context allocation | Duplicate removal and byte allocation among the same fetched candidates | Discovery, fetched candidate set, document cap and final budget |
| 4: combined validation | Combine only mechanisms that independently meet their gates | Frozen suite, model, prompt, source generation and final budget |

Use the same question, model and prompt in every matched arm. Freeze and report
any bounded targeted-fetch allowance before Phase 2, including request counts,
returned bytes and latency. Do not increase global `EXPANDED_DOC_CHUNKS` or other
caps as an unreported treatment. Fetching more evidence is a distinct cost from
delivering more useful evidence.

No hidden budget increases: the actual final generation context must stay at or
below **4096 UTF-8 bytes**, including labels and separators. Do not move source
evidence into another prompt field to bypass accounting, change model/context
settings, or tune the grounding prompt during selection comparisons.

Stop an unsuccessful mechanism in its current form. Preserve negative findings
and avoid further R1-specific or LightRAG-specific heuristic tuning. Successful
evidence delivery still requires separate answer-quality evaluation.

## Adoption gates and reporting

Before considering a production candidate, require all mandatory evidence and
dependency gates on the frozen suite, payload/manifest consistency, fixed-budget
compliance, and no regressions in existing overview and explicit-code controls.
Preserve the eight passing overview cases and established explicit-code controls
with their original settings; distinguish controls from new implementation arms.
Run meaningful local mechanics tests without treating unit-test counts as a
retrieval-quality pass.

Report baseline and each arm separately, including failures, source-access
assumptions, fetch costs and answer scores. Only successful mechanisms may be
combined. Passing these development gates permits a reviewable recommendation;
it does not authorize merge or deployment, resolve #254, or complete #243.
