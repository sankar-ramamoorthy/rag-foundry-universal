---
title: "#375 source-navigation agent diagnostic on the revealed mealie questions"
date: 2026-11-15
type: test-results
status: current
summary: "Development diagnostic, one bounded run. A capable hosted model (claude-fable-5-2) with only file listing, search and file reading answered the three #359-H mealie questions from a plain checkout at 1624c22. Its cited, mechanically verified relationships covered every expected witness under the lenient rule (core 16/16, 17/17, 14/14; supporting 10/10) and all but the route-decorator witness under the strict rule (15/16, 16/17, 13/14). The #359 graph selector supported 2/16, 2/17 and 5/14 core with the correct handler supplied. Each question took about four minutes, 31 to 38 source-navigation calls and roughly 100K fresh input tokens. Not held-out evidence: the expected chains were already revealed, mealie is public, and forward traces favour source navigation."
tags: [evaluation, results, code-intelligence, agent, source-navigation, development-diagnostic, issue-375, issue-359, issue-207]
related:
  - "[Issue #375](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/375)"
  - "[#359 held-out mealie results](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md)"
  - "[#359 final report and recommendation](/DOCS/test_results/2026-11-14-359-final-report-and-recommendation.md)"
  - "[Issue #207 (deferred agentic investigator)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/207)"
  - "[Issue #373 (graph completeness protocol)](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/373)"
  - "[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #375 source-navigation agent diagnostic on `mealie`

**Evidence class: development diagnostic (ADR-054).** The `mealie` expected
chains were revealed under #359, so this is not a held-out result and
supports no generalization claim. No product code, extractor, retrieval or
configuration was changed.

## 1. Result

| Question | #359 graph selector, correct handler supplied (core) | Agent, strict (core) | Agent, lenient (core) | Agent, supporting |
|---|---:|---:|---:|---:|
| H-1 `POST /api/users/forgot-password` | 2/16 | 15/16 | 16/16 | 4/4 |
| H-2 `POST /api/users/reset-password` | 2/17 | 16/17 | 17/17 | 3/3 |
| H-3 `GET /api/recipes/{slug}/exports` | 5/14 | 13/14 | 14/14 | 3/3 |

- The #359 column is the ORACLE-ENTRY score, which was identical in all 16
  cells per question. The #359 end-to-end result was 0/3, because no public
  route resolved. The #359 selector supported 0 supporting witnesses.
- The agent was given the public route only. It composed the public path
  itself in all three cases (`/api` from `mealie/routes/__init__.py`, then
  the `users` or `recipes` prefix, then the decorator path), including the
  class-based controller in H-3.
- All 270 cited relationships (102, 73, 95) had quotes that were found in
  the checkout file they named. None was unverified.
- The single strict miss per question is the same witness, R1, the route
  decorator. The agent cited the decorator line with caller `<module>` or
  the controller class, since a decorator sits outside the function body.
  The scoring rule was not changed after seeing this; both figures are
  reported.

## 2. Method

- **Corpus:** `sankar-ramamoorthy/mealie` at `1624c22`, a plain `git`
  checkout outside this repository.
- **Agent:** one fresh Claude Code subagent per question, model
  `claude-fable-5-2`, with no conversation history.
- **Tools:** Glob, Grep and Read on the checkout, plus writing the answer
  file. No graph, RAG service, web access or code execution.
- **Questions:** the three #359-H questions verbatim, plus one added
  sentence asking how the public URL path is composed.
- **Prompt guidance:** follow each call to its real definition, including
  through injected dependencies, attributes, base classes and callbacks; one
  relationship entry per call site; quotes copied exactly.
- **Output:** a prose answer and a list of caller-to-callee relationships
  with file, function, line and quoted source.
- **Scoring:** `scripts/agent_navigation_score_375.py` against
  `DOCS/evaluations/359-H/expected-chains.json`.
  - A relationship counts only if its quote is present in the named file.
  - Strict: caller file and function match, and the quote matches the
    witness regex.
  - Lenient: caller file matches, and the quote matches the regex or the
    cited line is the witness line.

**Isolation.** The agents were told to stay inside the checkout; there was
no sandbox. The three transcripts were then checked mechanically: every
Glob, Grep and Read call named a path inside the checkout, and the only
writes were to the answer file. One H-2 search result was spilled by the
harness to a file outside the checkout; the agent reported that it did not
open it, and the transcript shows no read of it.

## 3. Cost and latency

| Question | Wall time | Navigation calls | Fresh input tokens | Cached input re-reads | Output tokens |
|---|---:|---:|---:|---:|---:|
| H-1 | 242 s | 38 | 103,191 | 490,313 | 29,781 |
| H-2 | 205 s | 31 | 95,828 | 430,537 | 25,360 |
| H-3 | 235 s | 34 | 114,838 | 544,837 | 27,672 |

- Token counts come from the subagent transcripts. Fresh input includes the
  harness's own system prompt and tool definitions, so it overstates what a
  minimal purpose-built loop would send.
- No price is stated: this ran inside a subscription session, not a metered
  API. Cost on a pay-as-you-go model is unmeasured.
- For scale, #359 computed a minimum ideal evidence size of 4 to 6 KB per
  question. The agent read far more source than that to find it.

## 4. What was not checked

- **Prose answers were not graded.** Witness coverage is mechanical. The
  written explanations (early-exit behaviour, demo mode, cleanup) were not
  verified claim by claim against the source.
- **Callee attribution differs in four constructor witnesses.** Where the
  expected chain names a class (`RepositoryUsers`, `RepositoryRecipes`,
  `DefaultEmailSender`), the agent named the inherited `__init__` that
  runs. These count as supported because scoring is on the caller-scoped
  witness, as in #359.
- **Extra relationships were not graded.** The agent cited about five times
  as many relationships as the expected chains contain. Their quotes are
  real, but whether each is on the execution path was not assessed.

## 5. Limits

- Three questions in one repository; H-1 and H-2 share helpers.
- `mealie` is public and may be in the model's training data. The verified
  quotes and line numbers show the agent read the pinned source, but
  familiarity may have made navigation faster.
- One model, one run per question. Run-to-run variance is unknown.
- This is the top of the capability range. Whether a cheaper hosted model
  or a locally hosted one reaches the same coverage is not known.
- An agent answer and #359's bounded evidence selection are different
  objects. #359 delivered at most 16 KB of evidence deterministically in
  one pass; the agent used minutes and several hundred thousand tokens.
- Forward-trace questions favour source navigation. Reverse and global
  questions (callers of a function, change impact, route inventory), where
  an index should help most, were not tested.

## 6. What this does and does not establish

**Established for these three questions:** the evidence #359's selector
could not reach is reachable by a capable model using search and file reads
alone, including the cases #359 lost to missing route prefixes, the
class-based controller, `bg_tasks.add_task`, injected services and
`self.*` receivers.

**Not established:** that an agent should replace the graph, that this
holds on an unseen repository, that it holds for cheaper models, or that
the cost is acceptable for everyday queries.

## 7. Suggested next steps (not authorized by #375)

1. **Model ladder.** Run the same three questions and scorer through a
   minimal tool loop on two or three cheaper models through LiteLLM, to find
   the least capable tier that still passes and its metered cost.
2. **Questions that should favour the graph.** Add reverse and global
   questions with source-derived answers, and compare agent alone, graph
   alone, and agent with graph tools.
3. **Off-the-shelf resolver check.** Point Jedi or Pyright definition
   lookup at the call sites #359 left unresolved, as a comparator for #373.
4. **Fresh repository.** Any generalization claim needs a newly sealed
   held-out repository under ADR-054.

#373 stays paused with its protocol frozen until the owner decides.
