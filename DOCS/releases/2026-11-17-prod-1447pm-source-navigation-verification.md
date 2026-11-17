---
title: "Production verification: Source Navigation API at e958052"
date: 2026-11-17
type: release-record
status: proposed
summary: "Codex verified deployed HTTP source navigation and preserved corpus from Windows. Container OCI/Gradio revision inspection and original Compose timeout logs remain pending SSH access; operational completion awaits owner review."
tags: [release, production, source-navigation, verification, issue-379, pr-380]
related:
  - "[Implementation PR #380](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/380)"
  - "[Issue #379](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/379)"
  - "[API contract](/DOCS/architecture/source-navigation-api.md)"
  - "[Implementation verification](/DOCS/test_results/2026-11-16-379-source-navigation-implementation.md)"
  - "[Production release process](/DOCS/deployment/production-docker-compose.md)"
  - "[Execution boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[Raw evidence index](/DOCS/test_results/raw-index.json)"
---

# Production Source Navigation API verification

**Deployed API functional checks pass. Release-attestation evidence is incomplete.**
The owner requested read-only continuation from Windows, explicitly identifying
Codex as the verifier despite the pasted instructions naming Claude. No code
changes, ingestion, fixtures, redeployment, service restarts or configuration
changes were performed. This report records evidence for owner review; it does
not independently declare #379 operationally complete.

## Identity and running services

Verification started **2026-11-17 21:27:45 UTC**, with HTTP checks finishing at
21:27:50 UTC. One read-only SQL health assertion was corrected subsequently as
described under evidence integrity. Requests used the existing Tailscale host
configuration. No credentials or private endpoint addresses are retained here.

| Identity | Observation |
| --- | --- |
| Local checkout | `e9580524a51731184b161745023871e862e4e5bd` |
| GitHub `main`, read independently | `e9580524a51731184b161745023871e862e4e5bd` |
| PR #380 merge commit | `e9580524a51731184b161745023871e862e4e5bd` |
| Four deployed API `/version` results | Same complete SHA |
| Reported release | `prod-2026-11-17-1447pm` |
| Reported application build date | `2026-11-17T19:50:58Z` |
| Ingested target source commit | `9f039c43604b2e96a6f96351e00afa178c9c81f8` |

`ingestion_service`, `vector_store_service`, `llm_service` and `rag_orchestrator`
all returned `200` from `/version`, with the expected SHA, and from `/health`
both before and after the source checks. Gradio returned `200` with its HTML
page. PostgreSQL answered a read-only `SELECT 1`; its server is PostgreSQL 15.15
and `transaction_read_only` was `on` for this connection.

HTTP versions are application self-reports, not independent container/image
attestation. Gradio does not expose the same Foundry `/version` API, so its OCI
revision remains unverified. PostgreSQL uses an upstream image, not the Foundry
application Git revision. Neither individual Docker health states nor all five
application OCI revision labels have been inspected from Windows in this run.

## Existing corpus and complete source

| Target | Observed value, unchanged before/after |
| --- | --- |
| Repository | `f7641840-ba13-5f9d-9ae6-87e1f924709d` |
| Completed ingestion/generation | `8cbedbb9-9ad6-4c63-83f7-2b7d7659f7e5` |
| Generation status | `ready` |
| Source commit | `9f039c43604b2e96a6f96351e00afa178c9c81f8` |
| Original ingestion timestamp | `2026-11-13T14:45:50.933750` (as returned) |
| File/node counts | 967 / 13,458 |
| Corpus inventory | 15 repositories; repository IDs, generation IDs and counts unchanged |

`GET /v1/repos/{repo_id}/source/files` with
`pattern=**/codebase_utils.py` returned the exact stored module path:
`rag_orchestrator/src/retrieval/codebase_utils.py`.

`GET /v1/repos/{repo_id}/source/read` returned `200`,
`complete_file=true`, **274 lines, 10,479 UTF-8 bytes** and matching returned/
whole-source SHA-256:

`f1a037bab5dee68db183b8c9b64ea6e434194ed13a5b6e79719b0f2bc8877bf1`.

Parsing this HTTP-returned text locally found **13 Python functions**, matching
the earlier independently verified stored/Git source. No symbol API was used.
Three range reads (1–100, 101–200 and 201–274) reconstructed the complete text
exactly; per-range hashes, returned bounds and complete/partial flags agreed.

## Isolation, pagination and bounded reads

All **41 live assertions** passed after correcting the SQL-health harness's
row-access mistake. Deliberate error responses are expected successful checks:

| Case | Observed behavior |
| --- | --- |
| Wrong generation on existing target | `409 GENERATION_MISMATCH`, current target generation, no source |
| Unknown repository | `404`, no source or another repository's generation |
| Missing exact file | `404 FILE_NOT_FOUND` |
| Range exceeding 500 lines | `413 READ_TOO_LARGE`, no partial source |
| Start beyond EOF / reversed interval | `416 INVALID_LINE_RANGE` |
| Traversal path | `400 INVALID_REQUEST` |
| Page size 201 | `400` |
| Two one-record discovery pages | Deterministic distinct increasing paths |
| Cursor reused with another filter or repository | `400` |
| Same source path in another existing repository | That repository's distinct generation and source hash |
| Other repository's generation supplied for target | `409`, target source not returned |

For the existing 618,498-byte `codebase_rag/parsers/call_processor.py` in repository
`4a0af55f-b7d2-5206-9881-f164e29f324c`, generation
`a11910a7-88d9-4e0a-85ac-e1b4df68c74f`:

- A complete-file request returned `413 READ_TOO_LARGE` without partial text.
- Lines 1–100 returned 3,457 bytes in **148.256 ms** observed client elapsed time.
- Lines 13,701–13,800 returned 4,589 bytes in **224.985 ms**, with EOF/total line
  metadata indicating 13,800 lines.

These are individual live observations, not repeated benchmarks or latency
guarantees. Production did not receive synthetic 5 MiB source or changed limits
to force scan/query/deadline exhaustion. Those failure modes remain covered by
the isolated integration evidence linked above, not newly measured live here.
HTTP health stayed good after these reads.

## Initial Compose timeout and subsequent recovery

**Owner-reported deployment history:** the initial Compose health wait timed
out, and a later Linux check showed all six containers healthy. This history
must be retained rather than treating the initial deploy command as cleanly
successful or treating its timeout as continuing application unavailability.

**Independently observed later state:** all four API health checks returned 200,
Gradio served its page, PostgreSQL answered its health SELECT, and the deployed
source-navigation endpoints passed the functional checks above.

**Original event evidence still missing:** the deployment command/log, its exact
timeout stage, affected service(s), exit code, configured wait, timestamps and
the Linux Docker inspection showing six healthy containers. No root cause,
recovery mechanism, restart or precise recovery time is inferred. Once SSH or
the existing release record is available, append those facts while preserving
the original timeout outcome.

## SSH access and remaining verification

Tailscale reports the Linux peer online. Windows has no configured `.ssh`
directory or SSH agent available to this session. A noninteractive,
host-key-verified connection attempt to the Linux hostname on port 22 was
refused; no interactive password prompt, host-key acceptance, account change or
SSHD configuration was attempted. The owner was asked for the established SSH
user/port/key or config location and deployment evidence location, without
requesting passwords or private-key contents.

Remaining tasks before claiming the entire requested release verification:

1. Inspect all five Foundry application container/image OCI revision labels,
   including Gradio, and verify the expected SHA; identify PostgreSQL separately.
2. Capture six current Docker health states and confirm production application
   source bind mounts are absent, where the original release record supports it.
3. Read the existing release record/deployment log, recording the initial Compose
   timeout and later recovery as distinct timestamped observations.
4. Return complete evidence to the owner for the operational-completion decision.

No additional ingestion or deployment is needed for the successful HTTP checks.

## Evidence integrity

Captures registered by size and SHA-256 in the
[raw index](/DOCS/test_results/raw-index.json):

- `2026-11-17-380-live-http-verification.json`: 41 HTTP requests and 41 assertions,
  sanitized source metadata/hashes, corpus comparison and read-only SQL health.
- `2026-11-17-380-initial-harness-capture.json`: preserved initial capture whose
  SQL health assertion incorrectly unpacked dict-row keys as positional values.

Only that SQL SELECT was repeated with explicit named columns. Its actual result
confirmed read-only PostgreSQL health; HTTP tests were not rerun to replace an
unfavorable outcome. No application failure was diagnosed from this harness
mistake. Source bodies, URLs containing host addresses and credentials are not
retained in either capture. No application code changed during verification.
