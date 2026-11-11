---
title: "CI-06 embedding-input coverage: measurements and verification"
date: 2026-11-10
type: test-result
status: complete
summary: "Legacy inputs missed ~10-12% of artifact text; the exact-input contract covers it all with no token overflow; gap discovery roughly doubles, controls mixed on one corpus"
source_commit: "75c3b4c plus the #337 working tree"
tags: [ci06, ci03, embedding, chunking, coverage, retrieval, evaluation]
related:
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)"
  - "[ADR-056 (proposed)](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[Implementation plan](/specs/005-production-correctness/ci06-plan.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# CI-06 embedding-input coverage — #337

On two development corpora, about 10–12% of non-whitespace artifact text reached
no embedding input under the legacy contract. Under the proposed contract all of
it does, and no input exceeds the model's 512-token context. On sampled needle
queries, lines the legacy contract never embedded went from 42% to 81% hit@5
(foundry) and from 52% to 84% (LightRAG) with the shipped contract (verbatim
form). Lines every contract embeds were neutral to slightly better on one corpus
and slightly worse on the other. No held-out, production or deployed data
was used.

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
- **Token fit.** Exact token counts from a WordPiece counter built on the
  model's own vocabulary (from Ollama `/api/show`). It matched Ollama's
  `prompt_eval_count` on 43/43 sampled passages, including accented, CJK and
  base64 text. Measurement only; production uses a conservative estimate.
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

## Coverage and token fit

| Corpus | Contract | Code text missing | Docs text missing | Partially missing artifacts | Passages | Inputs > 512 tokens | Max tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Foundry | Legacy (v1 + 800-char cut) | 11.49% | 9.97% | 1,491 | 27,528 | 3 | 734 |
| Foundry | Legacy units, no cut | 0.00% | 0.00% | 29 | 27,528 | 236 | 2769 |
| Foundry | Fitted heuristic (doc path) | 0.00% | 0.00% | 30 | 31,130 | 0 | 488 |
| Foundry | **Line windows 800 (shipped)** | 0.00% | 0.00% | 1 | 21,326 | 0 | 489 |
| Foundry | artifacts | 3,413 code | 3,679 docs | | | | |
| LightRAG | Legacy (v1 + 800-char cut) | 10.24% | 12.15% | 4,624 | 77,799 | 373 | 697 |
| LightRAG | Legacy units, no cut | 0.00% | 0.00% | 20 | 77,799 | 1,245 | 2337 |
| LightRAG | Fitted heuristic (doc path) | 0.00% | 0.00% | 44 | 92,083 | 0 | 502 |
| LightRAG | **Line windows 800 (shipped)** | 0.00% | 0.00% | 2 | 73,996 | 0 | 484 |
| LightRAG | artifacts | 19,420 code | 1,494 docs | | | | |

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
2. **Removing the client cut is not enough.** Without it, 236 (foundry) and
   1,245 (LightRAG) inputs exceed 512 tokens, which Ollama would truncate
   silently by default. Even legacy inputs exceeded it 376 times, mostly in
   Chinese and Japanese documentation, where a character is about one token.
3. **The shipped contract fits.** Maximum 489 tokens across both corpora, zero
   overflows, complete coverage, and 22.5% (foundry) and 4.9% (LightRAG) fewer
   passages than legacy.
4. **Discovery of previously omitted text improves in every aligned contract**
   (p < 0.001 on both corpora and both query forms).
5. **Control effects are small and size-dependent.** For 800-character line
   windows, foundry control hit@5 rose (92→98 verbatim) while the paired test
   showed more small rank losses than gains (p ≈ 0.01). On LightRAG, control
   hit@5 fell from 90 to 85 (verbatim) and from 92 to 83 (words); paired tests
   were not significant. 400-character windows were neutral or better on
   controls but need about 1.8× the passages. 500-character windows were worse
   than both 400 and 800 on LightRAG controls, so differences at this scale are
   near the noise floor.
6. **Fitting legacy units** (kept for the document-upload path) improves gap
   discovery but is consistently worse on controls and adds about 17% more
   passages; it was not chosen for repository artifacts.

## Decision support and limits

800-character line windows were chosen over 400 because downstream passage
selection caps passages per document by count (three to five). Smaller passages
would halve delivered evidence per artifact, an effect this evaluation does not
measure. See [ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md).

- Needle queries are a discovery proxy. They favor small passages and do not
  represent natural-language questions or answer quality.
- The ranking is plain cosine over a 900-artifact sample. It omits graph
  expansion, generation filters, documentation artifacts and the orchestrator's
  passage and context budgets.
- One sample per corpus for the confirmatory run; no repeated seeds.
- No end-to-end `/v1/rag` or E1 delivery measurement was run: the pinned
  evaluation generations are deployed, and re-ingesting them is the owner's
  decision.

## Automated verification

| Check | Result |
| --- | --- |
| New unit tests (`ingestion_service/tests/codebase/test_embedding_input_contract.py`) | 57 passed |
| `ingestion_service`, `-m unit` | 464 passed, 1 skipped |
| `ingestion_service` full suite on test PostgreSQL (pgvector pg15, port 5433, all migrations) | 578 passed. The 9 failures and 3 errors are identical on a clean `main` worktree (SQLite URLs, missing `alembic` executable, git-backed and ownership fixtures). |
| Incremental ingestion integration (`tests/api/test_incremental_ingest.py`) | 6 passed, including the new legacy-contract re-embed test |
| `rag_orchestrator` and `vector_store_service` non-DB suites | 433 and 31 passed |
| Remote CI on [PR #339](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/339) ([run 42956421223](https://github.com/sankar-ramamoorthy/rag-foundry-universal/actions/runs/42956421223)) | lint, unit-tests, integration-tests and bounded-memory passed; the new incremental-reuse step ran 6 tests on Linux, all passed |
| Ruff on changed files | clean |
| Pyright on new shared modules, new tests and the script | 0 errors. Remaining errors in touched service modules also exist on `main` (`git` stub, `local_path` typing, and the `ExtractionResult` defect filed as #338). |

The integration test records the first generation with the legacy strings
(`heuristic-v1`, `<provider>:<model>`) and checks that every artifact is then
re-embedded and that a following unchanged run reuses the new vectors. The
service log shows the gate firing:
`'heuristic-v1'/'mock:mxbai-embed-large:latest' -> 'budgeted-v2'/'mock:mxbai-embed-large:latest:exact-input-v2'; every file will be re-embedded`.

## Reproduce

Save the tokenizer tokens from Ollama `/api/show` (`verbose: true`,
`model_info["tokenizer.ggml.tokens"]`) as JSON first. Then:

```bash
DATABASE_URL=postgresql://unused/unused ./.venv/Scripts/python.exe \
  scripts/ci06_embedding_coverage.py coverage --repo <repo> \
  --contracts legacy-v1,unfitted,factory-docs,factory-code \
  --vocab DOCS/test_results/_raw/ci06/mxbai-embed-large-vocab.json --json OUT.json

./.venv/Scripts/python.exe scripts/ci06_embedding_coverage.py retrieval \
  --repo <repo> --budgets 400,500 --token-budgets 480 \
  --contracts legacy-v1,factory-docs,factory-code,linewin@400/t480,linewin@500/t480 \
  --sample 150 --distractors 600 --seed 3370 \
  --cache DOCS/test_results/_raw/ci06/emb-cache-<repo>.jsonl \
  --ollama "$OLLAMA_URL" --json OUT.json
```
