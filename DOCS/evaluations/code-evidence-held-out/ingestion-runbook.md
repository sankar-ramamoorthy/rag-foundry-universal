---
title: "E1 held-out ingestion runbook"
date: 2026-10-31
type: runbook
status: ready-nothing-ingested
tags: [held-out, ingestion, operator-owned, pinned-commits]
related:
  - "[Issue #303](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/303)"
  - "[Held-out set README (frozen)](/DOCS/evaluations/code-evidence-held-out/README.md)"
  - "[Pre-registration](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)"
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
| pypa/hatch | `740565ac2929597cb9def8d46338cbef6493fc8d` | same | `ab8c48bb625432f23f8035afbd1aaf7fccb8141d` | ingest the upstream URL, then verify the commit; mirror it if it moved |
| pdfminer/pdfminer.six | `a18de2a9c479b4c847538500017b449ddaec177e` | same | `b34c055ee8a7c23e332229bbbdc4e3c1ca8d1cf4` | ingest the upstream URL, then verify the commit |
| pallets/werkzeug | `b73dce5a2ce14f7c7fd645699d1d878de48d2948` | `2adaad1ab68312fa46efb07ff072b15b720e2444` (moved) | `93f10217a04d9b5b3367d57227d3fec46c7990b8` | **pinned mirror required** (below) |

All 17 frozen function texts in `manifest.json` were checked against these pinned commits
(0 mismatches). For werkzeug, five files differ between the pin and the 2026-10-31 HEAD
(`_internal.py`, `exceptions.py`, `http.py`, `test.py`, `wrappers/response.py`); `test.py`
holds the case function `run_wsgi_app`'s file, so ingesting HEAD is not equivalent.
`POST /v1/ingest-repo` takes no ref parameter and clones the default branch HEAD, so exactness
needs a separate repository whose default branch is the pinned commit (the #292 procedure).

## Expected repository ids
Repository identity is `uuid5(NAMESPACE_URL, lowercase URL without a trailing .git or /)`.
| Source URL | Expected repo id |
| --- | --- |
| `https://github.com/pypa/hatch` | `15f342ab-984c-5727-952c-513b25320d92` |
| `https://github.com/pdfminer/pdfminer.six` | `2dd9827e-3682-5d60-bbb1-973c235b6294` |
| `https://github.com/sankar-ramamoorthy/werkzeug-e1-heldout-pin` (proposed name) | `520a1d74-1784-561c-a37e-effc32c8fc95` (changes if the name changes) |

Approximate indexable files at the pins (py/md/json etc.): hatch ~500, werkzeug ~150,
pdfminer.six ~75 — each far smaller than the 768-file dev corpus.

## Step 0: before ingesting
1. Merge PR #295 (idempotent batch insert and bounded retry) and deploy it **or** accept that a
   cold-cache 90 s timeout (#287) can still fail an ingestion. Applying its migration needs
   idle ingestion and a duplicate-key check first (see the PR).
2. Check health: `/health` and `/version` on ports 8001-8004, and that the clean dev corpus
   (`a6e336ef-d0ee-54dd-a687-140dc1df17d3`) and LightRAG are still `ready`.
3. Ingest one repository at a time and let it finish before starting the next.

## Step 1: werkzeug pinned mirror (owner, in a scratch directory)
```bash
git clone --no-checkout https://github.com/pallets/werkzeug.git werkzeug-pin   # full history
cd werkzeug-pin
git cat-file -t b73dce5a2ce14f7c7fd645699d1d878de48d2948                       # must print: commit
# create an EMPTY public repository: no README, no license, no .gitignore
gh repo create sankar-ramamoorthy/werkzeug-e1-heldout-pin --public \
  --description "Pinned snapshot of pallets/werkzeug at b73dce5a (BSD-3-Clause) for E1 held-out evaluation"
git push https://github.com/sankar-ramamoorthy/werkzeug-e1-heldout-pin.git \
  b73dce5a2ce14f7c7fd645699d1d878de48d2948:refs/heads/main
```
Push only that commit to `main` (no tags, no other branches). The commit object, history and the
BSD-3-Clause `LICENSE.txt` and notice are preserved. Then an agent verifies read-only:
`git ls-remote` shows `main` = `b73dce5a...`, and a shallow clone's `HEAD^{tree}` equals
`93f10217a04d9b5b3367d57227d3fec46c7990b8`.

## Step 2: ingest (web UI), then verify
Ingest `https://github.com/pypa/hatch`, `https://github.com/pdfminer/pdfminer.six` and the werkzeug
mirror URL, one at a time. For each, report the ingestion id and, on request, an agent checks
read-only:
- `GET /v1/repos/{repo_id}/generation` is `ready` and `commit_sha` equals the pin. **If hatch or
  pdfminer.six reports a different commit, upstream moved: do not use it; create a pinned mirror
  with the same commands as Step 1.**
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
