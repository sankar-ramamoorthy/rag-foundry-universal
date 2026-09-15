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
against a real production deployment on 2026-09-14, with direct database
verification. The fix (issue #142) is unit-tested but **not yet
re-verified live** against a deployment actually running it — this
repo's evaluation-gating discipline (Constitution Principle III/VIII,
`DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`) requires that
before `DOC_TYPE_TIE_BREAK_ENABLED`'s default flips to `True`. This
document will be updated in place once that live pass runs, per
`09-Retrieval-Technique-Decision-Gates.md`'s "update the row, don't
delete the record" convention — not superseded by a new dated file.

**2026-09-15 update: live re-verification attempted, original repro no
longer reproduces.** See "2026-09-15 live re-verification attempt"
below — the corpus drifted enough between the 2026-09-14 finding and a
2026-09-15 redeploy+re-ingest that this exact query (and several other
frozen-set candidates) no longer exhibits the failure, flag on or off.
The fix's *mechanism* remains verified only by the unit-test suite; a
live pass/fail on a currently-reproducing near-tie is still needed
before Stage B.

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

1. ~~Deploy this branch (issue #142) to a reachable stack.~~ Done
   2026-09-15 (`DOC_TYPE_TIE_BREAK_ENABLED=true` set in the deployment's
   `.env`, `rag_orchestrator` force-recreated, repo re-ingested).
2. ~~Re-run this exact query...~~ Attempted 2026-09-15 — **inconclusive**,
   see below: the original repro no longer fails even with the flag off,
   so this query can no longer distinguish the fix's effect.
3. Run a control question genuinely best answered by documentation (e.g.
   "what does ADR-048 say about cross-artifact linking?") with the flag
   enabled, and confirm the answer is unaffected. Done 2026-09-15 as a
   byproduct of the investigation below — `ADR-048-Cross-Artifact-Linking.md`'s
   own section ranked #1 and the answer correctly cited exact-name-matching.
   Not blocking on its own (a query that was already unambiguous isn't a
   strong test of the epsilon band), but no regression observed.
4. **Still needed:** a live query against the current corpus that
   actually reproduces a near-tie failure (an implementation chunk
   scoring within `DOC_TYPE_TIE_BREAK_EPSILON` of a documentation chunk,
   on the wrong side of the `top_k` cutoff) — see candidates for this
   under "2026-09-15 live re-verification attempt" below. Update this
   document's Status to `complete` and the decision-gates row from
   `investigate` to `validated` only once such a case shows the flag
   changing the outcome.

## 2026-09-15 live re-verification attempt

**Setup:** `DOC_TYPE_TIE_BREAK_ENABLED=true` confirmed set in the
deployment's `.env` (previously unset — the 2026-09-14 evidence above
was gathered before the flag was ever turned on live). `rag_orchestrator`
force-recreated to pick up the env change; repo re-ingested. `repo_id`
(`f7641840-ba13-5f9d-9ae6-87e1f924709d`) is unchanged (deterministic
scoping per ADR-030); `document_id`s changed (fresh UUIDs), confirming a
genuine re-ingest.

**Finding: the corpus has drifted.** `base.py` dropped from 10 to 7
`vector_chunks` between the two ingests (content unchanged in the DB
inspection, but chunking/embedding shifted). Direct `vector_store_service`
queries (bypassing the orchestrator's tie-break and its
alphabetized-and-already-narrowed `seed_canonical_ids` output, to see
the *raw* pre-tie-break similarity ranking) show:

- **Candidate 1** (issue #141's exact query): `base.py`'s best chunk now
  ranks **#10** by raw cosine score — comfortably inside `top_k=20`,
  with or without the flag. Pre-fix (2026-09-14), it was excluded from
  the top 20 entirely.
- **Candidate 4** (`SymbolTable.lookup`, exact candidate question): real
  answer (`GraphAssembler._link_docs_to_code`) ranks **#13** raw —
  same story.
- **Candidate 10** (`config.py` constants), asked exactly as worded in
  the eval doc: real answer ranks **#6–7** raw.
- **Candidate 9**: no `python source` chunk anywhere in the top 25 for
  the exact candidate question — but this looks like a genuine
  relevance miss (the phrasing doesn't specifically target the file),
  not a doc-type near-tie the fix is meant to correct.
- A *paraphrase* of Candidate 10 ("What are the retrieval expansion and
  cap constants defined in rag_orchestrator settings?", not the eval
  doc's literal wording) fails to surface the real answer in the top 30
  at all — but the crowding-out is generic `rag_orchestrator`-overview
  documentation, not the eval doc's near-verbatim self-reference. A
  different failure shape than issue #141; the epsilon-band tie-break
  is not designed to fix a genuine relevance miss, only a near-tied
  false positive.

**Conclusion:** none of the frozen-set candidates, asked as literally
worded in the eval doc, currently reproduce issue #141's specific
failure signature (implementation chunk pushed entirely outside
`top_k` by a near-tied documentation false positive) on this corpus.
The database-level root cause documented above (the eval doc's ~25x
chunk-count fan-out) is still present unchanged (253 `vector_chunks`,
confirmed 2026-09-15), so the *hazard* the fix guards against hasn't
gone away — it just isn't currently triggering for these specific
queries. The fix remains a defensive, flag-gated no-op for any query
that doesn't hit a near-tie, which is consistent with its design.

**Standing evidence for Stage B, pending a reproducing live case:**
the unit-test suite (`rag_orchestrator/tests/test_doc_type_tie_break.py`,
7 tests) directly exercises the promotion logic in isolation, including
the control case that a documentation chunk with a clear score margin
is left alone. This is real code-level verification, just not an
end-to-end live one. `DOC_TYPE_TIE_BREAK_ENABLED=true` has been left on
in this deployment (harmless when no near-tie occurs) so that a future
query that does hit one will be caught live without further setup.
