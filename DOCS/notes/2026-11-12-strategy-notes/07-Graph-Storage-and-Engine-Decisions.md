---
title: "Graph Engine Reassessment — Need Before Database"
date: 2026-11-12
type: architecture-exploration
status: deferred-decision
project: RAG-FOUNDRY-UNIVERSAL
tags: [graph-database, postgres, pgvector, helixdb, grafeo, apache-age, storage]
aliases: ["Graph Database Decision Revisit"]
authority: "Product landscape discussion and evaluation proposal; no selection or live engine benchmark"
related: ["[[02-Retrieval-Strategies-and-Planning]]", "[[03-Evidence-Driven-Investigation-Loop]]", "[[08-Experiments-Gates-and-Open-Decisions]]"]
---
# Graph Storage and Engine Decisions

## Historical reasoning revisited

The project previously considered using a dedicated or alternative graph engine instead of—or alongside—PostgreSQL. Candidates discussed included Neo4j, Rust-based HelixDB, Grafeo, SurrealDB, and PostgreSQL's Apache AGE extension. The prior reason not to migrate was **maturity, dependency/API churn, operational overhead and reversibility**, not a proof that PostgreSQL graph traversal is always optimal.

## Why revisit now?

If future retrieval becomes a bounded investigative loop with repeated neighborhood traversals, path searches and vector/lexical filtering within structural neighborhoods, access patterns may differ from the existing single-shot vector + graph expansion workflow. A graph engine could eventually help with query expressiveness, round-trips, index combinations and traversal performance.

But current test failures are **not sufficient grounds for migration**:

| Observed problem | Database replacement alone? |
| --- | --- |
| Relevant implementation ranks thousands below other chunks | No |
| Code and markdown share broad `source_type` | No |
| Example script outranks a library definition | No |
| An instance call resolves to an external placeholder | No; extractor/resolver first |
| Useful evidence dropped at context allocation | No |
| Repeated graph traversals too slow at scale | Possibly; benchmark |
| Structural + lexical + vector queries require costly coordination | Possibly; benchmark |

A different database stores and searches relationships; it does not automatically infer dynamic receivers or correct erroneous canonical links.

## Candidate engines — evaluation questions, not endorsements

| Candidate | Why consider | What must be independently verified |
| --- | --- | --- |
| Current PostgreSQL + pgvector | Already deployed; durability and operational knowledge | Real traversal plans, path query costs, generation-safe joins |
| Apache AGE | Graph query language within PostgreSQL | Supported PostgreSQL versions, extension lifecycle, operational constraints |
| HelixDB | Rust-based graph/vector/lexical integration claim | Exact license/version, API stability, persistence, indexing, community longevity |
| Grafeo | Rust embedded/server graph approach | Exact current maturity/license, bindings, graph import and update behavior |
| SurrealDB | Multi-model and graph query flexibility | Core license obligations, operational maturity, compatibility, query semantics |
| Neo4j | Mature graph query tooling | Licensing edition, second service overhead, migration/cost |

This note intentionally avoids asserting current release numbers as permanent facts; verify versions, licenses, and sustained maintenance immediately before any formal selection.

## Proposed engine-independent contract

An investigation layer should request: `neighbors(canonical_id, relation, direction, depth, limits)`, `find_paths(start,end,...)`, `get_node`, `resolve_symbol`, `lookup_route`, and generation-verified evidence fetches. Use adapters to isolate query language and storage representation. Avoid promising a seamless backend swap: transaction consistency, graph/vector identity, batching and failure semantics differ.

## Minimum benchmark before a choice

- Same frozen canonical graph and exact call edges across engines.
- Same graph query semantics and edge direction.
- Realistic workloads: 1-hop/3-hop fan-out; endpoint-to-storage path; reverse caller lookup; neighborhood-filtered lexical/vector candidate retrieval.
- P50/P95 latency, memory/CPU, ingestion/import, incremental updates and delete/rebuild costs.
- Recovery and schema evolution; correctness under generation switches.
- Operator costs and installation complexity on the actual Linux host.
- Robustness against unresolvable dynamic call edges (report unknown rather than invent paths).

## Provisional position

**Keep PostgreSQL/pgvector as the control.** Design and measure the evidence-retrieval interface and workloads first. Re-evaluate graph engines only after demonstrating an actual storage limitation rather than an extraction/planning/delivery defect. No new database is approved in this conversation.
