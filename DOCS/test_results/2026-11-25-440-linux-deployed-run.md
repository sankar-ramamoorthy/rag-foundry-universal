---
title: "#440 verification on the Linux dev host: product routes over HTTP, real models, two repositories"
date: 2026-11-25
type: test-results
status: current
summary: "Deployed-host pass of the #440 verification plan, run from a Windows machine over HTTP against the orchestrator's product routes (build 6538e93, equal to main). Steps 1-7 and 10 pass on two repositories: 24 of 24 ranged citations read back to the same interval, none differed from their passage beyond whitespace, and the no-range citations are the known Markdown and TypeScript-declaration gaps. Steps 8, 9 and 11, and every browser step, were not run by the agent: the frontend port is bound to localhost and unreachable from here, and two steps mutate the deployed stack. The run found a UI defect (Orient limits listed twice, #453, fixed in #454)."
tags: [evaluation, results, frontend, deployment, issue-440, development-diagnostic]
related:
  - "[Issue #440](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/440)"
  - "[Verification plan](/specs/016-product-frontend/verification-plan.md)"
  - "[Local run report](/DOCS/test_results/2026-11-24-440-frontend-first-release.md)"
  - "[Agent execution boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #440 on the Linux dev host (HTTP, product routes)

**Evidence class: development measurement (ADR-054).** Two repositories,
author-chosen questions, a development stack (the owner has said the Linux host
is a development machine, not production). Read-only apart from the model
calls that Ask makes and the ingestion the owner ran beforehand. No host
addresses or credentials are recorded.

## How this was run, and what it is not

- **From where:** a Windows machine, over HTTP, against the already-running
  services. Nothing was deployed and nothing on the host was changed, in line
  with [the deployment boundary](/DOCS/deployment/agent-execution-and-verification.md).
- **Through what:** the orchestrator's `/v1/product` routes directly. The
  frontend container publishes its port on `127.0.0.1` (the #438 decision), so
  the frontend origin could not be reached from this machine. Therefore no
  browser step and no check of the frontend's path allowlist was run by the
  agent.
- **Not run by the agent, by design:** step 8 (forcing a generation change
  re-ingests, which mutates the deployed database) and step 9 (stopping the
  orchestrator is an operator action).
- **Reported by the owner, not verified by the agent:** the owner pasted the
  rendered page text from the frontend on this host. It shows the repository's
  generation, commit and index time, the Overview, an Ask box and file search.
  Its numbers (for example "Files indexed: 72 of 101") match what the API
  returned. It is what exposed finding 1 below.

## The four SHAs

| What | SHA |
| --- | --- |
| Local checkout used to run the checks | `6538e93c6aa4a678ff4ee5607465038f19792aed` |
| `main` HEAD at the time | `6538e93c6aa4a678ff4ee5607465038f19792aed` |
| Deployed runtime (`/version`, all four services: orchestrator, ingestion, vector store, LLM) | `6538e93c6aa4a678ff4ee5607465038f19792aed`, built 2026-11-24T22:19:42Z, release `prod-2026-11-24-1718pm-front` |
| Ingested source: `raythurman2386/fastapi-react-starter` | `eaebfb16a67577c47af643f8e280502c7074172d` (generation `03b5e352-1c36-490c-a41e-92e6874d6a6f`) |
| Ingested source: `sankar-ramamoorthy/mealie` | `1624c22bf70988c7fe404ad586e2f9689f77748d` (generation `eb171cd9-2c25-4d86-a7f9-96664435c740`) |

`/version` is the services' self-report, not an attestation. Runtime settings
that are not exposed over HTTP (for example the model digests and retrieval
defaults) are unknown. The answering model reported by the service was
`ollama/Qwen3:4b`. `GET /v1/product/capabilities` reported
`{"ask": true, "investigate": false}`, as expected before the Investigate
settings are populated.

## The ingestion that was checked first

The owner ingested `fastapi-react-starter` through Gradio on the host. Before
these steps the database was inspected read-only (the owner's inspection
script's connection, SELECT only): one attempt, `completed` in about 10 minutes
40 seconds; 947 nodes and 804 chunks, all in one generation, all 1024-dimension
vectors, no nulls; 920 graph edges with none dangling or crossing repositories;
every node that has text has a chunk. The file tree at that commit (119 files)
reconciles with the inventory (101 non-hidden files indexed, 18 hidden paths
skipped by design). The database is at migration head
`20261121_node_source_span`.

## Results by step

| # | Step | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Select repository; readiness | **Pass** | `readiness` returns the generation and the commit for both repositories; the commit is recorded here (a git ingest), unlike the local-path run. |
| 2 | Overview | **Pass** | Orient returns `coverage: partial`, 72 of 101 files indexed for the starter, with the reported gaps and heuristic fields; Mealie 1,094 of 1,727. Finding 1. |
| 3 | Locate | **Pass** | `auth.py` returned 3 candidates, all `verified_complete` definitions. The glob `**/*.tsx` returned 20 files with a cursor; page 2 kept the pattern and repeated no file. Note: the glob `*.tsx` matches nothing, because a glob is anchored to the repository root (finding 4). |
| 4 | Ask | **Pass** | Six questions, 14.6 to 47.4 seconds, each answer pinned to the deployed generation with the ingested commit in its envelope. |
| 5 | Ranged citations read back | **Pass (HTTP)** | 24 of 24 ranged citations (13 starter, 11 Mealie) read back through `/source` with the same start and end lines and a self-consistent digest. Browser highlighting was not run. |
| 6 | Citation without a range | **Pass (HTTP)** | 16 citations (8 per repository) carried no range, each with the reason `artifact range not verified`: Markdown files and TypeScript component declarations. Browser display was not run. |
| 7 | Range yield | **Info** | See below. |
| 8 | Generation change while a result is open | **Not run** | Mutates the deployed database. Offered to the owner. |
| 9 | Orchestrator unavailable | **Not run** | Operator action. |
| 10 | Error contracts | **Pass** | On both repositories: start beyond EOF and inverted interval give `invalid_range`, 900 lines gives `resource_limit`, a missing path `not_found`, another generation `stale`, a non-UUID repository `invalid_request`; an Ask for another generation returns `stale` and runs nothing. |
| 11 | Other API paths through the frontend origin | **Not run** | Frontend origin unreachable from here. |
| 12 | Gradio alongside | **Partial** | Gradio answers (`/` and its API info return 200) next to the rest of the stack. A question was not put through Gradio in this run; the owner has used it to ingest. |

### Step 7: range yield, and why it is not the #416 figure

| Repository | Citations with a range | By type |
| --- | --- | --- |
| `fastapi-react-starter` | 13 of 21 | Python 5/5, TSX 8/12, Markdown 0/4 |
| `mealie` | 11 of 19 | Python 10/10, TypeScript 1/1, Markdown 0/8 |

The #416 report counted 18 of 19 on three different Mealie questions. These
are not comparable: the questions differ, and one question in each set asks
about documentation, which draws Markdown passages, and Markdown citations
carry no range (issue #430). All 11 non-Markdown citations on Mealie carried a
range. The four TSX citations without a range are component declarations
(issue #417). No regression is indicated, and no improvement is claimed.

### Passage digest versus the read-back text (24 ranged citations)

15 byte-identical, 6 identical except for the final newline, 3 identical after
stripping leading and trailing whitespace, 0 different. A citation's passage
digest and a source read's digest describe slightly different payloads, as the
API assessment noted; the UI highlights the returned interval and does not
claim digest equality.

## Findings

1. **Orient lists each gap twice (found in the owner's pasted page).** The
   server's envelope already carries one note per gap and the panel added the
   gaps again with their paths. My earlier fixture did not carry the server's
   real shape, so no test saw it. Issue #453, fixed in PR #454 with regression
   tests that fail against the old code. Not yet deployed.
2. **The deployed build equals `main`** on all four services, so these results
   describe `main` as of PR #452.
3. **The frontend is unreachable from other machines by design** (localhost
   bind). A browser run needs an SSH tunnel or an operator-run pass on the host.
4. **Glob anchoring.** `*.tsx` finds nothing and `**/*.tsx` finds the files,
   because a glob is matched against the full path. The placeholder text shows
   `src/**/*.ts`, but a user typing `*.tsx` gets an empty result. Not filed;
   noted for the owner.

## Not verified

- Any browser behavior against the deployed frontend, including highlighting,
  the stale banner and rerun, and the unavailable-service message (#450).
- Steps 8, 9 and 11 (above).
- Investigate against the real service or any model: the mode is off here and no
  run was made.
- Markdown ranges and Markdown source reads (#430), and any audience beyond a
  single local user.

## Status of #440

Not closed. The HTTP half of the deployed pass is green. The browser half and
steps 8, 9 and 11 need either a tunnel to the frontend or an operator-run pass
on the host, and the owner can decide whether to accept the local browser run as
covering the UI behaviors.
