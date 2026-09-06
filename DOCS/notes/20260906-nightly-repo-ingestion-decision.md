# Decision: nightly re-ingestion of rag-foundry-universal on the Linux/Tailscale instance (2026-09-06)

Status: decided, not yet automated (manual re-ingestion for now; cron/CI
automation is a separate follow-up, not committed to here).

## Decision

The Linux/Tailscale machine (`sankar-ml`, `100.105.24.12`) is treated as
the "prod" instance of this stack. This repository (rag-foundry-universal)
will be re-ingested there nightly, so the RAG index stays reasonably
current with `main`.

## Why

- Confirmed on 2026-09-06 (issue #89 live verification): the repo's query
  `id` returned by `GET /v1/repos` is **stable across re-ingestions**
  (`f7641840-ba13-5f9d-9ae6-87e1f924709d` — the same value before and
  after a full container rebuild + re-ingestion that same day). Only the
  `ingestion_id` field (the value you pass when *starting* an ingestion
  run) changes each time. Nightly re-ingestion therefore does not
  fragment history or break anything that references the repo by `id`.
- Without periodic re-ingestion, RAG answers reflect an increasingly stale
  snapshot of the codebase as PRs land on `main`.

## Caveat to carry forward

Every new file committed under `DOCS/test_results/` (and any other
knowledge-bearing doc) gets re-ingested along with the code on the next
nightly run. Section 16 of
`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`
documents a concrete case of this: the eval docs from earlier evaluation
rounds contain the written-up ground truth/answers for a fixed set of
baseline questions, and once ingested, get retrieved as sources when those
same questions are asked again — contaminating any future answer-quality
regrade against this repo using that question set. Nightly ingestion makes
this compound over time as more eval docs accumulate, not less. Any future
live evaluation against this repo should either exclude
`DOCS/test_results/*.md` from the seed/expansion set, or use a
question set that isn't already answered in the repo's own docs.

## Not decided here

- Whether re-ingestion is a full re-ingest or an incremental/delta
  ingestion (this stack's current ingestion API shape wasn't checked for
  incremental support as part of this decision).
- The actual automation mechanism (cron on the Linux box, a GitHub Actions
  scheduled workflow calling the ingestion API, etc.) — tracked as
  follow-up, not this note.
