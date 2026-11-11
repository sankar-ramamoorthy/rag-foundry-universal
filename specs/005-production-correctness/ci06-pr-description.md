# CI-06: stored passages are the exact embedding input

## Change

About 10–12% of non-whitespace artifact text reached no embedding input on two
development corpora. Sentence/paragraph chunks had no size limit and the Ollama
embedder cut every input to 800 characters; Ollama also silently cut inputs past
`mxbai-embed-large`'s 512-token context (376 legacy inputs, mostly CJK docs).

Proposed [ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md) makes every
stored passage the exact, complete model input:

- `shared/embedders/input_contract.py`: one contract (800 characters, 480 by a
  conservative token estimate, 100-character line overlap, id `exact-input-v2`).
- Repository artifacts: exact line windows (verbatim slices covering the whole
  artifact). Document uploads keep their strategy with each unit fitted.
- `OllamaEmbedder`: no client trimming; `truncate: false`; an over-context input
  is isolated and, only as a last resort, server-truncated and recorded as
  `source_metadata.embedding_input.truncated = true`.
- Reuse gate (CI-03 link): `budgeted-v2` and `<provider>:<model>:exact-input-v2`
  replace the old strings, so each repository is fully re-embedded once on its
  next ingestion; unchanged-contract reuse still works.

Closes #337. Phase 6 correctness follow-up (CI-06). No schema change, no
canonical-ID or graph change, no deployment. Out of scope: the rest of CI-03
(#313); uploaded Markdown/Docling section ingestion, broken on `main` since #81
(#338).

## Validation

Details, tables and commands:
`DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md`.

- **Coverage/token fit** (this repo and LightRAG at the E1 dev pin, real extractor,
  exact WordPiece counts validated 43/43 against Ollama): missing text 11.5% /
  10.0% (foundry code/docs) and 10.2% / 12.2% (LightRAG) → complete; inputs over
  512 tokens 376 → 0 (max 489); passages −22.5% / −4.9%.
- **Discovery** (needle line queries, 900-artifact corpora, confirmatory seed
  3370, remote Ollama, same model digest): lines legacy never embedded, hit@5
  54→105/129 (foundry) and 60→97/116 (LightRAG), p < 0.001. Already-covered
  lines: foundry hit@5 92→98 but more small rank losses (p ≈ 0.01); LightRAG
  90→85 (verbatim) and 92→83 (words), paired tests not significant.
- 400-character windows were neutral-or-better on controls but need ~1.8× the
  vectors and halve evidence per passage under count-based passage caps; deferred
  pending a delivery-side evaluation.
- Tests: 57 new unit tests; ingestion unit 464 passed; full ingestion suite on test
  PostgreSQL 578 passed, with the same 9 failures + 3 errors as a clean `main`
  worktree; incremental integration 6 passed (new legacy-contract re-embed test,
  now also a CI step); orchestrator 433, vector store 31, root 202 passed.
- Ruff clean on changed files; Pyright 0 errors on new modules; whole-repo Pyright
  adds no diagnostics from tracked files versus `main`.

Limits: needle queries are a discovery proxy that favors small passages; no
`/v1/rag`, E1 delivery or answer-quality measurement; one confirmatory sample per
corpus.

**Owner decisions:** ADR-056 acceptance; deployment and re-ingestion timing —
pinned E1/held-out generations are legacy-contract and change when re-ingested;
whether to run a delivery-side passage-size experiment.

## README accuracy and documentation

- [x] README remains accurate: it makes no chunk-size or embedding-input claims.
- [x] Progress and validation are in `DOCS/status.md` and the evidence report.
- [x] New local documentation links checked; no licensing change.
