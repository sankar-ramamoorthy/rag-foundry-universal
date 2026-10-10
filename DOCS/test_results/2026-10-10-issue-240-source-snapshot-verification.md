---
title: "Issue #240 source snapshot verification and acceptance scope"
date: 2026-10-10
type: test-result
status: complete-with-limited-coverage
tags: [repository-overview, evaluation, provenance, generation]
related:
  - "[C1 correction and frozen verification](/DOCS/test_results/2026-10-10-issue-240-c1-fix-frozen-verification.md)"
  - "[New-generation comparison](/DOCS/test_results/2026-10-10-issue-240-new-generation-http-comparison.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #240 source snapshot verification

## Decision and measured scope

Accept #240's current implementation for PR and merge on the measured
repository-overview evidence: the corrected candidate passed all 11 frozen
answer/source checks on ready generation
`efd94377-679d-494d-84af-53b00c83f487`. This is evidence for the frozen
questions against this repository source and the tested runtime configuration.
It is not a claim of universal repository understanding or of performance on
held-out repositories. Generalization and overfitting review are tracked
separately in [issue #243](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/243).

The candidate's orchestrator ran locally at `f65fdfc` for the final C1 rerun;
the ingestion service serving the generation reported runtime
`1b8f4f510a6627689b2f48979e43feaf0595a7af`. These are runtime identities.
The repository **being analyzed** was recorded as source commit
`7a805d5b3cee031c44fbe0d9b8048065ce8ef039`, then the `main` head. No
claim is made that the feature branch itself was ingested as the subject.

[PR #244](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/244)
merged the candidate to `main` on October 10. Lint, unit tests, and the
bounded-memory CI job passed on the first attempt. The first integration job
failed two vector-store ANN result-count assertions; the unchanged job passed
on one rerun, and all four checks were green at merge. This does not establish
that the final orchestrator was deployed remotely after the merge.

## Independent Compose byte check

The generation-scoped Compose endpoint reported the two Compose SHA-256
digests below. The [saved verifier output](/DOCS/test_results/2026-10-10-issue-240-compose-source-verification.json)
shows that both match exact Git blob bytes at the recorded source commit:

| Source path | Recorded and independently recomputed SHA-256 |
| --- | --- |
| `docker-compose.yml` | `a574e85155c3aa6a6d7b90e6de3f56bf500f7ecbcf66dcebe6f0002c2daaa447` |
| `docker-compose.test.yml` | `5f6eb00e7dbb48bc2fefef3a7f3f0c4bb13519015a5a72b644f874719dbc1e4f` |

The October 8 adapter used different local Compose bytes. Their digests
(`7b648b9a...` and `5cc9f441...`) therefore cannot be treated as a byte
reproduction of this new production ingestion. The October 10 production
snapshot itself is reproducible for the two Compose files. The exact reason
the October 8 adapter used different bytes is not established by this check.

## Repeatable verification for future runs

After ingestion, record the runtime revision, repository ID, ready generation
ID, source commit SHA, and evaluation revision separately. Fetch the recorded
source commit into an independent checkout. Run:

```text
python scripts/verify_repo_compose_snapshot.py \
  --ingestion-url http://HOST:8001 \
  --repo-id REPO_ID --generation-id GENERATION_ID \
  --source-checkout PATH_TO_SOURCE_REPOSITORY \
  --output PATH_TO_EVIDENCE_JSON
```

The verifier reads the ready generation before and after, fetches the pinned
generation's Compose snapshot, compares its source commit identity, and
recomputes SHA-256 from `git show COMMIT:PATH` for every exposed Compose file.
It exits nonzero for a missing or changed generation, unavailable source
commit, absent Compose evidence, invalid path or digest, or a byte mismatch.
Keep its JSON output with the evaluation record. Use a source checkout from an
independent fetch; the current checkout's HEAD is irrelevant as long as it
contains the recorded commit.

This verifies **only the exposed Compose files**. It does not establish a
complete per-file corpus manifest, dirty `local_path` disclosure, pinned-ref
ingestion, or the full #180 source-revision contract. Those remain #180 work.
For a source without a Git commit or a generation without Compose snapshots,
the verifier fails rather than asserting reproducibility. Do not infer a
runtime/source match merely because both are Git commit IDs.
