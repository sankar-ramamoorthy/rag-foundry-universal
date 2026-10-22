---
title: "E1 baseline preparation and service availability limitation"
date: 2026-10-14
type: evaluation-report
status: superseded-by-completed-baseline-results
tags: [baseline, evidence-coverage, local, availability]
related:
  - "[Experiment decisions](/DOCS/evaluations/2026-10-14-code-evidence-experiment-decisions.md)"
  - "[Frozen cases](/DOCS/evaluations/code-evidence-e1/README.md)"
  - "[Availability observations](/DOCS/test_results/code-evidence-e1/availability.json)"
  - "[Historical L1 score](/DOCS/test_results/code-evidence-e1/historical-L1-score.json)"
  - "[Post-restart connectivity](/DOCS/test_results/code-evidence-e1/post-restart-connectivity.json)"
---

# E1 baseline preparation and service availability limitation

**Completion update:** all six cases were subsequently captured. The
[results and audit](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)
supersede this preparation record. Its zero-capture statements below describe
the earlier attempts, not current baseline status. A later prototype control
replay encountered a separate full-graph download timeout.

## Completed work

Six cases across two diagnostic repositories are frozen, covering 26 required
operations and 20 dependency obligations. Expected expressions were checked
against full persisted node bodies using the existing direct PostgreSQL
diagnostic connection in a read-only transaction. No new model answer was used
to choose or adjust the cases.

The local capture harness observes unchanged orchestrator code, records fetched
passages and the actual generation payload, validates generation stability and
enforces the 4096-byte budget. It has not implemented a candidate selector.
Eight scoring/manifest/cap/observer guard tests pass; focused Ruff and Pyright
checks pass.
Those checks establish harness mechanics, not baseline retrieval quality.

## Baseline capture status

A fresh L1 request started after generation and version checks succeeded. It did
not produce a completed capture before application service availability failed;
the local process was interrupted. Subsequent bounded HTTP checks of all four
service `/version` endpoints failed. The captured preflight at
`2026-10-14T14:14:05.847191+00:00` records `ReadError` for ports 8001-8004.
Other requests raised connection errors. The underlying service/network cause
has not been established. PostgreSQL inspection and an Ollama model-list request
were reachable separately; they do not establish application-service health.

After the operator restarted Linux, the resumed attempt passed all four version
checks at `2026-10-15T00:40:45.866841+00:00` (October 14 local time), with runtime
commit `109f12d83ab83a306318423be618c195f8c4e6ea` and the frozen LightRAG
generation. The latest `availability.json` contains this successful startup
preflight, replacing the earlier availability snapshot. L1 started but did not
complete. All four application HTTP ports subsequently reset requests; the
waiting local process was interrupted again.

At `2026-10-15T00:45:22.965902+00:00`, TCP connections to ports 8001-8004
and 5434 succeeded, but HTTP requests to all four application ports failed with
connection-reset error 10054. Raw HTTP and a request bypassing environment
proxies reproduced the reset. A separate PostgreSQL handshake timed out;
Ollama's `/api/ps` returned HTTP 200. These observations establish transient
availability, not a container crash, OOM event, firewall defect or causal
connection to retrieval. Host/container status is required to distinguish them.
The new connectivity snapshot retains the exact observations.

There are **zero completed fresh E1 baseline captures**. Unavailable requests
are unverified, not failed retrieval scores. No selector treatment or full
overview/control rerun has begun because the baseline gate is incomplete.

The local harness now records per-request progress events and preserves
incomplete observations without quality scores. Synchronous HTTP calls lacking
a deadline receive a diagnostic `(10, 120)` second connect/read timeout; explicit
existing deadlines are preserved. This limits capture hangs without changing
runtime policy, selected evidence or production configuration. These new hooks
were added after the interrupted attempt and do not establish its exact last
completed retrieval stage.

## Historical comparison, kept separate

The October 13 observed local replay has exactly the L1 question and the same
source generation. Applying the frozen obligations to its captured generation
payload gives:

| Metric | Historical L1 result |
| --- | --- |
| Target discovery | Yes |
| Target document survival | Yes |
| Required operation coverage | 0/4 |
| Required dependency expression coverage | 0/4 |
| Actual delivered context | 3960/4096 UTF-8 bytes |
| Unique relevant source bytes, conservative lower bound | 1702 bytes; 41.55% of cap |
| Repeated relevant source bytes, conservative lower bound | 587 bytes |

Relevant here means source lines in the frozen target/helper bodies, including
their signatures and setup. A high count does not imply the mandatory operations
are covered. Ambiguous short lines and whitespace are excluded from this lower
bound; it is not a full irrelevant-byte or overhead accounting.

The historical answer identifies the function and four-stage outline but
explicitly cannot explain the budget implementation. It does not pass the full
implementation explanation gate. No numeric faithfulness score is claimed;
formal answer/citation review remains pending. Incomplete delivered evidence
prevents attributing this failure solely to the model.

This historical record is not substituted for a newly captured cross-repository
baseline and does not supply scores for the other five questions.

## Next executable step

The operator was asked for read-only `docker ps` container status and `free -h`
output. No service restarts or deployment changes were attempted by the agent.
Once application HTTP access is stable, rerun the baseline command
in the frozen-case README. Preserve pins and checksum; if the ready generation
has changed, report the mismatch and explicitly version the evaluation rather
than silently comparing different sources. Complete per-case source/dependency
and answer review before beginning discovery-survival prototypes.

No production code, database contents, retrieval policy, context cap, prompt or
deployment was changed. No policy merge, commit or push was performed. #254
remains parked, C1 separate and #243 untouched.
