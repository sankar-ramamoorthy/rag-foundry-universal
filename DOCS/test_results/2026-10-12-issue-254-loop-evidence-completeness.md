---
title: "Issue #254: agent-loop evidence completeness versus grounding"
date: 2026-10-12
type: test-result
status: complete-with-delivery-and-grounding-failures
tags: [issue-254, evidence-survival, chunk-fetching, context-budget, grounding]
related:
  - "[Fixed-cap complete-evidence experiment](/DOCS/test_results/2026-10-12-issue-254-complete-evidence-experiment.md)"
  - "[Local policy candidate](/DOCS/test_results/2026-10-12-issue-254-policy-candidate.md)"
  - "[Original control comparison](/DOCS/test_results/2026-10-12-issue-254-overview-control-comparison.md)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #254: agent-loop evidence completeness versus grounding

**The complete implementation loop is not delivered.** Its provider-generation,
tool-call extraction and tool-result feedback passages are indexed, but are
outside the three passages fetched for `Agent.run`. All three fetched passages
survive to the generation payload. Separately, the exact `main` method is
fetched and survives chunk selection but loses to the context-byte budget.
The candidate's new answer also misinterprets delivered dispatch code by
ascribing the agent's tool lookup/execution to the LLM.

Incomplete delivery and incorrect synthesis both occur. This does **not**
prove that the LLM fails on a fully delivered loop: no such input was tested.
No classification rule, prompt, fetch setting, budget, ranking, or production
runtime was changed during this diagnosis. The policy candidate is preserved,
unmerged and undeployed; #243 was not started.

## Contract and observation boundary

Two explicit-path R1 replays use the existing local candidate and its prior
effective settings: `candidate` (claim selection and structured answers on,
canonical selection off) and `overview_off` (all controls off). Both use
`claim_type=repository_overview`, `top_k=10`, reranking off,
`EXPANDED_DOC_CHUNKS=3`, per-document selection of 5, global count of 50,
and the same 4096-byte retrieved-context cap. Structured rendering is not
eligible for this behavior query. Model responses report `ollama/Qwen3:4b`
with no fallback.

Repository `863e770d-651e-5bc5-83d1-a1409693e707` remains ready at generation
`24f827d7-a33b-45f7-93f4-ff6e5eaf3856`, source commit
`f854303e6e44ff95d94792d24868442a28080ba2`. Local HEAD and locally available
`origin/main` remain `24d956184d566753fe5ac80f57132191a4f7c3e1`; the dirty
candidate's runtime files match the prior recorded SHA-256 hashes. Upstream
ingestion, vector and LLM versions stayed at that reported commit. HTTP
metadata is not image attestation, and unexposed deployed settings remain
unknown. These are development diagnostics, not held-out generalization.

The [observer runner](/scripts/issue254_loop_diagnostic.py) calls the existing
`run_rag` with the exact saved request. Process-local wrappers copy observations
and return the original results, recording fetched chunks, plan slicing,
adapter selection, policy input/output, exact-source ordering, and assembly.
An HTTP observer records the vector request/responses and the actual
`/generate` request body and response. It never records authorization headers.

The [raw observations](/DOCS/test_results/2026-10-12-issue-254-loop-diagnostic.json)
contain both responses, stage snapshots, original request parameters, and
generation/version checks. The
[chunk and transition audit](/DOCS/test_results/2026-10-12-issue-254-loop-diagnostic-audit.json)
matches final manifests to text hashes and the generation request, and exactly
replays byte-capacity accounting over the captured assembly input. All selected
passages appear unmodified in the `/generate` context. This proves delivery to
the LLM service; it does not independently attest provider-side processing.

After both unchanged query runs, generation-fenced, out-of-band document reads
enumerate persisted passages and their query-specific distance ranks. These
reads use `k=100` for inspection only; their results are never supplied to RAG
or generation. Runtime fetch remains 3. The ranked inventory reproduces the
observed top three exactly. Source bytes are independently re-read from the
three pinned GitHub source URLs and match the previously captured snapshot.

## 1. Indexed but not fetched: the missing agent-loop transitions

`Agent.run` is graph-discovered, fetched, and present in final context. That
document-level trace is true but does not establish complete passage coverage.
The artifact has 15 persisted chunks. Its actual R1 fetch returns ordinals
**7, 9, 0**, in that order. Both arms deliver all three; no subsequent slicing,
policy rule, reranker, or byte cap removes these fetched passages.

The following are individual code obligations verified against the pinned
source. Ranks are one-based within this exact artifact for the observed
query embedding; ordinals are persisted chunk indices.

| Transition | Ordinal | Distance rank | Source line | Observed delivery |
| --- | --- | --- | --- | --- |
| Append user input to memory | 1 | 8 | 641 | Not fetched |
| Obtain active provider inside step loop | 2 | 13 | 650 | Not fetched |
| Construct messages, call `llm.generate`, extract response's `tool_call` | 4 | 9 | 684 | Not fetched |
| Read tool name/arguments from that tool call | 5 | 6 | 699 | Not fetched |
| Record assistant tool call | 8 | 4 | 727 | Not fetched |
| Look up the tool and invoke `tool.run(**args)` | 9 | 2 | 746 | Fetched and delivered |
| Append role-`tool` result to memory, then `continue` | 10 | 5 | 755 | Not fetched |

The other delivered passages are the method header/input strip (ordinal 0)
and repeated-call handling (7). Neither supplies the missing normal loop.
The first missing transition is the **within-artifact ranked fetch cut**:
`search-by-doc` only returns the highest-ranked three passages. The missing
code is present in the vector store but never crosses that fetch boundary.
This is distinct from failure to discover the method, global approximate ANN
behavior, policy exclusion, or later context budgeting.

For example, ordinal 4 shows `response = llm.generate(...)` and
`tool_call = response.get("tool_call")`. Ordinal 5 reads name and arguments
from `tool_call`; it does not parse them from the user prompt. Ordinal 10
records `{"role": "tool", "tool_call_id": ..., "content": str(result)}`
and continues the loop. No final current-code passage in the observed
candidate payload contains those normal feedback/generation transitions.

## 2. Fetched but discarded: exact `main` and full CLI method passages

**Correction to the previous candidate report:** its saved R1 traces already
showed `main` surviving chunk-count limits and then being dropped by the
context budget in all four arms. The report incorrectly called that a
chunk-count loss. The new stage snapshots corroborate byte-budget loss;
this is a corrected attribution, not a new fix.

The exact `main` document has one persisted chunk, ordinal 0, returned by
the runtime fetch. It passes the plan's five-chunk per-document slice,
the adapter's five-chunk slice/global 50-chunk selection, and policy selection.

| Assembly event | Candidate | Overview off |
| --- | --- | --- |
| Exact `main` chunk's zero-based assembly-input position | 24 | 47 |
| Byte cost including source label and separator | 1481 | 1481 |
| Capacity consumed before evaluating it | 4061 | 4036 |
| Remaining retrieved-context capacity | 35 | 60 |
| First actual rejection | Context byte cap | Context byte cap |

The chunk fits the total 4096-byte allowance in isolation; the preceding
allocation consumes the capacity. There is no per-document or global chunk
count rejection of `main` in these observed requests.

`start_cli` has two chunks. The candidate delivers ordinal 0 (the signature
and docstring), but its ordinal 1 containing the full interactive loop costs
986 bytes when evaluated with only 35 remaining. That chunk is also fetched
and discarded by the byte cap. In the off arm both method chunks lose to
the byte cap. Method-ID presence therefore does not prove that its full
implementation was delivered.

## 3. Delivered content and grounding: distinguish identity from behavior

The exact `main` method is absent, but its important startup handoff is **not**
entirely absent from context. `py_mono/main.py` file chunk 10 supplies session
manager construction, `agent = Agent(...)`, and `start_cli(agent)`.
Likewise `py_mono/ui/cli.py` file chunk 3 supplies `response = agent.run(prompt)`
and the subsequent printing of the returned response. These equivalent current
file passages reach the candidate's actual generation payload. The startup/CLI
handoffs must not be called missing solely because an exact method passage
was excluded. The central provider/result-feedback gap remains inside `Agent.run`.

The new candidate answer uses the CLI handoff and says the tool result returns
to the LLM, but relies explicitly on conventional behavior and conflates the
LLM with the agent. It says the LLM accesses `self.tools` and calls the tool's
`run`, even though delivered ordinal 9 shows that execution in the current
`Agent.run` implementation. This is an incorrect explanation of a delivered
dispatch passage. Its feedback assertion also lacks the corresponding current
memory-update/provider passage in the payload. The whole flow is still not
grounded, even though some statements now match the source by inference.

The off answer gives a conceptually correct loop using the ADR's example
flow. That does not prove complete current implementation delivery: its
critical current `Agent.run` ordinals are missing too. The extra concept-level
evidence and different answer do not isolate the LLM as the sole cause.
No complete-evidence generation control, rewritten prompt, selected oracle
context, or enlarged budget was used.

## Independent C1 failure

C1 was not changed or rerun in this two-request investigation. Its earlier
candidate response retained the requested historical note and correctly
described fixture contamination, then added unsupported claims about ORIENT's
inventory state during the incident. Keep that as a separate historical-answer
grounding defect. Nothing in the agent-loop fetch diagnosis demonstrates a
cause or correction for C1, and no code-evidence correction is credited with
resolving it.

## Result and next bounded work

The three possibilities are separated with positive evidence:

1. **Not fetched:** the normal provider-generation, tool-call extraction and
   result-memory passages are indexed below the within-artifact top-three cut.
2. **Fetched but discarded:** exact `main` and the full CLI method passage
   survive count/authority selection but do not fit the remaining byte cap.
3. **Delivered but misunderstood:** the candidate attributes the delivered
   agent dispatch to the LLM; complete-loop misunderstanding under complete
   delivery remains untested.

The immediate engineering question is therefore passage coverage for a named
implementation under the existing caps, followed by an independently scored
grounding check using the context actually delivered. Any corrective proposal
should preserve the overview/source-authority gates and separately demonstrate
the normal loop's provider, response, dispatch and feedback obligations; merely
retaining a canonical method ID will not satisfy them. Exact-source priority
currently treats the explicit `#main` request as a file-path group, so module
passages can precede the precise method. This is a measured ordering concern,
not an implemented priority change or proof that reordering alone solves the loop.

Validation: observer identity/deep-copy test passed; Ruff and Pyright passed for
the diagnostic runner/test. Both unchanged live replays completed on matching
ready generations and stable upstream versions. The audit checks all 36 tracked
chunk states, exact capacity accounting, source hashes, and the generation body.
Runtime candidate files remain byte-for-byte unchanged. The failed answer gate
and independent C1 defect remain open under #254; held-out #243 evaluation
is deferred.
