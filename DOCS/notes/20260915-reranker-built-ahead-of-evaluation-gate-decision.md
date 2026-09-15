# Decision: build the optional reranker before re-running the evaluation gate (2026-09-15)

Status: decided and implemented (issue #152). Off by default; no
production behavior change from this decision alone.

## Decision

Built WP-S8's flag-gated cross-encoder reranker (`RERANK_ENABLED`,
default `False`) now, rather than waiting for a fresh evaluation pass
to first confirm rank-8-20 failures are the dominant pattern, as
`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §4 and the WP-S8
callout in `DOCS/audit/04-Scalability-Plan.md` both say to do.

## Why this isn't just skipping the gate

The gate exists to stop a reranker from being built and defaulted-on
on vibes ("answers feel better") instead of evidence. This decision
doesn't do that:

- The reranker's *default* stays off. Nothing about today's production
  behavior changes as a result of this work landing.
- The stated reason for building now: comparing reranker-on vs.
  reranker-off requires having a working "on" arm to compare against.
  Per-request override (`RAGQuery.rerank` / `SimpleRAGQuery.rerank`)
  means the same deployment can serve both arms of an A/B comparison
  without a redeploy — building the infrastructure is a precondition
  for gathering the evidence the gate asks for, not a substitute for
  it.
- Same shape as the `DOC_TYPE_TIE_BREAK_ENABLED` precedent (issue
  #142): ship flag-gated, evaluate live, only then consider flipping
  the default. That feature is still `investigate` in the decision
  gates, not `validated`, despite being merged and deployed — merging
  code and validating a default are different steps, and this decision
  keeps that separation for the reranker too.

## What triggered this, concretely

During TradeForge multi-model retrieval testing (2026-09-15), a
candidate (`handleRequestFundamentals`, issue #149) looked at first
like reranker territory — genuinely relevant code that some generators
answered incorrectly about. Investigating it live surfaced issue #150
instead (an HNSW post-filter under-recall bug: the chunk wasn't merely
ranked low, it usually wasn't being retrieved into the candidate pool
at all). That's a different problem with a different, already-shipped
fix (`DOCS/test_results/2026-09-15-hnsw-iterative-scan-issue-150.md`).

This raised the real open question directly: once #150's fix is live,
does *any* meaningful rank-8-20 pattern remain, or was #150 the whole
story? Answering that well requires a real on/off comparison, not
inference from one query's raw-rank number — hence building the
reranker now, evaluating properly once #150 is deployed.

## What's not decided here

Whether the reranker actually helps, whether `RERANK_ENABLED` should
ever default to `True`, and which model (`RERANK_MODEL`) is the right
choice long-term are all open, pending the evaluation in issue #152's
follow-up steps. This note records only the decision to build ahead of
that evidence, and why that's a considered choice rather than a
process shortcut.

## Related

- [Issue #152](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/152) — the reranker implementation.
- [Issue #150](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/150) — the HNSW recall fix that changed the evidence picture.
- [Issue #149](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/149) — the finding that triggered this whole thread.
- `DOCS/audit/09-Retrieval-Technique-Decision-Gates.md` — the reranker's row, updated 2026-09-15 to reference this context.
