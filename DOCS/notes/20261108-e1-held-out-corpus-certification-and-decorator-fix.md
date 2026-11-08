---
title: "E1 held-out corpus certification and the Python decorator-text fix"
date: 2026-11-08
type: work-record
status: complete-pending-pr-316-merge
tags: [e1, held-out, corpus, certification, python-extractor, incremental-reuse, evidence]
related:
  - "[Issue #294: E1 goal tracking](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/294)"
  - "[Issue #311: Python extractor omits decorators](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/311)"
  - "[PR #312: the fix](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/312)"
  - "[Issue #313: extractor behavior in the reuse identity](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/313)"
  - "[Issue #314: span semantics](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/314)"
  - "[Issue #315: corpus pin record](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/315)"
  - "[PR #316: the corpus pin](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/316)"
  - "[Held-out corpus pin](/DOCS/evaluations/code-evidence-held-out/held-out-corpus-pin.json)"
  - "[Held-out ingestion runbook](/DOCS/evaluations/code-evidence-held-out/ingestion-runbook.md)"
  - "[Frozen held-out set](/DOCS/evaluations/code-evidence-held-out/README.md)"
  - "[Dev corpus pin (precedent)](/DOCS/evaluations/code-evidence-e1/dev-corpus-pin.json)"
  - "[ADR-041: text persisted on DocumentNode.text](/DOCS/adr/ADR-041-code-artifact-persistence-embedding-strategy.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# E1 held-out corpus certification and the Python decorator-text fix

Roadmap phase: Phase 6, workstream E (E1, goal #294), with the extractor correction under Phase 3,
WP-L5 (Python extractor parity). Written 2026-11-08. This note records what was done, what was
found, and what is and is not established. Nothing here edits the frozen held-out manifest,
questions, predictions or evaluation contract.

## Why this work happened

The ingestion runbook requires that, before any held-out run, the stored text of every manifest
function in each ingested repository hashes to the manifest's SHA-256. Checking the five pypa/hatch
functions of the first Hatch generation (`184d3d89-6e15-4699-8f6f-1eccd195748b`) found 2 matches
and 3 mismatches, with no function missing.

## Finding: decorator lines were not stored (#311)

A line diff of the three mismatches (`show`, `lock`, `run`) showed one difference: the manifest
source began at the first `@click...` decorator, the stored `DocumentNode.text` began at `def`.
Bodies were identical; there were no line-ending differences. The two matching functions are
undecorated.

Cause: both Python extractors took the stored text from the `def`/`class` node, which excludes
decorators. Tree-sitter nests that node inside a `decorated_definition`, and the `ast` node's
`lineno` is the `def` line.

Fix (PR #312, merged `82b263f`): only the start of the stored text moves, to the first decorator's
`@`. `span`, `lineno`, kind, `symbol_path` and canonical IDs are unchanged. New regression tests run
every case on both extractors and compare the text byte-for-byte; the legacy test that pinned
"equal to `ast.get_source_segment`" now expects decorators for decorated nodes. The pinned manifest
text of the three functions reproduces the manifest hashes on both extractor paths.

## Finding: a normal re-ingest would not have picked the fix up

Reading the reuse gate showed it compares per-file raw-byte `content_hash` plus the chunking and
embedding config versions, and nothing about extractor behavior. Re-ingesting an unchanged commit
could therefore keep the old decorator-less nodes. The re-ingestion had to use
`force_full_rebuild=true` (a form field of `POST /v1/ingest-repo`; the API clones the repository's
default branch HEAD and cannot pin a commit, so the recorded `commit_sha` has to be checked after the
fact). This was recorded in the PR #312 description. The general problem is tracked separately:

- [#313](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/313): make extractor
  behavior part of the reuse identity (stale persisted data).
- [#314](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/314): define whether
  `span` means the definition or the full stored text (source-location correctness). The manifest's
  `start_line` for the decorated functions includes decorators, the stored span does not.

## Result: Hatch rebuilt and certified

The owner deployed PR #312 and re-ingested Hatch with `force_full_rebuild=true`. New generation
`c142f7d1-f473-4731-a33e-b0e7431e7b8d`: `ready`, `is_incremental=false`, parent `184d3d89-...`,
`commit_sha` `740565ac2929597cb9def8d46338cbef6493fc8d` (the frozen pin; the upstream HEAD was the pin
when checked). All five Hatch hashes matched, including the four functions under
`src/hatch/cli/env/` that PR #310 / issue #307 (an over-broad `env` directory ignore) had earlier
kept out of the corpus.

## The corpus pin (#315, PR #316)

[held-out-corpus-pin.json](/DOCS/evaluations/code-evidence-held-out/held-out-corpus-pin.json)
records all three held-out corpora. Every fact carries a status:

| Status | Meaning |
|---|---|
| measured | read from the production database by the cited read-only query |
| fetched | returned by a read-only GET or git command on the cited date |
| inferred | concluded from other evidence, not observed |
| reported | stated by the owner, not independently checked |
| unverified | not established; no value is recorded |

| Repository | Generation | Commit | Nodes | Chunks | Frozen functions |
|---|---|---|---|---|---|
| pypa/hatch | `c142f7d1-f473-4731-a33e-b0e7431e7b8d` | `740565ac...` | 9,243 | 13,795 | 5/5 |
| pdfminer/pdfminer.six | `85085698-8251-4471-9bd2-4101f8af471e` | `a18de2a9...` | 2,922 | 3,113 | 6/6 |
| pallets/werkzeug (snapshot) | `046c6d19-baff-4f1e-912c-2734e9797914` | `585fb463...` (tree `93f10217...`) | 6,084 | 6,640 | 6/6 |

All three: generation `ready` (generation API), `completed`, not incremental, the only generation
for the repo, chunking `heuristic-v1`, embedding `ollama:mxbai-embed-large:latest`. The werkzeug
generation is the verified snapshot permitted by the
[tree-equivalence clarification](/DOCS/evaluations/code-evidence-held-out/clarification-snapshot-tree-equivalence.md)
(#305): the snapshot commit differs from the upstream pin by design, the tree is identical.
Stored-text hashes are recomputed directly from `document_nodes.text` scoped to repo and ingestion
id, with no normalization. The pre-registration is merged (PR #304, issue #303).

## What is not established

- **Embedder digest at ingestion time.** The database stores the model name only. The current host
  model list shows `mxbai-embed-large:latest` at the contract digest (`468836162de7...`) modified
  2026-09-02, before every ingestion. That is consistent with, not proof of, the model that produced
  the vectors, so it is recorded as `inferred` from current host state (the same approach as the dev
  corpus pin).
- **Deployed runtime SHA at ingestion time.** Not stored per ingestion; recorded `unverified`. The
  current deployment SHA is deliberately not substituted.
- Hatch's `4861/4861` nodes processed is owner-reported. (Its `13795` chunks was reported and was then
  also measured.)
- pdfminer.six and werkzeug were ingested (2026-11-02) before PR #312. They contain no decorated
  frozen functions and all match.

## How to reproduce

`scripts/held_out_corpus_pin.py measure` reads the database read-only (connection string from the
environment variable you name; nothing is stored in the repository) and writes a measurements file
under `DOCS/test_results/_raw/`. `build` combines it with the manifest, two files fetched by plain
GETs (the generation API responses and the Ollama model list) and the execution contract, refuses to
run if `manifest.json` no longer matches `manifest.sha256`, and writes the pin.
`tests/test_held_out_corpus_pin.py` cross-checks the pin against the frozen manifest; it does not
re-read production.

## State and next steps

Corpus source-text verification is 17/17. E1 is **not** ready to execute: the held-out control
harness (the isolated 12-case control path, its own issue) and agreement on the control path remain.
No held-out query, control or candidate run has been made. Review notes on PR #316 asked for chunk
counts, alignment with the dev pin, measured hashes, `ready` from the API, and the embedder
attestation approach; this version carries them.

## Process notes

- Every change followed issue, branch, PR. Production reads were read-only and owner-authorized;
  deployment and re-ingestion were done by the owner.
- Operational lesson for any extractor change: a forced full rebuild is required until #313 is
  resolved, and the rebuild must be verified (`is_incremental=false`, a new `ingestion_id`, the parent
  recorded).
