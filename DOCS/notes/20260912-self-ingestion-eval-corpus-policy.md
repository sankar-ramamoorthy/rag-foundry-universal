# Decision: self-ingestion is fine for engineering checks, not for answer-quality claims (2026-09-12)

Status: decided. Closes issue #106. No code or ingestion-behavior change — this is a process rule,
not a technical fix.

## Decision

Self-ingesting `rag-foundry-universal` into itself remains fine, and is still encouraged, for:

- engineering smoke tests (does `/v1/rag` respond, does ingestion complete, does a known-good query
  return *something*),
- retrieval-mechanics debugging (does the evidence trace fire, does the `MAX_EXPANDED_DOCS` cap
  behave as expected, does a chunk get fetched) — anything checking **how** retrieval behaves.

Self-ingesting this repo must **not** be used to make **answer-quality claims** — grading whether a
generated answer is factually correct — for any question whose expected answer is written down
anywhere in the corpus being queried. This is the narrow rule: the prohibition is on grading
correctness against a contaminated corpus, not on self-ingestion itself.

## Why

WP-T1e's first live evidence-survival run (`DOCS/test_results/2026-09-12-wp-t1e-evidence-survival-run.md`,
filed as issue #106) found that `DOCS/evaluations/2026-09-07-evidence-survival-question-set.md` — the
document recording every frozen candidate's exact expected answer — is itself part of this repo's
ingested corpus, and was retrieved as a source for 6 of the 7 Python-repo candidates in that run.
`DOCS/audit/2026-09-07-current-state-retrieval-audit.md`, which restates several candidates'
reasoning, was retrieved for 3 of them as well. A correct-looking answer in that run could be the
model deriving it from real source, or echoing the leaked expected-answer text verbatim — the two
are indistinguishable from the answer text alone, which invalidated answer-quality grading for
those candidates. This is the same failure mode `DOCS/audit/00-Audit-Overview.md`'s 2026-08-30
status entry already recorded once for `DOCS/test_results/*.md`; it now also applies to
`DOCS/evaluations/` and to audit docs that restate expected answers.

## What this rules out, and what it doesn't

**Ruled out:** self-ingesting this repo and then grading generated answers against a frozen
question set whose expected answers (or close paraphrases of them) live anywhere in the ingested
tree.

**Not ruled out:**
- Self-ingesting this repo for anything that only checks retrieval mechanics (trace fields, cap
  behavior, chunk counts, whether a specific canonical_id was found) — the evidence-trace fields
  WP-T1a-d added are unaffected by this kind of textual contamination, since they measure
  document/rank/cap survival, not answer wording.
- Future evidence-survival/answer-quality evaluations against a genuinely different, uncontaminated
  repo — exactly what the TradeForge candidate in the same WP-T1e run already did successfully.
- Writing new audit/evaluation docs under `DOCS/` in general. The rule is specific to documents that
  state expected answers for a live or future question set, not to audit/documentation content
  broadly.

## Explicitly deferred, not part of this decision

A reusable ingestion-time path-exclusion mechanism (e.g. `.ragignore`-style patterns to keep
specific paths out of self-ingestion) was considered and explicitly **not** built here — this
decision is a process rule, not new tooling. If that capability becomes independently useful later
(vendored code, generated files, or a future need to exclude answer-key docs from ingestion rather
than avoid grading against them), it should be scoped and filed as its own issue at that time.

## How to apply this going forward

- Before grading any future evidence-survival run's answers, check whether the frozen question
  set's own expected-answer text (or a doc restating it) is retrievable from the corpus being
  queried. If it is, either run against a different repo, or grade only the mechanical
  evidence-trace fields (which stay trustworthy) and flag answer-quality verdicts as unreliable —
  exactly as `DOCS/test_results/2026-09-12-wp-t1e-evidence-survival-run.md` already did for the
  affected candidates in that run.
- This repo is re-ingested nightly on the production instance (per
  `DOCS/notes/20260906-nightly-repo-ingestion-decision.md`), so any answer-key document committed
  under `DOCS/` will be back in the corpus by the next re-ingestion regardless of when it was
  written — there is no "temporarily uncommitted" workaround once nightly re-ingestion is running.
