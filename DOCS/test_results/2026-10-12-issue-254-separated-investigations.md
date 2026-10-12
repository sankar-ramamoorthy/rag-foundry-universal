---
title: "Issue #254: automatic coverage and frozen-evidence grounding"
date: 2026-10-12
type: test-result
status: complete-gates-failed
tags: [issue-254, behavioral-completeness, evidence-selection, answer-grounding]
related:
  - "[Fixed-cap evidence experiment](/DOCS/test_results/2026-10-12-issue-254-complete-evidence-experiment.md)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #254: automatic coverage and frozen-evidence grounding

Two separate development-corpus investigations preserve the unmerged candidate
and the 4096-byte retrieved-evidence allowance. Neither changes runtime retrieval,
classification, chunk counts, model configuration or deployed services.

## Automatic selection, without oracle line ranges

The [offline selector](/scripts/issue254_automatic_coverage_eval.py) receives
the exact R1 question and the three full pinned Python source snapshots. It
resolves the explicitly named symbols with Python AST, creates literal leaf
statement/control-header spans, seeds them by query/identifier lexical overlap,
and follows nearest preceding local definitions. It gives unrepresented named
owners priority, then greedily selects by utility per marginal UTF-8 byte.
The implementation was fixed before running selection; no answer, oracle
range, transition rubric, or manual source span is an input to `select`.
The [frozen selection](/DOCS/test_results/2026-10-12-issue-254-automatic-coverage.json)
records algorithm hash, accepted/rejected seeds, literal manifests and bytes.
No post-result selector revision or second attempt is included.

This is a deliberately small Python-only research spike, not a proposed
production policy. It assumes access to complete pinned source. It does not
prove that live retrieval's three-chunk pool contains these spans, acquire source
automatically through the application, or generalize to other repositories.

The output costs **3952 bytes**, leaving **144 bytes**. Inspection finds
the normal user-memory append, provider acquisition and `generate` arguments,
returned tool-call/name/args extraction, and lookup plus `tool.run(**args)`.
It omits the role-tool memory append and next-iteration `continue`, the
assistant tool-call record, `Agent(...)` construction and `start_cli(agent)`.
Thus **4/5 primary statement witnesses are present**, but the complete-flow
gate fails. Repeated labels, dynamic-tool startup, special-command and logging
statements consume space while feedback is rejected. Source-owner diversity
does not establish the correct startup handoff.
The feedback append seed at pinned line 753 requires a **4236-byte** trial
context when considered; the assistant record at line 723 requires **4608**,
and the constructor at line 138 requires **4296**. These are recorded marginal
selection failures, not evidence that those passages cannot fit together under
the cap: the earlier manual oracle already demonstrates that they can.

There is an additional relationship failure: literal AST headers alone do not
preserve `else` provenance. For example, the selected `if not tool` error branch
and the later `try: result = tool.run(**args)` occupy separate fragments without
the intervening `else`. Nearest preceding assignment is also not a sound
branch-sensitive reaching-definition analysis. These fragments are source
excerpts, not a valid standalone program or a certified execution path.
They are **not submitted to generation**. Local definition closure and lexical
byte utility cannot be credited as automatic behavioral completeness.

The two selector checks cover source-line relocation with unchanged selected
text and exact UTF-8 budget rejection without statement truncation. Their
passing results validate these mechanics, not behavioral coverage.

## Grounding with frozen evidence

The [grounding runner](/scripts/issue254_grounding_contract_eval.py) freezes
three counterbalanced pairs before generation: frozen/contract,
contract/frozen, frozen/contract. Both arms use the exact earlier 4024-byte
evidence, original question, 3081-byte policy/inventory envelope,
`ollama/Qwen3:4b`, `rag_answer.v1`, default stochastic generation and the same
pinned ready generation. The control is regenerated in each pair.

The only treatment is an additional answer-contract instruction before the
unchanged context. It requests ordered rows with implementing owner, canonical
source, exact operation/arguments, input/output state, handoff and literal quote;
it asks for startup and all five normal-flow transitions, distinguishes lookup
from execution, and requires unknown dependencies to be marked instead of
invented. It supplies no correct code expressions or missing initializer value.
This is a **prompt-size increase outside the retrieved-evidence cap**, explicitly
recorded in the raw payloads, not a claim of total-prompt-size equivalence.

The [raw grounding experiment](/DOCS/test_results/2026-10-12-issue-254-grounding-contract.json)
records all payloads, identities, generation checks and responses. The unchanged
five factual/five attribution obligations are scored separately. Literal quote
accuracy and unsupported memory-role assumptions are reviewed separately.
The memory initializer is still absent in both arms. This test can reveal
prompt sensitivity but cannot isolate model capability from unresolved state
dependencies or demonstrate that the source covers every dependency.

## Grounding results

All six calls completed with the frozen model/template and generation, without
fallback. The contract adds **1089 UTF-8 bytes** outside retrieved evidence;
full context sizes are **7105** control and **8194** treatment bytes. The
[integrity audit](/DOCS/test_results/2026-10-12-issue-254-separated-audit.json)
verifies exact evidence suffixes, question, scoring, source manifests,
generation before/after each request and unchanged candidate runtime hashes.
Runtime identity remains HTTP self-report, not independent image attestation.

The [manual score record](/DOCS/test_results/2026-10-12-issue-254-grounding-scores.json)
binds judgments to exact response hashes. Component attribution is distinct
from mechanics and canonical/literal citation accuracy. A correct component
can receive attribution credit while its invented call or rewritten quotation
fails factual or citation review. These are the same obligation axes as the
previous experiment; the controls here are new concurrent responses.

| Pair / arm | Factual / 5 | Actor attribution / 5 | Full loop |
| --- | --- | --- | --- |
| 1 / frozen | 3 | 3 | F |
| 1 / contract | 2 | 3 | F |
| 2 / contract | 0 | 2 | F |
| 2 / frozen | 2 | 3 | F |
| 3 / frozen | 2 | 3 | F |
| 3 / contract | 2 | 3 | F |
| **Frozen total** | **7/15** | **9/15** | **0/3** |
| **Contract total** | **4/15** | **8/15** | **0/3** |

The tested contract does **not** improve the scored requirements. All three
treatments use the requested table shape, yet all omit `main`, active-provider
acquisition and complete name/args extraction. Two reproduce provider arguments
or `tool.run`, but fail the complete respective obligation. The first invents
`self.llm.generate(messages)` and `tool.execute(tool_call)`; the third adds
unobserved helper-like handoff names and replaces the canonical assistant record
with `[tool_call]`. Literal quotation and precise canonical attribution remain
unreliable. Table compliance is not source compliance.

Normal user-role memory and role-tool feedback each pass **3/3** controls and
**2/3** treatments; the second treatment omits the roles. None of the six
answers repeats the earlier incorrect memory-slice role inference, but **0/3
in either arm** identify the missing initializer as unknown. The absence of
that earlier error in both arms provides no contract-specific improvement.
Three stochastic pairs on one development question support only this bounded
observation, not statistical superiority or a universal verdict on answer
contracts. No model-capability ceiling or initializer-fix result is established.

## Decision and next boundary

Both investigations fail their gates. Automatic selection must preserve branch
and def-use relationships and select feedback/startup ahead of incidental
statements; this spike does not demonstrate those properties. The frozen-source
contract tested here fails to obtain a fully correct attributed explanation.
Further experiments should treat dependency completion and prompt structure as
separate variables, rather than attribute all residual errors to the model.
The existing 4096-byte fit remains established only by the manual oracle.

**#254 remains open; the candidate stays unmerged and undeployed; C1 stays a
separate historical-grounding defect; #243 remains deferred.** No new retrieval
heuristic, classification rule, global cap, production prompt or model change
is implemented. Local checks: five targeted experimental-helper tests pass;
Ruff and Pyright pass for the new scripts/test. These checks validate local
mechanics; the behavioral gates above fail.
