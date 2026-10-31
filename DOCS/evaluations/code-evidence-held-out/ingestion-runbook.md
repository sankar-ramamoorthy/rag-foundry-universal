---
title: "E1 held-out ingestion runbook"
date: 2026-10-31
type: runbook
status: ready-snapshot-for-werkzeug-nothing-ingested
tags: [held-out, ingestion, operator-owned, pinned-commits]
related:
  - "[Issue #303](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/303)"
  - "[Held-out set README (frozen)](/DOCS/evaluations/code-evidence-held-out/README.md)"
  - "[Pre-registration](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)"
  - "[Snapshot clarification (#305)](/DOCS/evaluations/code-evidence-held-out/clarification-snapshot-tree-equivalence.md)"
  - "[Dev corpus pin (the same procedure, #292)](/DOCS/evaluations/code-evidence-e1/dev-corpus-pin.json)"
---

# E1 held-out ingestion runbook

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by #303.
**Operator-owned:** the repository owner runs every ingestion and every push; an agent only
verifies read-only, and reads the production database only when asked. Nothing has been
ingested yet. No held-out query or run happens before the pre-registration is merged.

## Pins checked on 2026-10-31
| Repository | Pinned commit | Upstream HEAD on 2026-10-31 | Tree hash at the pin | Action |
| --- | --- | --- | --- | --- |
| pypa/hatch | `740565ac2929597cb9def8d46338cbef6493fc8d` | same | `ab8c48bb625432f23f8035afbd1aaf7fccb8141d` | ingest the upstream URL, then verify the commit; use a verified snapshot if it moved |
| pdfminer/pdfminer.six | `a18de2a9c479b4c847538500017b449ddaec177e` | same | `b34c055ee8a7c23e332229bbbdc4e3c1ca8d1cf4` | ingest the upstream URL, then verify the commit |
| pallets/werkzeug | `b73dce5a2ce14f7c7fd645699d1d878de48d2948` | `2adaad1ab68312fa46efb07ff072b15b720e2444` (moved) | `93f10217a04d9b5b3367d57227d3fec46c7990b8` | **snapshot required** (Step 1; tree-hash equivalence) |

All 17 frozen function texts in `manifest.json` were checked against these pinned commits
(0 mismatches). For werkzeug, five files differ between the pin and the 2026-10-31 HEAD
(`_internal.py`, `exceptions.py`, `http.py`, `test.py`, `wrappers/response.py`); `test.py`
holds the case function `run_wsgi_app`'s file, so ingesting HEAD is not equivalent.
`POST /v1/ingest-repo` takes no ref parameter and clones the default branch HEAD, so exactness
needs a separate repository whose default branch holds the pinned content: for werkzeug a verified
single-commit snapshot (equivalence by tree hash, see the clarification).

## Expected repository ids
Repository identity is `uuid5(NAMESPACE_URL, lowercase URL without a trailing .git or /)`.
| Source URL | Expected repo id |
| --- | --- |
| `https://github.com/pypa/hatch` | `15f342ab-984c-5727-952c-513b25320d92` |
| `https://github.com/pdfminer/pdfminer.six` | `2dd9827e-3682-5d60-bbb1-973c235b6294` |
| `https://github.com/sankar-ramamoorthy/werkzeug-e1-heldout-pin` (created; holds the snapshot) | `520a1d74-1784-561c-a37e-effc32c8fc95` |

Approximate indexable files at the pins (py/md/json etc.): hatch ~500, werkzeug ~150,
pdfminer.six ~75 — each far smaller than the 768-file dev corpus.

## Step 0: before ingesting
1. Merge PR #295 (idempotent batch insert and bounded retry) and deploy it **or** accept that a
   cold-cache 90 s timeout (#287) can still fail an ingestion. Applying its migration needs
   idle ingestion and a duplicate-key check first (see the PR).
2. Check health: `/health` and `/version` on ports 8001-8004, and that the clean dev corpus
   (`a6e336ef-d0ee-54dd-a687-140dc1df17d3`) and LightRAG are still `ready`.
3. Ingest one repository at a time and let it finish before starting the next.

## Step 1: werkzeug snapshot (owner, in the existing werkzeug clone)
The full-history push failed twice with a GitHub HTTP 500, so werkzeug uses a single-commit
**snapshot** of the pinned tree, as allowed by the
[snapshot clarification](/DOCS/evaluations/code-evidence-held-out/clarification-snapshot-tree-equivalence.md)
(tree-hash equivalence, limited to verified snapshots). No history, no fork, no staged pushes.
```powershell
# in the werkzeug-pin clone (the pinned objects are already local)
git commit-tree 'b73dce5a2ce14f7c7fd645699d1d878de48d2948^{tree}' -m "Snapshot of pallets/werkzeug at b73dce5a (BSD-3-Clause)"
# it prints ONE sha: call it SNAPSHOT_SHA. Push only that commit to main of the empty repository:
git push https://github.com/sankar-ramamoorthy/werkzeug-e1-heldout-pin.git SNAPSHOT_SHA:refs/heads/main
```
Add nothing to the repository (no README, license or other file): any addition changes the tree
and ends the equivalence. The BSD-3-Clause `LICENSE.txt` and notice are already in the tree.
Tell the agent `SNAPSHOT_SHA`; it verifies read-only that `git ls-remote` shows `main` =
`SNAPSHOT_SHA` and that a shallow clone's `HEAD^{tree}` equals
`93f10217a04d9b5b3367d57227d3fec46c7990b8` (the tree of the pinned commit). Only then ingest.

## Step 2: ingest (web UI), then verify
Ingest `https://github.com/pypa/hatch`, `https://github.com/pdfminer/pdfminer.six` and the werkzeug
snapshot repository URL, one at a time. For each, report the ingestion id and, on request, an agent checks
read-only:
- `GET /v1/repos/{repo_id}/generation` is `ready` and `commit_sha` equals the pin (for the werkzeug
  snapshot: equals `SNAPSHOT_SHA`, with the tree hash verified as in Step 1). **If hatch or
  pdfminer.six reports a different commit, upstream moved: do not use it; use a verified snapshot
  as in Step 1 (clarification conditions 1-5, with that commit's tree hash).**
- Node and chunk counts, chunking and embedding config versions (`heuristic-v1`,
  `ollama:mxbai-embed-large:latest`), and the host embedder digest vs `execution-contract.json`.
- The stored text of every manifest function in that repository hashes to the manifest's SHA-256
  (a narrow read-only SELECT, only when the owner asks).
- Record the result in `DOCS/evaluations/code-evidence-held-out/held-out-corpus-pin.json`
  (repo ids, ingestion ids, commits, counts, date). The frozen manifest is **not** edited.

## Step 3: not before
No held-out control or candidate run until all three corpora are verified and recorded, the
pre-registration is merged, and the control path is agreed (the F1-F3 control used the harness
`control` mode; a held-out equivalent needs its own harness change under its own issue).

## What is expected to be in these corpora
The upstream tests, docs and examples are ingested too, so tests and prose are candidate
chunks for retrieval. That is deliberate (it is the corpus a user would ingest) and is part of
what the held-out result measures. No file from this project's own evaluation corpus is in
these repositories.
