---
title: "Doc-Type Tie-Break: Evidence for Issue #141's Retrieval Failure and Issue #142's Fix"
date: 2026-09-14
type: test-result
status: partial
tags:
  - rag
  - evaluation
  - retrieval
  - ranking
  - self-ingestion
related:
  - "[Issue #141](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/141)"
  - "[Issue #142](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/142)"
  - "[Retrieval Technique Decision Gates](/DOCS/audit/09-Retrieval-Technique-Decision-Gates.md)"
  - "[RAG Quality Evaluation Methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)"
---

# Doc-Type Tie-Break: Evidence for Issue #141's Retrieval Failure and Issue #142's Fix

**Status: partial.** The failure mechanism below is confirmed live,
against a real production deployment, with direct database
verification. The fix (issue #142) is unit-tested but **not yet
re-verified live** against a deployment actually running it — this
repo's evaluation-gating discipline (Constitution Principle III/VIII,
`DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`) requires that
before `DOC_TYPE_TIE_BREAK_ENABLED`'s default flips to `True`. This
document will be updated in place once that live pass runs, per
`09-Retrieval-Technique-Decision-Gates.md`'s "update the row, don't
delete the record" convention — not superseded by a new dated file.

## The query

Against the `rag-foundry-universal` repo (`repo_id
f7641840-ba13-5f9d-9ae6-87e1f924709d`, ingested 2026-09-14, post-WP-L5),
via the production `/v1/rag` endpoint over Tailscale
(`http://100.105.24.12:8004`):

> In `ingestion_service/src/core/extractors/treesitter/base.py`, why are
> `_language_for`, `_parser_for`, and `_compiled_query` all wrapped in
> `@lru_cache`, and what would happen on every file parsed if that
> caching were removed?

This is Candidate 1 of `DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`
(its own "known control case" — the answer is a short, well-defined
module docstring claim, not a matter of interpretation).

## Failure mechanism, confirmed pre-fix

1. **The real answer exists in the database, correctly ingested.**
   Direct Postgres inspection (`ingestion_service.document_nodes` /
   `ingestion_service.vector_chunks`) confirmed `base.py`'s module and
   all three named functions present, correctly chunked (10 total
   `vector_chunks`), with `chunk_text` byte-identical to the current
   source checkout.
2. **At the default `top_k=20`, none of it is returned by seed vector
   search at all.** `/v1/rag` with `top_k=20` (the default) returned
   only chunks from `DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`
   — the eval doc that poses this exact question as its own candidate
   and lists the same three canonical IDs, but does not contain the
   function bodies.
3. **Widening `top_k` to 100 recovers the real module.** The identical
   query with `top_k=100` returned
   `ingestion_service/src/core/extractors/treesitter/base.py` (the
   module-level canonical ID) among the seed canonical IDs. This is the
   load-bearing finding for the fix's design: **the real answer was
   excluded from the database's own similarity-ordered `LIMIT` entirely
   at k=20, not merely outranked within an already-fetched set.** A
   client-side reorder of an already-narrow top-20 result cannot recover
   a candidate that was never fetched — the fix must widen the candidate
   pool before any doc_type-based selection can help.
4. **Root cause, verified against the DB, not the API alone:**
   `DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`
   produces ~253 `vector_chunks` (49 whole-document + ~204 across 21
   markdown-section sub-artifacts) vs. 10 for `base.py` — a ~25x
   chunk-count imbalance for one file, plus one chunk containing this
   exact question's wording near-verbatim, producing an artificially
   strong cosine match. `document_nodes.doc_type` correctly
   distinguishes `python source` from `markdown_section` for these
   artifacts; nothing in retrieval consulted it before this fix.
5. **Generator behavior on the resulting bad context** (both tried
   against the live, unfixed retrieval): `ollama/Qwen3:4b` filled the
   gap with fabricated implementation claims (invented specifics with
   no basis in the retrieved text, including a self-contradictory claim
   about `lru_cache` thread-safety); `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`
   was more evidence-bounded, in one run correctly declining to assert
   beyond what the retrieved text actually supported. Neither received
   correct context; the generator difference does not fix the retrieval
   defect.

## Fix implemented (issue #142)

- `rag_orchestrator/src/core/service.py`'s `hybrid_retrieve` now
  requests `k = max(top_k, settings.DOC_TYPE_TIE_BREAK_SEED_POOL_SIZE)`
  (default 100, the empirically-validated floor from finding 3 above)
  from seed vector search when `DOC_TYPE_TIE_BREAK_ENABLED=True`,
  instead of always `top_k`.
- `_apply_doc_type_tie_break` then narrows that wider pool back down to
  `top_k`, promoting an implementation-`doc_type` candidate ahead of a
  same-score-band documentation candidate only when their scores are
  within `DOC_TYPE_TIE_BREAK_EPSILON` (default 0.03 on the 0-1
  cosine-similarity scale) — a near-tie preference, not a hard filter,
  so a documentation chunk that is unambiguously the best match (margin
  exceeding epsilon) is left exactly where vector search ranked it.
- Default `DOC_TYPE_TIE_BREAK_ENABLED=False` (Stage A, mirrors WP-L5's
  rollout-flag precedent) — no production behavior change until this
  document is updated with a live-verified Stage B pass.

## Unit-test evidence (does not substitute for live re-verification)

`rag_orchestrator/tests/test_doc_type_tie_break.py` (7 tests, all
passing) covers, in isolation:
- Promotion of an implementation-doc_type chunk over a same-score-band
  documentation chunk (the exact shape of finding 4 above).
- **Control case**: a documentation chunk with a clear score margin is
  *not* displaced — proves this isn't a blanket doc_type preference
  that would break genuine documentation-seeking queries.
- No-op when the candidate pool isn't wider than `top_k` (the flag-off
  shape) — regression guard that disabling the flag exactly reproduces
  pre-fix behavior.
- `hybrid_retrieve` requests the widened `k` only when the flag is
  enabled (payload-capturing test, same `httpx.MockTransport` pattern as
  `test_repo_scoping.py`).

Full existing `rag_orchestrator` suite (137 tests) passes unchanged.

## What's still needed before Stage B (flag default → `True`)

1. Deploy this branch (issue #142) to a reachable stack.
2. Re-run this exact query with `DOC_TYPE_TIE_BREAK_ENABLED=true` and
   confirm `base.py`'s real content (not the eval doc) reaches
   `final_context_manifest`.
3. Run a control question that is genuinely best answered by
   documentation (e.g. "what does ADR-048 say about cross-artifact
   linking?") with the flag enabled, and confirm the answer is
   unaffected — proving the epsilon band doesn't over-fire.
4. Update this document's Status to `complete` with both results, and
   update the decision-gates row from `investigate` to `validated`
   before flipping the default.
