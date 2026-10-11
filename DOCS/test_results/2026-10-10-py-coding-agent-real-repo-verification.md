---
title: "Python coding agent re-ingestion and cross-file retrieval verification"
date: 2026-10-10
type: test-result
status: complete-with-retrieval-failures
tags: [repository-intelligence, ingestion, evaluation, cross-repository]
related:
  - "[Current status](/DOCS/status.md)"
  - "[Issue #240 frozen protocol](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
---

# Python coding agent re-ingestion and cross-file retrieval verification

This is an exploratory test of a different repository. Its results do not
change the 11/11 frozen Issue #240 result for `rag-foundry-universal`.
The [raw HTTP responses and traces](/DOCS/test_results/2026-10-10-py-coding-agent-real-repo-query-evaluation.json)
contain four initial questions and seven diagnostic follow-ups. Each request
used `top_k=10`, `rerank=false`, and the deployed orchestrator at
`f344bd58ffde5d98f4993bc0a27192b50c8decc3`. Model-generated responses
reported `ollama/Qwen3:4b`; the structured architecture answer did not call
the model. All 11 requests had matching before/after ready-generation reads
and a matching RAG response generation. These are single exploratory
responses, not a preregistered score or repeated reliability estimate.

## Ingestion and source integrity

Selected repository: `sankar-ramamoorthy/py-coding-agent`, repo ID
`863e770d-651e-5bc5-83d1-a1409693e707`. The current generation is
`24f827d7-a33b-45f7-93f4-ff6e5eaf3856`, an incremental child of
`f1499ec5-c35e-4497-99b3-ebf1ff6d4e05`, and reports source commit
`f854303e6e44ff95d94792d24868442a28080ba2`. The ingest status is
`completed`; its progress endpoint reports `nodes_processed=2286` of 2286.
The ready graph export has 3,388 nodes and 4,606 relationships: 2,124 CALL,
2,023 DEFINES, 376 IMPORTS, 48 OVERRIDES, 27 INHERITS, and 8 DOCUMENTS.

I checked out the exact source commit read-only. It has 340 tracked files.
ORIENT and the graph agree on 288 represented file paths: 277 indexed and
11 non-indexed. The other 52 tracked paths are hidden configuration/skill
trees or `.gitkeep` placeholders. All 99 tracked Python files have graph
paths. Local `ast.parse` succeeded for all 99, and all 573 top-level
classes/functions and immediate methods checked were present by canonical
ID in the graph. This establishes coverage for those definitions; it does
not prove every extracted relationship is resolved correctly. The `/v1/repos`
summary reports `file_count=289` because its distinct-relative-path count
also includes the empty path shared by 542 external-symbol nodes; it is not
evidence of an extra source file.

ORIENT records 99 Python, 178 Markdown, 3 TOML, 1 YAML, and 7 other files;
three `pyproject.toml` manifests; `tests`, `docs`, and `kb-template/docs`;
and the two Compose identities `py-coding-agent` and `datetime-mcp`. Those
service names match the pinned `docker-compose.yml`. ORIENT marks both
entry points unresolved because Compose has no explicit `command:`. The
source Dockerfiles do state the commands: root `dockerfile` runs
`python -m py_mono.main`; `mcp_servers/datetime/Dockerfile` runs
`uv run python datetime_mcp/server.py`. The graph includes both Dockerfiles
as file nodes, but the tested answers did not retrieve their content.

## Retrieval and answer observations

| Case | Mode | Observed result |
| --- | --- | --- |
| A1, architecture and entry points | Repository Overview, claim and structured on | Correctly states two Compose identities and their dependency, but does not supply the requested Dockerfile entry points. The structured result labels both components `external_container` and scopes itself to Compose evidence. |
| R1, CLI to tool result | Normal RAG | Incorrectly attributes the active agent loop to `agent_backupv1.py` and says it invokes `tool.func(**args)`. Current `main.py` imports `Agent` from `agent.py`, whose `Agent.run` calls `tool.run(**args)` and appends the result to memory before the next LLM step. The current method was not retrieved. |
| R2, `/provider` flow | Normal RAG | Cites a specification, issue note, and ADR, but no current CLI, agent, session, or provider-registry implementation. The answer omits the concrete `start_cli → Agent._handle_special_command → SessionManager.switch_provider → get_provider → Agent.run` path. |
| R3, dynamic tool worker | Normal RAG | Gets the broad static-discovery/worker idea from documentation, but wrongly says `run_skill_safe` invokes dynamic tools. Current `tool_loader.py` builds a worker-backed `Tool` proxy; `worker.py` imports and runs the module in the subprocess. No current implementation source was cited. |

Three explicit-path follow-ups for R1-R3 used Repository Overview mode with
claim selection and structured answers on, canonical selection off. All
three returned **zero sources** and false evidence-absence answers. Their
retrieval plans recorded `evidence_obligation=current_structure`, removed
all retrieved passages as `orient_inventory_authoritative_for_structure`,
and left zero final-context tokens. Some named code methods had reached
vector retrieval or graph expansion before this exclusion. The answers
claimed the `py_mono` paths were absent, despite those paths and methods
being present in the pinned graph. This is a confirmed routing/authority
error for code-flow questions in Repository Overview mode. It is separate
from the natural-language seed selection failures above.

Two exact-path follow-ups in Normal RAG mode retained some evidence but did
not solve source authority. R1 again omitted the current `Agent.run` method
and answered mainly from an older ADR. R3 included `tool_loader.py` yet
incorrectly repeated an old audit claim that `load_dynamic_tools` imports
generated modules in the agent process. At this commit it performs static
AST checks/metadata extraction, while `worker.py` imports the module in a
subprocess on invocation. A separate direct Dockerfile question answered
with `docker compose up` rather than either Dockerfile `CMD` and cited no
Dockerfile. These follow-ups are diagnostic variants, not replacements for
the initial questions.

The historical diagram miss also repeats on this generation. An explicit
question beginning “According to `docs/architectural-diagram.md`” cited
`docs/design.md` and a brainstorm note, then said the diagram content was
unavailable. The traced diagram sections were neither vector seeds nor
graph-expanded candidates. Yet the diagram is present in the graph and a
generation-fenced `/v1/vectors/search-by-doc` read returned four chunks for
one requested section. The current `Agent.run`, `load_dynamic_tools`, and
`run_dynamic_tool_in_worker` methods likewise had generation-fenced vector
chunks. The observed misses therefore do not establish extraction or index
absence; their loss stages vary by query.

## What the graph can and cannot connect

The pinned graph resolves `py_mono/main.py#main` CALL
`py_mono/ui/cli.py#start_cli`. It records `start_cli` calling
`EXTERNAL_SYMBOL:agent.run`, rather than resolving the typed `Agent` receiver
to `py_mono/agent/agent.py#Agent.run`. The same receiver limitation appears
for `Agent._handle_special_command` calling
`EXTERNAL_SYMBOL:self.session_manager.switch_provider`. The graph has
individual method nodes and many cross-file edges, but those two critical
handoffs are not traversable as exact method-to-method CALL edges. Source
inspection can still establish the flow; current retrieval did not reliably
assemble that evidence.

## Decision

Ingestion integrity and definition coverage pass the checks above. The
repository-specific architecture, function-relationship, and execution-flow
answers are **not yet reliable** on this new generation. The next bounded
investigation should separate (1) overview-intent routing that excludes
code evidence, (2) exact named-source discovery and survival, (3) current
implementation authority over historical plans/audits and backup code, and
(4) unresolved receiver CALL edges. No retrieval setting, code, ingestion,
or frozen #240 result was changed during this evaluation.
