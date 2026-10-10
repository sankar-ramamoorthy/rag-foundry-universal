---
title: "Issue #240 isolated typed-fact experiments for Q2–Q4"
date: 2026-10-04
type: test-result
status: complete
tags: [repository-overview, evaluation, typed-facts]
related:
  - "[Frozen protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Prior matched comparison](/DOCS/test_results/2026-10-04-issue-240-corrected-corpus-authority-comparison.md)"
---

# Q2–Q4 typed-fact experiments

## Pin and intervention

All requests selected repository `f7641840-ba13-5f9d-9ae6-87e1f924709d`,
ready generation `f873147c-a1d1-4891-bb98-972672db8e9a`, and source SHA
`7a805d5b3cee031c44fbe0d9b8048065ce8ef039`. The before/after generation
reads matched for every request. The candidate was a local orchestrator using
the existing production ingestion, vector, and LLM services; no corpus data
was changed. The model was `ollama/Qwen3:4b`, reranking was off, `top_k=10`,
and the retrieved-context budget was 4096 tokens. The prior claim-specific
selector stayed enabled in the candidate. One extra default-off typed-fact
mode was enabled per arm; no general authority or retrieval ranking was
changed.

The graph had 9,068 nodes. It supplies observed paths, `__init__.py` markers,
and 15 `CALLS_SERVICE` edges, whose recorded evidence is heuristic
co-occurrence. It does not supply datastore edges or exposed host ports. The
new formatter separates whole-repository ORIENT counts from per-service
indexed source counts, uses distinct Compose service identities rather than
declaration count, and preserves `not established` for absent package markers.

| Arm | Latest trace | Result |
| --- | --- | --- |
| Q2 service table | `337397b85e41408b98d775571d0e027f` | Partial: correct 13 graph-observed top-level directories and six service identities; omitted the available per-service Compose, Dockerfile, manifest, test, and language facts. No false universal package/test claim in this run. |
| Q3 package markers | `2f256d0011b24b3f87019b75d56b4d41` | Partial: correctly used 16/6/7/8 observed markers for the four marked services and recognized `gradio/`; then converted `not established` to "no Python packages exist" and treated absent `postgres/` path as proven nonexistence. |
| Q4 typed edges | `230e6fc233ae4418b3e7f200dd64a362` | Fail: separated five application services from one database in its table, but still described all six as communicating via HTTP, invented PostgreSQL port `N/A`, and asserted unsupported network/provider generalizations. |

Raw response records: [Q2 first](/DOCS/test_results/2026-10-04-issue-240-q2-service-table.json),
[Q2 corrected](/DOCS/test_results/2026-10-04-issue-240-q2-service-table-v2.json),
[Q3 first](/DOCS/test_results/2026-10-04-issue-240-q3-package-markers.json),
[Q3 directory correction](/DOCS/test_results/2026-10-04-issue-240-q3-package-markers-v2.json),
[Q3 explicit marker counts](/DOCS/test_results/2026-10-04-issue-240-q3-package-markers-v3.json),
and [Q4](/DOCS/test_results/2026-10-04-issue-240-q4-architecture-edges.json).

## Failure localization by claim family

**Q2.** The first table used language-classified source files to determine
directory presence. That mislabeled `gradio/` as unestablished even though its
Dockerfile and manifest paths occur in the graph. After correction, the model
reported directories and service count accurately but omitted most supplied
row facts. This is now a combination of an initially bad derivation and
incomplete synthesis. The table did eliminate the earlier Rust-count and
"all services have tests/packages" errors in the measured answers.

**Q3.** Explicit package paths fixed the earlier inference that
`vector_store_service` lacks a package because ORIENT lists no pyproject there.
An `__init__.py` establishes a traditional package; a missing marker does not
prove absence of all Python packages, including namespace packages. Even with
that instruction and computed marker counts, generation turned unknown into
"no Python packages exist." This is a generation/qualification failure after
the required evidence became available.

**Q4.** The typed formatter listed application-to-application HTTP candidates
separately from service-to-datastore, Compose declarations, and exposed ports.
The graph's `CALLS_SERVICE` edges are heuristic, and no port value comes from
the graph. The answer nevertheless used `N/A` for PostgreSQL's port and
flattened the service communication story. The retrieved README architecture
and service URL config survived final context (five chunks, 1,993 tokens after
budget). The specific error is synthesis over mixed relationship types, with
an unestablished port filled in; it is not missing architecture retrieval.

The candidate's extra policy/fact envelope remains outside the 4096-token
retrieved-context budget. Its contribution to these errors is plausible but
unmeasured; no causal claim is made from this run.

After the measured calls, the formatter's ambiguous `source directory` label
was split into `repository directory` (any graph-observed path) and `indexed
source directory` (a language-classified source path). This semantic cleanup
was unit-tested but not given another live answer-quality run; the raw traces
above describe the measured versions, not a claim that the final local
formatter passes.

## Gate and next bounded tests

The #240 frozen quality gate is **not met**. These runs cover only Q2–Q4 and
do not re-run the full 11-case set or controls, so they cannot establish a
regression-free candidate. The typed-fact mode remains default off; do not
merge it as a #240 fix or deploy it.

The next Q2 test should measure a short, service-keyed answer template or a
field-completeness check against each row. The next Q3 test should require an
explicit unknown value in a structured output field and reject prose that
turns unknown into absence. The next Q4 test should parse ports and deployment
edges from generation-pinned Compose content, if that content can be exposed
by a read-only API, then validate answer relationships by type before prose
generation. These are separate tests, not another broad authority policy.

Local verification: 298 orchestrator unit tests passed (22 deselected),
focused typed-fact tests passed, Ruff passed, and Pyright reported no errors.
