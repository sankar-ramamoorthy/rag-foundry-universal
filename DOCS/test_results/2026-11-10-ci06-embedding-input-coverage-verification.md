---
title: "CI-06 embedding-input coverage: measurements and verification"
date: 2026-11-10
type: test-result
status: complete
summary: "Legacy inputs missed ~10-12% of artifact text; the exact-input contract covers it all and every passage was accepted by the serving model; gap discovery roughly doubles; pre-registered delivery evaluation passed; review R1-R5 resolved"
source_commit: "75c3b4c plus the #337 branch; revised 2026-11-11 after the independent review"
tags: [ci06, ci03, embedding, chunking, coverage, retrieval, evaluation]
related:
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)"
  - "[ADR-056 (proposed)](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[Implementation plan](/specs/005-production-correctness/ci06-plan.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
  - "[Independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)"
  - "[Delivery evaluation protocol](/DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md)"
---

# CI-06 embedding-input coverage — #337

On two development corpora, about 10–12% of non-whitespace artifact text reached
no embedding input under the legacy contract. Under the proposed contract all of
it does, and the serving model accepted every one of the 80,819 unique passages
(both corpora) without truncation. On sampled needle
queries, lines the legacy contract never embedded went from 42% to 81% hit@5
(foundry) and from 52% to 84% (LightRAG) with the shipped contract (verbatim
form). Lines every contract embeds were neutral to slightly better on one corpus
and slightly worse on the other. A pre-registered bounded delivery evaluation
passed all five criteria, and the independent review's findings R1–R5 were
reproduced and resolved. No held-out, production or deployed data was used.

## Setup

- **Corpora (development only).** This repository at `75c3b4c` plus the #337
  working tree, and LightRAG at the E1 development pin
  `4d0afc1bc36e6a34d4a5895b68efe9413748627a` (shallow clone). Artifacts come from
  the real `RepoGraphBuilder`, exactly as persisted for embedding.
- **Model.** `mxbai-embed-large:latest`, digest `468836162de7`, on the owner's
  remote Ollama host (same digest as the local copy; used with the owner's
  permission for speed). Context 512 tokens (`bert.context_length`).
- **Script.** [`scripts/ci06_embedding_coverage.py`](/scripts/ci06_embedding_coverage.py).
  Raw outputs and embedding caches are under `DOCS/test_results/_raw/ci06/`,
  recorded with hashes in the [raw index](/DOCS/test_results/raw-index.json).

## Measures

- **Input coverage.** A non-whitespace artifact character is covered when it is
  inside at least one effective input (the exact text the model encodes, after
  any client cut). Inputs are matched to the artifact in source order, ignoring
  whitespace, so the legacy chunkers' whitespace rewriting is not counted as
  loss. The matcher is conservative on repeated text: the few "partially
  missing" artifacts left for line windows are matcher artefacts; exact tiling
  is proven by unit tests instead.
- **Token fit.** Judged by the serving model itself (`truncate: false`); see
  "Token fit, judged by the serving model". An earlier offline counter is
  withdrawn.
- **Discovery.** Needle queries are single source lines (25–160 characters, at
  least two identifiers, unique to one file). *Gap* lines lie entirely in text
  the legacy contract never embedded; *control* lines lie entirely in text every
  contract embeds. Each query runs verbatim and as split identifier words (cells
  below show both, in that order). Passages from 900 code artifacts (the gap and
  control owners plus 600 random distractors) are ranked by cosine similarity;
  an artifact's rank is the best rank of any of its passages. Paired per-query
  comparisons use an exact sign test. An exploratory run (seed 337, 400
  artifacts) preceded the confirmatory run reported here (seed 3370), which was
  the first to include 400/500-character windows.

## Coverage

| Corpus | Contract | Code text missing | Docs text missing | Partially missing artifacts | Passages |
| --- | --- | ---: | ---: | ---: | ---: |
| Foundry | Legacy (v1 + 800-char cut) | 11.49% | 9.97% | 1,491 | 27,528 |
| Foundry | Legacy units, no cut | 0.00% | 0.00% | 29 | 27,528 |
| Foundry | Fitted heuristic (doc path) | 0.00% | 0.00% | 30 | 31,130 |
| Foundry | **Line windows 800 (shipped)** | 0.00% | 0.00% | 1 | 21,326 |
| Foundry | artifacts | 3,413 code | 3,679 docs | | |
| LightRAG | Legacy (v1 + 800-char cut) | 10.24% | 12.15% | 4,624 | 77,799 |
| LightRAG | Legacy units, no cut | 0.00% | 0.00% | 20 | 77,799 |
| LightRAG | Fitted heuristic (doc path) | 0.00% | 0.00% | 44 | 92,083 |
| LightRAG | **Line windows 800 (shipped)** | 0.00% | 0.00% | 2 | 73,996 |
| LightRAG | artifacts | 19,420 code | 1,494 docs | | |

## Discovery (confirmatory run, seed 3370)

Foundry: 900 artifacts in the ranked corpus, 129 gap and 126 control queries.

| Contract | Passages | Gap hit@1 | Gap hit@5 | Gap MRR | Control hit@1 | Control hit@5 | Control MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Legacy (v1 + 800-char cut) | 1,984 | 28 / 31 | 54 / 49 | 0.301 / 0.313 | 74 / 79 | 92 / 99 | 0.666 / 0.694 |
| Fitted heuristic (doc path) | 2,359 | 81 / 77 | 101 / 99 | 0.704 / 0.681 | 70 / 75 | 91 / 93 | 0.638 / 0.663 |
| **Line windows 800 (shipped)** | 1,887 | 75 / 62 | 105 / 97 | 0.687 / 0.603 | 73 / 79 | 98 / 96 | 0.669 / 0.689 |
| Line windows 400 | 3,615 | 79 / 76 | 107 / 103 | 0.707 / 0.682 | 81 / 80 | 99 / 100 | 0.709 / 0.709 |
| Line windows 500 | 2,840 | 87 / 85 | 116 / 108 | 0.760 / 0.740 | 76 / 78 | 98 / 98 | 0.684 / 0.696 |

Paired against legacy (queries better / worse; exact sign-test p; verbatim then identifier-words):

| Contract | Gap | Control |
| --- | --- | --- |
| Fitted heuristic (doc path) | 97/8 (p<0.001); 88/11 (p<0.001) | 2/39 (p<0.001); 3/40 (p<0.001) |
| **Line windows 800 (shipped)** | 95/12 (p<0.001); 90/16 (p<0.001) | 15/33 (p=0.0133); 16/34 (p=0.0153) |
| Line windows 400 | 98/8 (p<0.001); 93/8 (p<0.001) | 27/24 (p=0.78); 19/34 (p=0.0534) |
| Line windows 500 | 98/9 (p<0.001); 94/12 (p<0.001) | 21/33 (p=0.134); 17/35 (p=0.0175) |

LightRAG: 900 artifacts in the ranked corpus, 116 gap and 125 control queries.

| Contract | Passages | Gap hit@1 | Gap hit@5 | Gap MRR | Control hit@1 | Control hit@5 | Control MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Legacy (v1 + 800-char cut) | 2,273 | 26 / 34 | 60 / 57 | 0.363 / 0.405 | 75 / 75 | 90 / 92 | 0.671 / 0.671 |
| Fitted heuristic (doc path) | 2,675 | 76 / 68 | 103 / 102 | 0.749 / 0.716 | 73 / 73 | 90 / 90 | 0.651 / 0.654 |
| **Line windows 800 (shipped)** | 1,959 | 68 / 59 | 97 / 95 | 0.696 / 0.642 | 73 / 70 | 85 / 83 | 0.639 / 0.622 |
| Line windows 400 | 3,816 | 80 / 77 | 109 / 103 | 0.792 / 0.762 | 83 / 77 | 98 / 96 | 0.723 / 0.693 |
| Line windows 500 | 3,007 | 84 / 80 | 109 / 112 | 0.822 / 0.797 | 70 / 68 | 91 / 88 | 0.647 / 0.629 |

Paired against legacy (queries better / worse; exact sign-test p; verbatim then identifier-words):

| Contract | Gap | Control |
| --- | --- | --- |
| Fitted heuristic (doc path) | 82/7 (p<0.001); 70/13 (p<0.001) | 2/41 (p<0.001); 1/38 (p<0.001) |
| **Line windows 800 (shipped)** | 78/10 (p<0.001); 72/11 (p<0.001) | 24/30 (p=0.497); 22/31 (p=0.272) |
| Line windows 400 | 82/9 (p<0.001); 74/8 (p<0.001) | 25/26 (p=1); 24/33 (p=0.289) |
| Line windows 500 | 80/8 (p<0.001); 74/9 (p<0.001) | 16/38 (p=0.0038); 18/42 (p=0.0027) |

## Findings

1. **The legacy contract omitted text throughout, not just at window edges.**
   Most loss came from sentence/paragraph units larger than 800 characters (a
   code "sentence" can be a whole function), not only the 800–900 gap in each
   1,000-character window that the audit reproduced.
2. **Discovery of previously omitted text improves in every aligned contract**
   (p < 0.001 on both corpora and both query forms).
3. **Needle-control effects are small and size-dependent.** For 800-character
   line windows, foundry control hit@5 rose (92→98 verbatim) while the paired
   test showed more small rank losses than gains (p ≈ 0.01). On LightRAG,
   control hit@5 fell from 90 to 85 (verbatim) and from 92 to 83 (words); paired
   tests were not significant, which does not establish non-inferiority.
   400-character windows were neutral or better on controls but need about 1.8×
   the passages; 500 was worse than both on LightRAG controls.
4. **Fitting legacy units** (kept for the document-upload path) improves gap
   discovery but is consistently worse on needle controls and adds about 17%
   more passages; it was not chosen for repository artifacts.

## Token fit, judged by the serving model

> [!warning] Withdrawn evidence
> The first version of this report counted tokens with an offline WordPiece
> reimplementation and reported 0 overflows for the shipped contract and 376
> for legacy. The [independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)
> (R3) showed that counter diverges from Ollama's tokenizer (long words,
> Unicode normalization), so those figures are withdrawn. The legacy figure was
> not re-measured; only the shipped contract was.

Every unique passage of the shipped contract was sent to the serving model with
`truncate: false` (bisecting rejected batches): Ollama 0.32.1,
`mxbai-embed-large:latest` digest `468836162de7…`, F16, context 512.

| Corpus | Unique code passages | Unique doc passages | Rejected by the model | Pieces added by splitting |
| --- | ---: | ---: | ---: | ---: |
| Foundry (working tree, 7,206 artifacts) | 7,822 | 10,380 | 0 | 0 |
| LightRAG @ `4d0afc1` (20,914 artifacts) | 57,659 | 4,958 | 0 | 0 |

Whatever the corpus, rule 3 of ADR-056 makes this a guarantee rather than a
measurement: a rejected passage is split and never stored truncated.

## Review follow-up (R1–R5)

| Finding | Independent verification | Resolution | Evidence |
| --- | --- | --- | --- |
| R1 truncated embeddings for budget-compliant passages | Reproduced on Ollama 0.32.1: all three review inputs (`"xyz " * 200`, `"qz" * 300`, a 791-character comment) are single passages within both budgets and are rejected with `truncate: false` | Passages are never truncated: rejected passages are split into exact pieces, re-embedded, ordinals kept consecutive across buffer flushes; unsplittable input fails ingestion; only queries may be server-truncated; contract bumped to `exact-input-v3` | Unit tests through the real pipeline, buffer and record builder; a live test against the serving model passed for all three inputs (each stored piece accepted strictly, text reassembles exactly) |
| R2 cleanup failure mixes generations on reuse | Reproduced on PostgreSQL: with the fence removed, G3 received both the stale G1 row and G2's row | Retag fenced to the expected prior generation in both UPDATE branches; the store returns the moved documents; ingestion embeds any reusable artifact lacking prior vectors | `test_retag_generation_fence.py` (both branches) and `test_failed_cleanup_never_mixes_generations_on_reuse` (one contract throughout: G1 → changed file in G2 with failed cleanup → G3 reuse); both fail with the fence removed and pass with it |
| R3 token counter not equivalent to the tokenizer | Reproduced (`"qz" * 51` is 104 real tokens) | Counter removed; fit validated by the serving model (above) | `fit` command of the script |
| R4 delivery quality not established | Agreed | Pre-registered bounded evaluation (below) | Protocol committed before results |
| R5 identity, rollout, scaling | Agreed | Dimension added to the identity (FR-006); identity limits stated; clean-rebuild rollout per owner; bisection limits request amplification; `_split_line` made linear (8M-character line: 1.2 s, was 16.5 s in the review) | ADR-056 |

## Delivery evaluation (pre-registered)

Protocol and criteria were committed (`01cba02`) and pushed before any of these
results existed: [protocol](/DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md).
Development data only; serving model as above.

| ID | Criterion | Legacy | New | Result |
| --- | --- | ---: | ---: | --- |
| D1 | Expected expressions delivered (of 112), margin 6 | 48 | 61 | pass |
| D2 | No case loses over half its delivered expressions | | none lost any | pass |
| D3 | Primary targets discovered (of 14) | 14 | 14 | pass |
| D4 | Multilingual doc hit@5 (of 150), margin 8 | 102 | repository path 94, upload path 114 | pass (repository path exactly at the margin) |
| D5 | Long-query discovery (of 14): (a) legacy index + legacy query, (b) legacy index + new query, (c) new index + new query | (a) 13 | (b) 13, (c) 14 | pass |

Per case, expressions delivered (k = 3 passages per expanded document; k = 5
gave identical totals):

| Case | Expected | Legacy | New |
| --- | ---: | ---: | ---: |
| L1 | 17 | 2 | 4 |
| L2 | 17 | 2 | 4 |
| L3 | 14 | 10 | 14 |
| F1 | 11 | 10 | 10 |
| F2 | 12 | 9 | 12 |
| F3 | 17 | 0 | 1 |
| WP-R4 (8 questions) | 24 | 15 | 16 |

Notes and limits:

- Delivery is simulated with the production `assemble_context` and the
  production caps, assuming graph expansion reaches every artifact the case
  names, for both contracts alike. Generated answers were not evaluated.
- The multilingual repository-path drop (102 → 94) is the weakest result and
  sits exactly on the pre-registered margin; the upload path improved (114).
- Frozen E1 bodies matched extraction for all E1 targets. In the WP-R4 snapshot
  one unnamed distractor (`run_rag`) was replaced by its E1-pinned text; both
  contracts saw the same text.
- One snapshot per case set and one sample seed.

## Decision support and limits

800-character line windows were kept over 400 because downstream passage
selection caps passages per document by count (three to five). The bounded
delivery evaluation found no loss at 800; 400 was not evaluated for delivery.

- Needle queries are a discovery proxy that favors small passages.
- Rankings are plain cosine over sampled corpora; real graph expansion,
  generation filters and competing repository documentation are not modeled.
- No deployed-stack, `/v1/rag` or held-out measurement.

## Automated verification

| Check | Result |
| --- | --- |
| `ingestion_service`, `-m unit` | 472 passed, 4 skipped |
| `ingestion_service` full suite on test PostgreSQL (pgvector pg15, all migrations) | All CI-06 tests pass; the 9 failures and 3 errors are identical on a clean `main` worktree (SQLite URLs, missing `alembic` executable, git-backed and ownership fixtures) |
| Incremental ingestion integration on PostgreSQL | 8 passed, including the R2 cleanup-failure scenario and the missing-prior-vector case |
| `vector_store_service` (with PostgreSQL) | 48 passed, including the fenced-retag test for both UPDATE branches |
| Live R1 test against the serving model (`CI06_OLLAMA_URL`) | 3 passed |
| Mutation checks | Removing the retag fence fails the store test and the end-to-end R2 test |
| `rag_orchestrator` non-DB suite, root tests | 433 and 202 passed |
| Ruff | clean on all tracked changed files |
| Whole-repository Pyright vs `main` | no new diagnostics from tracked files except an unresolved `psycopg` import in the new store test, the same environment-only diagnostic the existing WP-R4 store test has |

## Reproduce

```bash
# Coverage (no network)
DATABASE_URL=postgresql://unused/unused ./.venv/Scripts/python.exe \
  scripts/ci06_embedding_coverage.py coverage --repo <repo> \
  --contracts legacy-v1,unfitted,factory-docs,factory-code --json OUT.json
# Token fit judged by the serving model
./.venv/Scripts/python.exe scripts/ci06_embedding_coverage.py fit --repo <repo> \
  --contracts factory-code --ollama "$OLLAMA_URL" --json OUT.json
# Needle discovery
./.venv/Scripts/python.exe scripts/ci06_embedding_coverage.py retrieval \
  --repo <repo> --budgets 400,500 --token-budgets 480 \
  --contracts legacy-v1,factory-docs,factory-code,linewin@400/t480,linewin@500/t480 \
  --sample 150 --distractors 600 --seed 3370 \
  --cache DOCS/test_results/_raw/ci06/emb-cache-<repo>.jsonl \
  --ollama "$OLLAMA_URL" --json OUT.json
# Delivery evaluation (pre-registered)
./.venv/Scripts/python.exe scripts/ci06_delivery_eval.py --lightrag <LightRAG@4d0afc1> \
  --foundry-e1 <foundry@109f12d8> --foundry-r4 <foundry@3ba6a2f> \
  --ollama "$OLLAMA_URL" --cache-dir DOCS/test_results/_raw/ci06 --json OUT.json
```
