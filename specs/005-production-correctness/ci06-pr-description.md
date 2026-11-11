# CI-06: stored passages are the exact embedding input

## Change

About 10–12% of non-whitespace artifact text reached no embedding input on two
development corpora: sentence/paragraph chunks had no size limit, the Ollama
embedder cut every input to 800 characters, and Ollama silently truncates
inputs past `mxbai-embed-large`'s 512-token context by default.

Accepted [ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md) makes every
stored passage the exact, complete model input:

- `shared/embedders/input_contract.py`: one contract (800 characters, 480 by a
  packing estimate, 100-character line overlap, id `exact-input-v3`).
- Repository artifacts: exact line windows covering the whole artifact. Document
  uploads keep their strategy with each unit fitted.
- Passages are embedded with `truncate: false`; the model's rejection is the
  final guard. A rejected passage is split into exact pieces (ordinals kept
  consecutive across embedding-buffer flushes) and each piece is embedded in
  full; nothing is stored truncated, and an unsplittable passage fails the
  ingestion. Only queries may be server-truncated (logged).
- Reuse identity: `budgeted-v2` and `<provider>:<model>:<dim>d:exact-input-v3`
  (dimension per FR-006).
- **Generation-fenced reuse:** retag moves only rows of the expected prior
  generation (both UPDATE branches), reports the documents moved, and ingestion
  embeds any reusable artifact lacking prior vectors. This fixes stale-vector
  contamination after a failed cleanup, which can occur even with one contract.

Rollout (owner decision): existing indexes are rebuilt cleanly at deployment;
no historical-vector compatibility. `vector_store_service` and
`ingestion_service` deploy together.

Closes #337. Phase 6 correctness follow-up (CI-06). Out of scope: the rest of
CI-03 (#313); uploaded Markdown/Docling section ingestion, broken on `main`
since #81 (#338).

## Independent review

All findings of the [Codex review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)
were independently verified and resolved:

- **R1** reproduced on the serving model (Ollama 0.32.1): the three review
  inputs fit both budgets yet are rejected. Fixed by split-on-rejection; unit
  tests through the real pipeline/buffer/record builder plus a live test against
  the model (each stored piece accepted strictly; text reassembles exactly).
- **R2** reproduced on PostgreSQL with the fence removed (G3 received the stale
  G1 row). Fixed; store-level test for both UPDATE branches and an end-to-end
  one-contract G1 → G2 (failed cleanup) → G3 test; both fail without the fence.
- **R3** reproduced; the offline counter is removed and its figures withdrawn.
  Fit is validated by the serving model.
- **R4** addressed by a pre-registered bounded delivery evaluation (below).
- **R5** dimension added to the identity; identity limits, rollout and rollback
  stated in ADR-056; rejected batches bisected; `_split_line` made linear; ADR-040
  carries a note on its relationship to ADR-056.

## Validation

Details: `DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md`.

- **Coverage:** missing text 11.5% / 10.0% (foundry code/docs) and 10.2% / 12.2%
  (LightRAG) → none; passages −22.5% / −4.9%.
- **Token fit (serving model):** every unique passage of the shipped contract was accepted with `truncate: false` (18,202 foundry, 62,617 LightRAG; Ollama 0.32.1, digest `468836162de7`), so splitting never fired on these corpora; it is a guard.
- **Needle discovery:** lines legacy never embedded, hit@5 54→105/129 (foundry)
  and 60→97/116 (LightRAG); already-covered lines mixed (LightRAG hit@5 90→85).
- **Delivery (pre-registered, committed before results):** expected expressions
  delivered 48 → 61 of 112, no case's delivered count declined (one case,
  `R4-chain`, swapped one expression for others); targets discovered 14/14 both;
  multilingual docs hit@5 102 → 94 (repository path, exactly at the margin) and
  114 (upload path); long-query discovery 13 → 14. All five criteria passed.
- **Tests:** ingestion unit 472 passed; incremental integration on PostgreSQL 8
  passed; vector store 48 passed; live R1 test 3 passed; orchestrator 433, root
  202. Full ingestion suite failures are identical to a clean `main` worktree.
  Ruff clean; no new whole-repository Pyright diagnostics beyond the
  environment-only `psycopg` import shared with existing store tests.

Limits: delivery is simulated with the production `assemble_context` and caps,
not the deployed stack; answers were not graded; one sample per case set.

## README accuracy and documentation

- [x] README remains accurate: it makes no chunk-size or embedding-input claims.
- [x] Progress and validation are in `DOCS/status.md` and the evidence report.
- [x] New local documentation links checked; no licensing change.
