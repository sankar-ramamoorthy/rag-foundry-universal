---
title: "#377 model ladder for source-navigation answers: cost of a correct, well-supported answer"
date: 2026-11-15
type: test-results
status: current
summary: "Development diagnostic. Six model tiers answered the three revealed #359-H mealie questions with only source search and file reads; 27 answers were scored mechanically for evidence support and graded blind for correctness against a rubric committed beforehand. Fable 5.2 and Opus 5.5 passed 3/3 (one run each). Sonnet 5.5 and Haiku 5.5 passed 4/6: all 12 answers were correct in prose with no material false statement, and the four failures left two or three core witnesses uncited on one question. Gemini 3.5 Flash-Lite passed 0/3 on incomplete evidence without false statements. GLM 4.7 Flash (free) passed 1/6 and made material false statements in three answers. Estimated cost per passing answer: Haiku about $0.06, Sonnet about $0.50, Opus about $1.21, Fable about $2.25 (list-price estimates, not metered). Gemini 3.8 Flash could not be measured on the free-tier quota. Addendum (section 9): on NEAR AI Cloud at published rates, Qwen 3.8 27B passed 4 of 6 attempts with all five written answers correct, at about $0.08 per passing answer but eight and a half minutes each; GLM 5.3 Flash and DeepSeek V4.1 Flash each passed 1 of 3 answers. Not held-out evidence; the Claude tiers and the other models ran in different harnesses."
tags: [evaluation, results, code-intelligence, agent, source-navigation, model-ladder, cost, development-diagnostic, issue-377, issue-375, issue-359]
related:
  - "[Issue #377](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/377)"
  - "[#375 source-navigation agent diagnostic](/DOCS/test_results/2026-11-15-375-source-navigation-agent-diagnostic.md)"
  - "[#377 correctness rubric and pass bar](/DOCS/evaluations/377-agent-ladder/rubric.json)"
  - "[#359 held-out mealie results](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #377 model ladder: what a correct, well-supported answer costs

**Evidence class: development diagnostic (ADR-054).** The `mealie` expected
chains were revealed under #359. Nothing here is held-out, and no product
code, extractor, retrieval or configuration was changed.

The question is not which model is cheapest at reaching the witnesses. It is
what one **correct and well-supported** answer costs per tier, counting the
attempts that fall short.

## 1. Result

| Tier | Model | Answers | Pass | Correct in prose | Mean time | Mean cost per answer | Cost per passing answer |
|---|---|---:|---:|---:|---:|---:|---:|
| Fable | `claude-fable-5-2` | 3 | 3 | 3 | 227 s | $2.25 | $2.25 |
| Opus | `claude-opus-5-5` | 3 | 3 | 3 | 178 s | $1.21 | $1.21 |
| Sonnet | `claude-sonnet-5-5` | 6 | 4 | 6 | 84 s | $0.33 | $0.50 |
| Haiku | `claude-haiku-5-5` | 6 | 4 | 6 | 161 s | $0.040 | $0.061 |
| Gemini Flash-Lite | `gemini-3.5-flash-lite` | 3 | 0 | 2 | 109 s | $0.027 | no pass |
| GLM Flash | `glm-4.7-flash` | 6 | 1 | 3 | 225 s | $0 (free tier) | $0 |

- **Pass** is the bar fixed in #377 before any run (§2).
- **Correct in prose** means the written answer alone met the bar: no
  contradicted rubric claim, no material false statement, and at least 90%
  of rubric claims stated. It ignores the evidence list.
- Costs for the four Claude tiers and Gemini are **list-price estimates
  from token counts**, not metered charges (§5). GLM was metered at zero.
- `gemini-3.8-flash` was attempted and could not be measured: the free-tier
  quota stopped every attempt before an answer (§6).

### What separates the tiers

- **Fable and Opus:** every claim correct, every core witness cited, every
  quote verified. One run per question each, so this says nothing about
  their variance.
- **Sonnet and Haiku:** all 12 written answers were correct, with no
  contradicted claim and no material false statement. All four failures
  are the same question, H-2, where the evidence list left out two or
  three core witnesses: a call inside `BcryptHasher.hash` in all four,
  and the token `SELECT` in three of the four.
  Both runs of both models missed there, so it is a repeatable gap, not
  noise.
- **Gemini Flash-Lite:** no false statement in any answer and every quote
  verified, but short answers with thin evidence (15/16, 11/17 and 10/14
  core witnesses) and one answer below the 90% claim threshold.
- **GLM Flash:** the only tier that was wrong, not just incomplete. Three
  of six answers contain material false statements, mostly about where a
  URL prefix comes from; H-3 was materially wrong in both runs. Up to a
  quarter of its quotes in one answer did not match the source. It also
  produced one clean pass, so its results swing widely between runs.

## 2. Method

- **Corpus and questions:** `mealie` at `1624c22`, the three #359-H
  questions, as in #375.
- **Tools:** file listing, search and file reading only.
- **Two harnesses.**
  - Claude tiers ran as Claude Code subagents with the #375 prompt
    (Glob, Grep, Read).
  - GLM and Gemini ran through `scripts/agent_navigation_ladder_377.py`, a
    minimal LiteLLM tool loop with equivalent tools, tool output capped at
    12,000 characters, and the answer returned through a `submit_answer`
    tool.
- **Runs:** two per question for Sonnet, Haiku and GLM; one for Fable (the
  #375 run), Opus and Gemini Flash-Lite. A second Opus and Fable run was
  dropped when the session's usage limit was reached.
- **Support (mechanical):** `scripts/agent_navigation_ladder_summary_377.py`
  reports witness coverage from the #375 scorer and the share of cited
  quotes found in the named file.
- **Correctness (graded):** a
  [rubric](/DOCS/evaluations/377-agent-ladder/rubric.json) of 11 or 12
  source-derived claims per question, committed at `69dc44f` before any
  answer was graded. Each claim is graded correct, missing or contradicted;
  material false statements outside the rubric are recorded separately.
- **Grading:** blind. Answers were stripped to prose, shuffled and labelled
  by `scripts/agent_navigation_grade_bundle_377.py`. A fresh
  `claude-fable-5-2` grader per question read the source and graded all
  answers to that question together, without the label key.
- **Pass bar (fixed in #377):** no contradicted claim, no material false
  statement, at least 90% of claims correct, every core witness supported
  under the lenient rule, and at least 95% of quotes verified.

## 3. Per-answer results

| Tier | Run | Q | Claims correct | Contradicted | Material false | Core witnesses | Quotes verified | Time (s) | Cost ($) | Bar |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| fable | 1 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 242 | 2.321 | pass |
| fable | 1 | H-2 | 11/11 | 0 | 0 | 17/17 | 100% | 205 | 2.059 | pass |
| fable | 1 | H-3 | 12/12 | 0 | 0 | 14/14 | 100% | 235 | 2.364 | pass |
| opus | 1 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 165 | 1.188 | pass |
| opus | 1 | H-2 | 11/11 | 0 | 0 | 17/17 | 100% | 173 | 1.145 | pass |
| opus | 1 | H-3 | 11/12 | 0 | 0 | 14/14 | 100% | 195 | 1.299 | pass |
| sonnet | 1 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 72 | 0.304 | pass |
| sonnet | 1 | H-2 | 11/11 | 0 | 0 | 15/17 | 100% | 72 | 0.303 | fail |
| sonnet | 1 | H-3 | 11/12 | 0 | 0 | 14/14 | 100% | 116 | 0.419 | pass |
| sonnet | 2 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 72 | 0.300 | pass |
| sonnet | 2 | H-2 | 11/11 | 0 | 0 | 14/17 | 100% | 73 | 0.305 | fail |
| sonnet | 2 | H-3 | 11/12 | 0 | 0 | 14/14 | 100% | 99 | 0.371 | pass |
| haiku | 1 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 131 | 0.033 | pass |
| haiku | 1 | H-2 | 11/11 | 0 | 0 | 15/17 | 100% | 171 | 0.044 | fail |
| haiku | 1 | H-3 | 12/12 | 0 | 0 | 14/14 | 100% | 171 | 0.043 | pass |
| haiku | 2 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 152 | 0.037 | pass |
| haiku | 2 | H-2 | 11/11 | 0 | 0 | 15/17 | 100% | 160 | 0.041 | fail |
| haiku | 2 | H-3 | 11/12 | 0 | 0 | 14/14 | 100% | 181 | 0.044 | pass |
| gemini-3.5-flash-lite | 1 | H-1 | 12/12 | 0 | 0 | 15/16 | 100% | 143 | 0.026 | fail |
| gemini-3.5-flash-lite | 1 | H-2 | 10/11 | 0 | 0 | 11/17 | 100% | 78 | 0.031 | fail |
| gemini-3.5-flash-lite | 1 | H-3 | 9/12 | 0 | 0 | 10/14 | 100% | 107 | 0.023 | fail |
| glm-4.7-flash | 1 | H-1 | 12/12 | 0 | 0 | 14/16 | 96% | 275 | 0 | fail |
| glm-4.7-flash | 1 | H-2 | 10/11 | 1 | 2 | 11/17 | 86% | 151 | 0 | fail |
| glm-4.7-flash | 1 | H-3 | 8/12 | 1 | 2 | 10/14 | 80% | 190 | 0 | fail |
| glm-4.7-flash | 2 | H-1 | 12/12 | 0 | 0 | 12/16 | 75% | 192 | 0 | fail |
| glm-4.7-flash | 2 | H-2 | 11/11 | 0 | 0 | 17/17 | 100% | 297 | 0 | pass |
| glm-4.7-flash | 2 | H-3 | 8/12 | 1 | 1 | 10/14 | 100% | 243 | 0 | fail |

The one rubric claim most answers missed is H-3 C11: on the error paths
nothing removes the temporary directory. Only the Fable answer and one
Haiku answer stated it. Missing it alone does not fail the bar.

## 4. How far to trust the grading

- **The grader is a model.** A `claude-fable-5-2` grader may share blind
  spots with the Claude tiers it graded, and its own answers were among
  those graded. Blinding hides identity, not style: the short GLM and
  Gemini answers are recognisable as a group.
- **Anchor check.** The second batch (Gemini) re-graded six first-batch
  answers unlabelled. Pass or fail agreed on all six. Claim-level counts
  agreed on four; on two GLM answers the graders split the same defects
  differently between "contradicted claim", "material" and "minor". Treat
  the pass column as stable and individual counts as plus or minus one.
- **Lenient partial credit.** The graders marked a claim correct when its
  main assertion was stated and a secondary clause was not. They listed
  these cases; they fall mostly on the GLM and Gemini answers. A stricter
  reading would lower those two tiers further and leave the Claude tiers
  about where they are.
- **Not human-checked.** No person has reviewed the grades. The grader
  notes are kept with the raw records for that review.

## 5. Cost and latency notes

- **Claude tiers are estimates.** Tokens come from the subagent
  transcripts and are priced at Anthropic list prices per million tokens
  (input / output): Fable $8 / $40, Opus $4 / $20, Sonnet $2 / $10, Haiku
  $0.10 / $0.50. Cache writes are taken as 1.25 times input; cache reads
  as $0.20, $0.20 and $0.10 for Fable, Opus and Sonnet.
- **Haiku's cache-read price is assumed** at a tenth of its input price;
  the reference used does not list it.
- **Caching matters.** The harness re-read a cached prompt on every step.
  Priced without prompt caching, the same runs would cost roughly 2.5 to
  3.5 times more.
- **The Claude Code harness inflates input.** Its own system prompt and
  tool definitions are in every request. A purpose-built loop would send
  less.
- **Gemini's figure is LiteLLM's list-price estimate.** The free tier
  billed nothing.
- **Free tiers were rate limited.** GLM and Gemini times include retry
  back-off (several retries per run), so they overstate model latency.
- **Opus timing is uncertain.** The three Opus runs were interrupted by
  the usage limit after 13 to 15 navigation calls and resumed in the same
  transcript. The times shown are what the harness reported for the
  resumed run and may leave out the time before the interruption.
- **Navigation effort differs by tier.** Mean search-and-read calls per
  answer: Haiku 35, Fable 34, Opus 30, Sonnet 20, GLM 37, Gemini 16.

## 6. Deviations and incomplete runs

- **One Sonnet run broke the tool rule.** Sonnet run 1 on H-3 used a shell
  and a helper script to write and self-check its answer file. It read
  nothing outside the checkout. Its result is kept and flagged.
- **`gemini-3.8-flash` not measured.** Three parallel attempts timed out
  after 6 to 8 model calls in nine minutes, and a solo retry of one
  question ended on a quota error. This is a free-tier limit, not a capability result.
- **Isolation.** Every Claude-tier search and read call named a path inside
  the checkout (checked mechanically from the transcripts). The LiteLLM
  runner confines its tools to the checkout in code.
- **GLM's strict witness score is zero** because it rarely filled the
  caller-function field. The bar uses the lenient rule, so this does not
  change any pass or fail.

## 7. Limits

- Three forward-trace questions in one public repository; H-1 and H-2
  share helpers. Not held-out.
- One to two runs per cell. Pass rates are indicative, not estimates of a
  population rate.
- **Harness is confounded with model family.** Claude tiers ran in Claude
  Code; GLM and Gemini ran in a minimal loop with a different prompt
  wrapper and capped tool output. The gap between families mixes model and
  harness.
- The pass bar is demanding by design. "Every core witness" turns a
  correct answer with two uncited leaf calls into a fail.
- No locally hosted model was run. Section 9 adds a hosted 27B open
  model, which is a proxy for model capability only.
- Reverse and global questions (callers, impact, route inventory), where
  an index should help most, are still untested.

## 8. What this suggests (not authorized by #377)

1. **Correct prose is cheap; complete evidence is what costs.** Haiku
   wrote a correct answer every time for about four cents. The premium
   tiers bought exhaustive citation of the path, at 30 to 55 times the
   price.
2. **The evidence gap is specific and may be closable without a bigger
   model.** The cheaper Claude tiers skipped leaf calls inside functions
   they had already opened. A second "list every call in the functions you
   cited" pass, or a graph tool that lists a function's call sites, are
   two candidate fixes. The second is a concrete job for the graph.
3. **Free does not mean usable.** GLM 4.7 Flash was wrong in half its
   answers and inconsistent between runs. For this task a cheap paid model
   beats a free one.
4. **Next measurements, in order of value:**
   - run the Claude tiers through the LiteLLM runner, for one harness
     across all models and a metered price;
   - a paid Gemini Flash and one mid-priced open model;
   - the evidence-completion pass on Haiku;
   - reverse and global questions, with and without graph tools;
   - a locally hosted model on a larger machine.
5. Any generalization claim still needs a fresh sealed repository
   (ADR-054). #373 stays paused pending the owner's decision.

## 9. Addendum: three low-cost hosted open models (NEAR AI Cloud)

Run later the same day, in the LiteLLM runner (the same harness as GLM 4.7
Flash and Gemini), against NEAR AI Cloud's OpenAI-compatible endpoint. Costs
here are **token counts at the provider's published pay-as-you-go rates**,
so they are closer to a metered price than the Claude estimates above. The
provider's invoice was not checked.

| Model | Rate in / out per 1M | Attempts | Answers | Pass | Correct in prose | Mean time | Mean cost per answer | Cost per passing answer |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `Qwen/Qwen3.8-27B` | $0.04 / $1.35 | 6 | 5 | 4 | 5 | 513 s | $0.056 | $0.079 |
| `z-ai/glm-5.3-flash` | $0.08 / $0.50 | 6 | 3 | 1 | 3 | 508 s | $0.045 | $0.249 |
| `deepseek-ai/DeepSeek-V4.1-Flash-1017` | $0.30 / $1.20 | 3 | 3 | 1 | 2 | 438 s | $0.224 | $0.673 |

"Cost per passing answer" counts every attempt, including those that
returned no answer. Total spend for this addendum: $1.24 at published rates.

| Model | Run | Q | Claims correct | Contradicted | Material false | Core witnesses | Quotes verified | Time (s) | Cost ($) | Bar |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| qwen-3.8-27b | 1 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 497 | 0.051 | pass |
| qwen-3.8-27b | 1 | H-2 | 11/11 | 0 | 0 | 15/17 | 100% | 491 | 0.046 | fail |
| qwen-3.8-27b | 1 | H-3 | 12/12 | 0 | 0 | 14/14 | 100% | 632 | 0.073 | pass |
| qwen-3.8-27b | 2 | H-1 | no answer | | | | | 906 | 0.034 | fail |
| qwen-3.8-27b | 2 | H-2 | 11/11 | 0 | 0 | 17/17 | 100% | 464 | 0.047 | pass |
| qwen-3.8-27b | 2 | H-3 | 12/12 | 0 | 0 | 14/14 | 100% | 480 | 0.064 | pass |
| glm-5.3-flash | 1 | H-1 | 12/12 | 0 | 0 | 15/16 | 100% | 349 | 0.030 | fail |
| glm-5.3-flash | 1 | H-2 | 11/11 | 0 | 0 | 15/17 | 100% | 723 | 0.045 | fail |
| glm-5.3-flash | 1 | H-3 | 11/12 | 0 | 0 | 14/14 | 100% | 453 | 0.061 | pass |
| deepseek-v4.1-flash | 1 | H-1 | 12/12 | 0 | 0 | 16/16 | 100% | 516 | 0.194 | pass |
| deepseek-v4.1-flash | 1 | H-2 | 11/11 | 0 | 0 | 16/17 | 100% | 310 | 0.229 | fail |
| deepseek-v4.1-flash | 1 | H-3 | 12/12 | 0 | 1 | 14/14 | 100% | 487 | 0.250 | fail |

### Reading

- **Qwen 3.8 27B matches Haiku 5.5 on quality at a similar price.** Five
  of five written answers were correct with no false statement, four met
  the full bar, and every quote verified. Its one evidence miss is the
  same H-2 pattern the cheaper Claude tiers showed.
- **It is slow here.** About eight and a half minutes per answer on this
  provider, against under three for Haiku, and one of six attempts stalled
  past its time cap with no answer.
- **A 27B model reaching this level bears on local hosting.** It is the
  size class a well-equipped desktop can run. This run says nothing about
  local speed, quantisation loss or context limits, which need their own
  measurement.
- **GLM 5.3 Flash was correct but incomplete, and needed a longer cap.**
  Its first three attempts hit the 520-second cap while still exploring
  and returned nothing; they are the three no-answer attempts in its
  count. Re-run with a 1,200-second cap it answered all three, correct in
  prose, with one or two core witnesses uncited on two questions.
- **DeepSeek V4.1 Flash cited the most and cost the most of the three.**
  One answer invented a "periodic purge task" for the temporary directory
  that does not exist in the source, which is a material false statement.
- **All three were far better than the free GLM 4.7 Flash and Gemini
  Flash-Lite in the same harness**, which weakens the worry in section 7
  that the minimal loop itself was holding those two back.

### Limits specific to this addendum

- One or two runs per question; the Qwen pass rate rests on six attempts.
- Time caps differed: 520 to 560 seconds for Qwen and DeepSeek, 1,200
  seconds for the GLM 5.3 Flash re-run. Three questions ran in parallel
  per model, so times include any provider-side queueing.
- Graded in a third blind batch by the same kind of grader. The six anchor
  answers again agreed with the first batch on pass or fail, six of six.
- Kimi K2.6, GLM 5.3 and Kimi K3 were not run, to stay inside a $2 limit.
