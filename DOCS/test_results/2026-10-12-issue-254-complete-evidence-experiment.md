---
title: "Issue #254: complete execution-flow evidence under the existing byte cap"
date: 2026-10-12
type: test-result
status: complete-with-partial-generation-improvement
tags: [issue-254, behavioral-completeness, evidence-selection, controlled-experiment]
related:
  - "[Loop completeness diagnosis](/DOCS/test_results/2026-10-12-issue-254-loop-evidence-completeness.md)"
  - "[Unmerged policy candidate](/DOCS/test_results/2026-10-12-issue-254-policy-candidate.md)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #254: complete execution-flow evidence under the existing byte cap

The offline evidence construction fits the requested normal execution flow
in **4024 UTF-8 bytes**, including source labels and separators. The existing
candidate's captured retrieved evidence uses **4061 bytes**. All six matched
generation requests completed. The complete-evidence answers correctly explain
user-memory and result-memory feedback in **3/3** runs versus **0/3** controls,
but **0/3** treatment answers satisfy every frozen factual and attribution
obligation. Evidence fit is established; fully correct and fully attributed
explanation is not.

## Frozen experiment

The [experiment runner](/scripts/issue254_complete_evidence_eval.py) freezes
both exact payloads, their hashes, source excerpts, question, model/prompt
identity, paired order and scoring before its first generation request.
The [raw experiment](/DOCS/test_results/2026-10-12-issue-254-complete-evidence-experiment.json)
persists responses after each request and fails closed on model, fallback,
prompt-template, runtime-version, source-byte or generation mismatch.

The control is the **exact captured candidate `/generate` payload**, reconstructed
and checked against the prior observed assembly. Its answer is regenerated
alongside the complete-evidence arm; this comparison does not reuse an old
answer as a concurrent control. The treatment replaces only that payload's
retrieved-evidence suffix with six source-faithful excerpts. The question,
policy/inventory envelope, LLM endpoint and system prompt remain unchanged.
Three fixed paired runs use candidate/complete, complete/candidate, then
candidate/complete order. No answer-conditioned edits, extra repeats or prompt
tuning are planned.

Model identity is `ollama/Qwen3:4b`, alias `default`, prompt template
`rag_answer.v1`, without fallback. The repository remains
`863e770d-651e-5bc5-83d1-a1409693e707`, ready generation
`24f827d7-a33b-45f7-93f4-ff6e5eaf3856`, source commit
`f854303e6e44ff95d94792d24868442a28080ba2`. The exact R1 question is:

> Using `py_mono/main.py#main`, `py_mono/ui/cli.py#start_cli`, and
> `py_mono/agent/agent.py#Agent.run`, trace a normal user prompt through a tool
> call and the tool result returning to the LLM.

The existing application's **4096-byte cap applies to retrieved evidence**.
Its captured policy/inventory envelope is another **3081 bytes**, unchanged
in both arms and outside that pre-existing cap. Full `/generate` context sizes
are therefore 7142 bytes for the control and 7105 for the treatment. This
does not increase the evidence allowance, silently remove the envelope, or
claim that the full prompt has historically been capped at 4096 bytes.

Source bytes are independently re-read from the pinned GitHub URLs before the
oracle is constructed. The excerpts preserve source lines and indentation,
without rewritten code or generated behavioral summaries. Each excerpt has
its canonical function label, source-line range and source/text hashes in the
manifest. Separate excerpt blocks mark noncontiguous selections; they are
not represented as a complete standalone function or an executable rewrite.

## Evidence and coverage

| Canonical source | Pinned lines | Labeled bytes | Obligation supplied |
| --- | --- | --- | --- |
| `py_mono/main.py#main` | 132-148 | 449 | Session manager/Agent construction and `start_cli(agent)` |
| `py_mono/ui/cli.py#start_cli` | 37-58 | 678 | Input reading and normal-path `agent.run(prompt)` |
| `py_mono/agent/agent.py#Agent.run` | 638-650 | 393 | User-role memory append, bounded step loop, active provider |
| `py_mono/agent/agent.py#Agent.run` | 675-702 | 905 | Messages include memory; provider invocation; response tool-call extraction/name/args/ID |
| `py_mono/agent/agent.py#Agent.run` | 723-738 | 654 | Assistant tool-call record with matching ID |
| `py_mono/agent/agent.py#Agent.run` | 740-764 | 935 | Agent dispatch, role-tool result memory update, prune condition, `continue` |

The six labels plus ten separator bytes total **4024**, leaving **72 bytes**
under the fixed cap. Nothing is truncated to fit. All five required primary
transitions are present: input/memory, provider invocation, tool-call extraction,
agent dispatch, and memory feedback to the next provider call. Startup and CLI
attribution, plus the assistant/tool-call ID relationship, are also available.
The excerpt selection deliberately scopes the **normal prompt-to-tool-result
flow**, not every special-command, playbook, repeated-call or final-answer branch.

The control retains startup/CLI handoffs and dispatch but lacks complete normal
input-memory, provider invocation, response extraction and result-feedback
evidence. Its partial method labels do not imply behavioral completeness.

## Scoring fixed before answers

Factual correctness and actor/source attribution are assessed separately.
Each axis has five binary obligations; omissions or contradictions score zero.
The complete loop requires **5/5 factual and 5/5 attribution**. Incorrect
extra claims are recorded rather than hidden by a high coverage score.

| Factual obligation | Correct fact |
| --- | --- |
| Input | Prompt passes into `run` and is appended as user-role memory. |
| Provider | Active provider generation receives messages/memory and tools. |
| Extraction | Name/arguments come from the returned `tool_call`, not direct prompt parsing. |
| Dispatch | Tool lookup and `tool.run(**args)` perform execution. |
| Feedback | Role-tool result enters memory; loop continues and the next generation uses that memory. |

Attribution obligations are: `main` constructs/starts; `start_cli` reads/passes
input while `Agent.run` owns memory; the provider produces the tool-call decision
while the agent extracts it; the agent executes the tool; the agent updates
result memory and invokes the provider again. Source-bound references to the
three functions are additionally judged for citation accuracy, separately from
correctly naming actors. Fabricated sources and misplaced claims are failures.

This is a manual oracle on development data. It tests whether source-faithful
selection can fit and whether this model explains the supplied normal flow.
It does not test automatic discovery/selection of those spans, certify a
retrieval policy, demonstrate reliability on unseen repositories, or resolve C1.
No production or candidate retrieval code is changed by this experiment.

## Results: coverage, facts and attribution are separate

Every required transition fits and appears in the treatment payload, with
its original source text and owner label. The control contains only one
complete primary witness, dispatch; it also contains partial input/CLI and
startup evidence. A source-label or partial-input hit is not counted as a
complete input-plus-memory witness.

The [manual scores](/DOCS/test_results/2026-10-12-issue-254-complete-evidence-scores.json)
bind each judgment to the answer's SHA-256 and give per-obligation decisions,
omissions/contradictions, and a separate citation review. Scores count fully
met requirements; **they are not the proportion of true sentences**. For
example, the concise second treatment answer correctly gives the high-level
memory feedback loop but omits provider invocation parameters and name/argument
extraction, so it does not receive full requirement coverage.

| Pair / arm | Factual obligations / 5 | Actor attribution / 5 | Full-loop gate |
| --- | --- | --- | --- |
| 1 / candidate | 1 | 1 | F |
| 1 / complete evidence | 2 | 3 | F |
| 2 / candidate | 1 | 1 | F |
| 2 / complete evidence | 2 | 2 | F |
| 3 / candidate | 0 | 1 | F |
| 3 / complete evidence | 3 | 3 | F |

Across the three runs, treatment meets **7/15 factual obligations versus 2/15**
and **8/15 attribution obligations versus 3/15**. Correct normal user-role
memory append and correct role-tool/next-iteration feedback each improve
from **0/3 to 3/3**. This is an observed within-experiment improvement, not
a statistically estimated reliability rate or a held-out generalization claim.

The control answers either invent raw-prompt-to-tool parsing/direct CLI return,
or infer feedback from conventional agent behavior without explaining the
current memory mechanism. One says the tool result is the only input returning
to the LLM, contrary to the retained message history. Another quotes altered
variable names as if they were verbatim implementation. Some explicit agent
dispatch attribution is correct and is credited even when other obligations fail.

All treatment answers mention user memory, tool-result memory, and the next
iteration using the result. The remaining defects are:

- All three omit a precise account of active-provider invocation with both
  messages/history and the tools argument, and of the agent explicitly reading
  the returned call's name/arguments. The third correctly shows those fields
  in returned `tool_call` JSON and receives factual provenance credit; it
  still omits the agent's extraction operation. The first two only describe
  a generic returned tool call.
- All three fail to describe `main`'s construction/startup ownership despite
  receiving its source. The third labels prompt-to-agent routing as coming
  from `main`, although that action is in `start_cli`.
- The first says `memory[1:]` excludes the initial user prompt. The pinned
  constructor actually initializes memory with a system message; the normal
  user message is then appended and remains in that slice. The slice statement
  is therefore wrong, even though the answer's broad feedback mechanism improves.
- The second leaves the tool's executor unnamed and does not distinguish
  lookup from invocation. The third cites `self.tools.get(...)` as an example
  of execution, conflating lookup with the subsequent `tool.run(**args)` call.

Source citations also remain imperfect. The first two treatment answers bind
their explanations to the CLI/agent files but omit `main`'s role; the third
provides exact canonical labels yet attaches `main` to a CLI operation.
Correct labels alone are not proof of correct actor/action attribution.

## Limits and architectural implication

The experiment answers the budget question positively: **source-faithful
selection can fit all requested normal-flow transition spans without raising
the existing cap**. It also shows why an increased fetch count is insufficient
evidence of useful coverage: the captured context occupies more bytes while
omitting the critical provider/response/feedback spans. No larger retrieval
volume was used in the model comparison.

This manual selection changes coverage, source granularity and ordering
together. It is an oracle upper-bound experiment on known development source,
not an automatic selection strategy or an isolated estimate of each factor's
effect. It does not require mechanically retaining whole existing stored chunks;
it uses verbatim line excerpts with provenance. Whether a future strategy can
discover and select these spans remains untested.

The oracle is complete for the five predeclared **transition witnesses**, not
every semantic dependency. In particular, it does not include the constructor's
initial system-memory assignment or all playbook/system-prompt construction.
The observed `memory[1:]` error makes that state dependency worth tracking.
The experiment does not prove that all remaining errors are solely a model
failure under a fully dependency-closed context. No context was revised after
seeing that error, and no additional tuned run was substituted for the frozen
six-call result.

Symbol retrieval and behavioral completeness are different contracts. A method
ID certifies discovery of an artifact; explaining a behavior requires witnesses
for the relevant transitions, their data/state dependencies, and correct
attribution of who performs them. Here transition coverage fits, but the model
still omits or misattributes parts of the explanation. A future proposal should
measure those obligations and delivered bytes rather than cite symbol survival
or total fetched volume as a success metric.

## Validation and disposition

The construction tests pass for overflow rejection and immutable replacement
of only the evidence suffix. Ruff and Pyright pass. The
[completion audit](/DOCS/test_results/2026-10-12-issue-254-complete-evidence-audit.json)
verifies six
unique planned requests, matching ready generation/source before and after,
identical question/envelope, unchanged model alias/template/runtime, no fallback,
exact source-range fidelity, both evidence byte counts, and all five treatment
transition witnesses. Both context payloads and every answer are retained for
review. This is a local controlled construction/generation experiment using
the same read-only deployed LLM endpoint; no deployment or ingestion occurred.

The policy candidate remains preserved, unmerged and undeployed. No retrieval
policy or prompt change is proposed as implemented by these results. #254's
end-to-end behavior gate and independent C1 grounding defect remain open;
#243 is still deferred.
