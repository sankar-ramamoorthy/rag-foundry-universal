---
title: "E1 held-out set: repository selection record"
date: 2026-10-28
type: experiment-record
status: recorded-before-case-authoring
tags: [held-out, selection, adr-054, evidence-delivery]
related:
  - "[Issue #281](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/281)"
  - "[Stratification and selection declaration](/DOCS/evaluations/code-evidence-held-out/stratification.md)"
  - "[Raw scan output](/DOCS/evaluations/code-evidence-held-out/selection-scan.json)"
  - "[Scan script](/scripts/held_out_selection_scan.py)"
  - "[Statement-level contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
---

# E1 held-out set: repository selection record

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by
#281. This record is committed **before any case is written**. It is the result of
running the [frozen declaration](/DOCS/evaluations/code-evidence-held-out/stratification.md)
sections 4-6 mechanically with `scripts/held_out_selection_scan.py` on 2026-10-28.
The scan used only public GitHub metadata and static analysis (`ast`) of shallow clones.
No code from the clones was executed. Nothing from the evaluation stack, any retrieval,
control or candidate run, or any oracle byte cost was used.

## Selected repositories

| Domain | Repository | License | Stars | Pinned commit (default branch HEAD at scan) | Source files | Last push |
| --- | --- | --- | --- | --- | --- | --- |
| D1 command-line / tooling | [pypa/hatch](https://github.com/pypa/hatch) | MIT | 7,246 | `740565ac2929597cb9def8d46338cbef6493fc8d` | 211 | 2026-10-28 |
| D2 HTTP / networking | [pallets/werkzeug](https://github.com/pallets/werkzeug) | BSD-3-Clause | 6,880 | `b73dce5a2ce14f7c7fd645699d1d878de48d2948` | 54 | 2026-10-26 |
| D3 parsing / serialization | [pdfminer/pdfminer.six](https://github.com/pdfminer/pdfminer.six) | MIT | 7,046 | `a18de2a9c479b4c847538500017b449ddaec177e` | 43 | 2026-03-13 |

License texts are stored in `licenses/`. Attribution and the notices required by MIT and
BSD-3-Clause must accompany any stored function body (the manifest README will carry
them).

## What the declared rule did

| Step | D1 (`topic:cli`) | D2 (`topic:http`) | D3 (`topic:parser`) |
| --- | --- | --- | --- |
| Pool (4 license queries merged, stars descending, first 30) | 30 | 30 | 30 |
| Candidates evaluated before one qualified | 1 | 1 | 2 |
| Rejected on the way | none | none | `The-Vibe-Company/megaparse` (7,417 stars): topics include `llm`, description "File Parser optimised for LLM Ingestion" (criterion 3) |
| Selected | pypa/hatch | pallets/werkzeug | pdfminer/pdfminer.six |

Queries, verbatim: `language:python topic:<topic> stars:300..8000 archived:false
license:<mit|apache-2.0|bsd-3-clause|bsd-2-clause>`.

Shape availability (declaration section 6 minimums: 2 long functions, 1 long signature,
2 short branchy functions, 1 caller-callee file). Counts over non-test source files:

| Repository | Functions | Long body (>= 120 lines) | Long signature (>= 8 lines) | Short body (< 40) with branch/try/with | Files with a caller-callee pair | Unparsed files |
| --- | --- | --- | --- | --- | --- | --- |
| pypa/hatch | 1,192 | 8 | 45 | 550 | 37 | 0 |
| pallets/werkzeug | 1,157 | 7 | 43 | 451 | 26 | 0 |
| pdfminer/pdfminer.six | 683 | 5 | 34 | 313 | 12 | 0 |

All three pass comfortably. The scan found no reason to look past the first qualifying
repository in any domain.

## Checks beyond the script

- **Prior use in this project.** Searching the whole repository (including lockfiles)
  for each name: `werkzeug` has no mentions. `hatch` appears only in the English phrase
  "escape hatch" (two documents). `pdfminer` appears only as the transitive dependency
  `pdfminer-six` in `ingestion_service/uv.lock`. A dependency in a lockfile is not use
  of its source as an evaluation corpus; none of the three repositories has been
  ingested, queried or discussed as a corpus here.
- **Excluded repositories** (LightRAG, rag-foundry-universal, py-coding-agent) did not
  appear among the evaluated candidates.

## Clarifications and implementation choices (stated so they can be challenged)

1. **Mechanized criteria.** The declaration says "not a retrieval/LLM/RAG/agent
   framework" and "not a monorepo". The script implements the first as a keyword check
   (`rag`, `llm(s)`, `agent(s)`, `langchain`, `openai`, `chatgpt`, `gpt`, `retrieval`,
   `embedding(s)`, `genai`, `copilot`, `autogpt`) over the description and topics. It
   does **not** implement the monorepo clause.
2. **Source-file counting** excludes directories named tests/test/testing/docs/doc/
   examples/example/vendor/vendored/third_party/build/dist/venv/.venv/site-packages/
   node_modules, `conftest.py`, `test_*.py`, `*_test.py` and `*_pb2*.py`.
3. **Recency** uses the repository's last push date, not the last commit on the default
   branch.
4. **Signature length** is measured from the first decorator (or the `def` line) to the
   line before the first body statement, so a blank or comment line between header and
   body would be over-counted; function "body length" is the node's line span.
5. **Clones** used `git -c core.longpaths=true` because the scratch path exceeded the
   Windows length limit. This changes how the clone is written, not what is cloned.
6. A repository chosen for an earlier domain would be skipped for a later one. This
   was not triggered.

## Things the reviewer should look at

- **pypa/hatch ships two distribution packages** (the `hatch` CLI under `src/` and the
  `hatchling` build backend under `backend/`). The declaration excludes "a monorepo of
  many projects"; two coupled packages from one project was judged to satisfy it, but
  the clause is not mechanical. If the reviewer disagrees, the answer is a superseding
  declaration and a rerun of D1, not an exception.
- **Training-data exposure.** The star ceiling is a heuristic. pallets/werkzeug is the
  WSGI layer under Flask and is very likely well represented in model training data
  despite its star count. This is a limit on what a held-out result from that repository
  can show, not something the rule removes.
- **pdfminer.six** is a PDF parser; the project also ingests documents (Docling/OCR).
  That is unrelated to using its Python source as a code corpus, noted for completeness.

## What happens next (declaration sections 7-10)

1. Cases are written from the pinned sources only, 4 per repository, to the quotas in
   section 6 of the declaration. No ingestion, retrieval, control or candidate run on
   these repositories happens before the freeze.
2. The structural oracle is run only to confirm each expression is located and
   unambiguous and each function parses; its byte costs cannot add, drop or reshape a case.
3. The repository owner reviews every case (second reviewer); verdicts are recorded as given.
4. After the review, the manifest, its SHA-256 and the counting test are committed.
