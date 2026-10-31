---
title: "E1 held-out clarification: tree-hash equivalence for verified snapshot repositories"
date: 2026-10-31
type: evaluation-addendum
status: frozen-before-any-held-out-ingestion-or-run
tags: [held-out, adr-054, pinned-commits, snapshot, frozen]
related:
  - "[Issue #305](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/305)"
  - "[Pre-registration (frozen)](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)"
  - "[Ingestion runbook](/DOCS/evaluations/code-evidence-held-out/ingestion-runbook.md)"
  - "[Held-out set README (frozen)](/DOCS/evaluations/code-evidence-held-out/README.md)"
---

# E1 held-out clarification: tree-hash equivalence for verified snapshots

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by #305,
under goal #294. Written on 2026-10-31, **before any held-out repository is ingested and before
any held-out query, control or candidate run**. It does not edit the frozen held-out manifest,
the frozen pre-registration, the GO rate or the statement-level contract.

## What it clarifies
Rule 5 of the [pre-registration](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)
says each repository is ingested at its pinned commit and that a generation whose `commit_sha`
differs from the pin is not used. That rule stays in force. This document adds one narrow,
explicit exception to what counts as "the pinned commit".

## Why an exception is needed
`POST /v1/ingest-repo` takes no ref and clones the default branch HEAD, so an exact source
needs a repository whose default branch is the pinned content. For `pallets/werkzeug`
(pinned `b73dce5a2ce14f7c7fd645699d1d878de48d2948`; upstream HEAD has moved and one changed file,
`src/werkzeug/test.py`, holds a case function) the full-history push of that commit to a
separate repository failed twice with a GitHub HTTP 500. Ingestion reads the source files and
records only the HEAD commit SHA; it uses no git history. The evaluation depends on the bytes of
the source, which a Git tree hash identifies exactly.

## The exception (and its limits)
A repository may be ingested from a **snapshot** instead of from the pinned commit itself only if
**all** of the following hold. The exception applies to such snapshots and to nothing else.
1. **Same tree.** The snapshot's tip commit has a tree hash **equal** to the tree hash of the
   original pinned commit (git computes it from the content, so equal tree hashes mean
   byte-identical files, paths and modes). For werkzeug that tree hash is
   `93f10217a04d9b5b3367d57227d3fec46c7990b8`.
2. **Nothing added.** The snapshot is a single root commit whose tree is exactly that tree: no
   README, license, workflow or other file is added or changed (any addition changes the tree
   hash and ends the exception).
3. **Verified, not assumed.** The tree hash is verified independently with git (for example from a
   shallow clone of the snapshot) and the result is recorded. The frozen manifest's stored
   function texts must hash to their recorded SHA-256 at the pinned commit (checked on
   2026-10-31: all 17, no mismatch).
4. **Mapping recorded.** The held-out corpus pin file records, per snapshot repository: the
   original pinned commit, the snapshot commit SHA, the shared tree hash, the repository id, the
   ingestion id and the generation's `commit_sha`.
5. **The generation is the snapshot.** The generation's `commit_sha` must equal the snapshot
   commit SHA recorded in (4), and the generation must be `ready`.

If any condition fails, the snapshot is not equivalent and is not used.

## What does not change
- The commit-SHA rule remains for every repository **not** ingested from a verified snapshot:
  `pypa/hatch` (`740565ac2929597cb9def8d46338cbef6493fc8d`) and `pdfminer/pdfminer.six`
  (`a18de2a9c479b4c847538500017b449ddaec177e`) are ingested from their upstream URLs and must
  report exactly those commits. If one of them has moved at ingestion time, it may be replaced by
  a snapshot only under conditions 1-5 above, using the tree hash of its pinned commit
  (hatch `ab8c48bb625432f23f8035afbd1aaf7fccb8141d`, pdfminer.six
  `b34c055ee8a7c23e332229bbbdc4e3c1ca8d1cf4`).
- The predictions P1-P4, the "named" and "delivered" definitions, the single-run and
  no-tuning discipline, the GO rate and the frozen manifest are unchanged.
- Repository identity: a snapshot has its own URL and therefore its own deterministic repository
  id; the frozen manifest records no repository ids, so nothing frozen is affected.

## Known limits (stated before the run)
A snapshot carries no history, authorship or upstream link, and its commit SHA is not the
upstream SHA. Neither affects what ingestion reads. The equivalence claimed is of the source
tree, verified by tree hash, and nothing more.
