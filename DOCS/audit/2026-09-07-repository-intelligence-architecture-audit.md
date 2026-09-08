---
title: "Repository intelligence: architectural fit, evidence gaps, and design options"
date: 2026-09-07
type: audit
status: complete
tags: [audit, architecture, repository-intelligence, provenance, retrieval]
source_commit: 9044d68a5c1821854aaac9089d186f177ab5f937
related:
  - "[[00-Audit-Overview]]"
  - "[[07-Roadmap]]"
  - "[[2026-09-07-current-state-retrieval-audit]]"
  - "[[../notes/20260906-repository-understanding-trace-and-structural-artifacts]]"
  - "[[../adr/ADR-030-unified-artifact-graph]]"
  - "[[../adr/ADR-031-canonical-identity-model]]"
---

# Repository-intelligence architecture audit

Scope: assess the [exploratory note](../notes/20260906-repository-understanding-trace-and-structural-artifacts.md) against current source and [roadmap](07-Roadmap.md). This report proposes options and investigation gates, not accepted architecture or scheduled work. No code, configuration, roadmap, issues, or existing documents were changed; no commit was made.

Evidence: source inspection plus an in-memory probe using the existing Python extractor and GraphAssembler on the current `routes.py` and `service.py`. No new extractor/workflow was implemented. The note's user-visible failures remain historical observations; the earlier [retrieval audit](2026-09-07-current-state-retrieval-audit.md) contains separately identified production spot-checks. No new live answer-quality evaluation was conducted here.

## Executive summary

- **ORIENT is the strongest capability candidate.** A deterministic repository inventory addresses the note's actual-directory and fixture-subject failures directly. The current graph only inventories successfully extracted, supported files; it is not a complete filesystem map. [RepoGraphBuilder.build/_walk_repo](../../ingestion_service/src/core/codebase/repo_graph_builder.py).
- **Keep one factual representation with multiple views.** The unified artifact graph can accommodate structural facts, but a giant embedded `REPO_STRUCTURE` document would duplicate module paths and remain vulnerable to chunking/top-k/context caps. A structured inventory with an on-demand text view deserves comparison with persistent graph expansion. [RepoGraph](../../ingestion_service/src/core/codebase/repo_graph.py), [hybrid_retrieve/run_rag](../../rag_orchestrator/src/core/service.py).
- **A static architecture map is feasible in bounded subsets; a universal runtime architecture graph is not already available.** Compose declarations, router registration, and resolved configuration support some explicit relationships. Deployment dependencies, package ownership, dynamic HTTP targets, and actual execution must remain distinct. [Compose](../../docker-compose.yml), [route registration](../../rag_orchestrator/src/api/v1/main.py), [service configuration](../../rag_orchestrator/src/core/config.py).
- **TRACE needs richer evidence, not just deeper BFS.** Current CALL edges represent possible calls, omit HTTP request arguments, and lose confidence/call-site metadata at graph export. Service-local import roots can already prevent a direct call from resolving. [PythonASTExtractor.visit_Call](../../ingestion_service/src/core/extractors/python_extractor.py#L226), [GraphAssembler._resolve_calls](../../ingestion_service/src/core/codebase/graph_assembler.py#L527), [get_full_graph_for_repo](../../ingestion_service/src/core/db_utils.py#L220).
- **IMPACT is closest for candidate callers/importers; “will break” is unsupported.** Tests, documentation mentions, cross-service contracts, runtime dispatch, and revision comparison need evidence beyond existing adjacency. [traversals](../../rag_orchestrator/src/retrieval/codebase_queries.py), [DOCUMENTS matching](../../ingestion_service/src/core/codebase/graph_assembler.py#L754).
- **Authority and snapshot identity are foundational.** Repo-scoped retrieval preserves corpus membership, but the generation payload does not establish the selected repository as the subject or distinguish source roles. Structural inventory and bounded trace workflows fit existing boundaries; a general autonomous investigator is a separate capability. [run_rag](../../rag_orchestrator/src/core/service.py#L378), [build_messages](../../llm_service/src/core/prompts/__init__.py#L26).

## Current architectural fit: what exists and what is missing

| Layer | Existing implementation | Consequence for these ideas |
|---|---|---|
| Extraction | Suffix registry for Python, Markdown, TS/JS; language-neutral `ExtractionResult`, `SymbolRecord`, imports, calls, inheritance records | Good extension seam, but no inventory/configuration/endpoint records or full-repository manifest parser. [builder](../../ingestion_service/src/core/codebase/repo_graph_builder.py), [IR](../../ingestion_service/src/core/codebase/ir.py) |
| Graph assembly | One assembler resolves identity, DEFINES, IMPORTS, INHERITS, OVERRIDES, CALL, DOCUMENTS | New mechanically supported relations can follow the same ownership model; language-neutral IR does not itself supply framework or deployment semantics. [GraphAssembler.assemble](../../ingestion_service/src/core/codebase/graph_assembler.py#L71) |
| Persistence | `DocumentNode` keyed by `(repo_id, canonical_id)`; textual node type via `doc_type`; relationships carry JSON metadata | Flexible foundation, but no persisted node `artifact_type` or generic node metadata column; emitted node metadata is not generally persisted. This matters for the note's proposed roles and derivation lineage. [node model](../../shared/models/document_node.py), [persist_graph](../../ingestion_service/src/core/codebase/codebase_persistence.py#L79) |
| Retrieval | Vector seeds, typed-edge BFS, canonical lookup, chunk fetch, labeled context, one generation phase | Reusable primitives for specialized modes, not an evidence-sufficiency loop. [service](../../rag_orchestrator/src/core/service.py), [selector](../../rag_orchestrator/src/retrieval/traversal_selector.py) |
| Plan/provenance | `RetrievalPlan` contains document sets and one expansion reason per document; CALL metadata includes confidence and source lines | No ordered trace, multiple-path evidence, coverage obligations, or snapshot-aware reconciliation. Repo RAG repackages all fetched docs as plan seeds with empty expansion metadata; graph export drops edge metadata. [plan](../../shared/retrieval/retrieval_plan.py), [run_rag](../../rag_orchestrator/src/core/service.py#L411), [graph export](../../ingestion_service/src/core/db_utils.py#L220) |

### Ownership and ADR compatibility

The natural division remains: **ingestion derives and persists facts; orchestration selects/assembles evidence over HTTP; llm_service owns synthesis; UI renders results**. Structural facts do not require another database or ingestion-time LLM. This fits [ADR-030](../adr/ADR-030-unified-artifact-graph.md) and [ADR-031](../adr/ADR-031-canonical-identity-model.md), subject to explicit identity rules for synthetic artifacts.

Two guidance claims cannot be used as implementation facts:

- `CLAUDE.md` says ingestion owns all DB access exclusively. In code, ingestion uses [SQLAlchemy](../../ingestion_service/src/core/database_session.py), while vector_store_service uses [psycopg directly](../../vector_store_service/src/core/vectorstore/pgvector_store.py); [Compose](../../docker-compose.yml) points both at the same Postgres database. A truthful architecture map should show both accesses, distinguishing graph persistence from vector operations. This does not justify giving orchestration direct DB access.
- [ADR-038](../adr/ADR-038-pipeline-construction-ownership.md) requires a core pipeline factory, but current [_build_pipeline](../../ingestion_service/src/api/v1/codebase_ingest.py#L39) still constructs dependencies in the API module; the specified factory file is absent. That is existing drift, not a reason to introduce another constructor for structural ingestion.

Accepted ADRs constrain future design, but their old implementation descriptions are not authoritative. The proposed ADR-032/045 and historical roadmap sections must also be read with their statuses. OKF front matter, wikilinks, and the canonical DOCS hierarchy are intentional organization and require no parallel knowledge tree.

## Findings by capability

### 1. Repository structure as a first-class artifact

**Mechanically available, not currently captured completely.** The repository worker has a real checkout/local path; `_walk_repo()` sorts directories/files, prunes dot/ignored directories, and yields only supported suffixes. Parse/read failures are silently skipped. Dockerfiles, Compose YAML, TOML/JSON manifests, other unsupported files, and empty directories never become inventory entries. Git-ignore policy is not a complete inventory contract either. A list derived from current graph paths must be labeled **indexed files**, not “the actual repository tree.” [worker](../../ingestion_service/src/api/v1/codebase_ingest.py#L141), [walker](../../ingestion_service/src/core/codebase/repo_graph_builder.py#L113).

Partial structure exists in `RepoGraph.files`, module canonical IDs, `DocumentNode.relative_path`, and module naming conventions. Directory ancestors can be derived from indexed paths; Python `__init__.py` and TS `index.*` affect module names, but directories are not equivalent to packages. `/v1/repos` exposes identity, ingestion, node/file counts; its file count is distinct persisted paths, not a checkout census. [RepoGraph](../../ingestion_service/src/core/codebase/repo_graph.py), [module conventions](../../ingestion_service/src/core/codebase/module_conventions.py), [RepoSummary](../../ingestion_service/src/api/v1/repos.py), [list_complete_repos](../../ingestion_service/src/core/db_utils.py#L105).

**Avoid duplication.** A second FILE node for each existing MODULE/MARKDOWN_MODULE would duplicate identity and path facts. A textual tree repeats information derivable from containment/path records; a document plus independently maintained graph would create two authorities. Reuse existing file-level identities where applicable, distinguish additional directory/service/package concepts, and derive human-readable views from one inventory. Do not automatically embed every directory or copy all source into an overview.

**Placement if pursued later:** inventory belongs in ingestion while the checkout exists, adjacent to repository walking and before parser eligibility removes files. Manifest/config extraction can produce typed evidence; assembly can then relate source artifacts and structural entities before the existing atomic graph persistence. A rendered overview may be a projection after assembly. Putting this in `IngestionPipeline._chunk`, the LLM service, or a query-time walk of the orchestrator's own checkout would mix ownership or inspect the wrong repository. Git clones are temporary and removed after ingestion. [RepoGraphBuilder.build](../../ingestion_service/src/core/codebase/repo_graph_builder.py#L90), [_background_ingest_repo](../../ingestion_service/src/api/v1/codebase_ingest.py#L141).

**Identity and rebuild implications:**

- `repo_id` comes from a normalized source URL/local path; it is not a commit or a universal identity across every clone location. `ingestion_id` identifies a run. Canonical IDs remain source-structural and must not contain timestamps, content hashes, or ingestion IDs. [identity helpers](../../ingestion_service/src/core/codebase/identity.py), [ADR-031](../adr/ADR-031-canonical-identity-model.md).
- A service declaration can be anchored to its manifest and stable service key. Repository-root, directory, and synthesized-overview identities need an explicit collision-free convention; existing EXTERNAL_* synthetic IDs are precedent, not an approved namespace for every new concept.
- `persist_graph()` replaces all repo nodes/edges and creates new database document UUIDs; graph persistence and subsequent vector embedding are separate phases. Derived references should use canonical identity plus snapshot provenance, not assume document UUID stability or atomic graph/vector publication. Current ingestion does not record a commit SHA. [persistence](../../ingestion_service/src/core/codebase/codebase_persistence.py#L79), [worker](../../ingestion_service/src/api/v1/codebase_ingest.py#L141).
- Future WP-S6 must invalidate inventory summaries and architecture projections when paths, manifests, imports, or source-root mappings change. Unchanged-source rebuilds should reproduce facts and sorted views; incremental results must equal full rebuilds. Snapshot hashes/derivation versions belong in provenance, not canonical identity. [WP-S6](04-Scalability-Plan.md).

**Judgment:** a structured inventory with deterministic views is justified for investigation. Persisting a new embedded document is one storage option, not a prerequisite or a demonstrated solution by itself.

### 2. Architecture graph / architecture artifact

Here “derivable now” means supported by current repository source that a bounded analyzer could inspect; **none of the service-level edge types below is emitted by the current assembler**. A declaration should remain a declaration, not silently become proof of observed runtime behavior.

| Candidate relationship | Mechanical evidence and reliability | Ambiguity / representation |
|---|---|---|
| Repository CONTAINS directory/file/package/service | File membership is high-confidence given an explicit inventory policy. Compose service keys are explicit declarations; package membership needs language/manifest rules. | Existing graph paths cover only indexed files. Directory ≠ package ≠ deployable service. Persist base inventory facts in the unified model or inventory record; derive grouped views. [walker](../../ingestion_service/src/core/codebase/repo_graph_builder.py), [Compose](../../docker-compose.yml) |
| Service OWNS package | Dockerfile COPY, entry command, source-root configuration, manifest scope, and imports provide evidence; directory-name matching alone is weak. | All main Compose builds use root context `.`; `shared/` is copied/mounted into multiple services. Gradio actually runs `ingestion_service/src/ui/gradio_app.py`, copied by [gradio/Dockerfile](../../gradio/Dockerfile). Prefer non-exclusive “includes/uses source” facts until ownership is explicitly declared. |
| Service EXPOSES endpoint | Literal route decorators plus recursively resolved router prefixes and ASGI entry point are high-confidence for this repo's simple registrations. `/v1` + `/rag` mechanically yields `/v1/rag`. | Router inclusion can repeat, be conditional, or use factories/mounts. Current function metadata omits decorators/routes; do not execute an ingested application's code merely to discover them. Framework extraction plus registration evidence can fit the unified graph. [main](../../rag_orchestrator/src/api/v1/main.py), [routes](../../rag_orchestrator/src/api/v1/routes.py), [ingestion router chain](../../ingestion_service/src/api/v1/__init__.py) |
| Service CALLS_SERVICE | An actual HTTP call combined with a resolvable URL base/path/method can establish a possible outbound call. `run_rag` posts to the configured LLM `/generate`; ingestion posts vector batches. | URL declaration alone proves no call. Environment overrides, dynamic paths, external hosts, client wrappers, and unused helpers require qualifications. Call-site/config evidence should underlie a derived service projection. [run_rag](../../rag_orchestrator/src/core/service.py#L447), [HttpVectorStore.add_vectors](../../ingestion_service/src/core/http_vectorstore.py#L114), [URL defaults](../../shared/config/service_urls.py) |
| Service DEPENDS_ON service/package | Compose `depends_on`, dependency manifests, and resolved imports are mechanically extractable within their respective semantics. | Keep deployment/startup dependencies separate from code imports and actual HTTP calls; optional/dev dependencies and unresolved packages differ. Example: Compose makes llm_service depend on vector_store_service, while generation does not call it. Preserve evidence kind rather than flatten all into an unqualified dependency edge. [Compose](../../docker-compose.yml), [llm completion](../../llm_service/src/core/llm_client.py), [import resolver](../../ingestion_service/src/core/codebase/graph_assembler.py#L220) |
| Service USES datastore | DB client construction/operations plus configured DSN target are strong evidence of possible access; both ingestion and vector services have it. | Config is deployment-specific; declared DSNs do not alone prove active use or exclusive ownership. Table-level read/write facts require additional analysis. Store source/config facts and derive the architecture view. [database_session](../../ingestion_service/src/core/database_session.py), [PgVectorStore](../../vector_store_service/src/core/vectorstore/pgvector_store.py) |
| Entry-point relationships | Docker CMD identifies uvicorn application targets or Gradio script; literal route registration identifies handler entry points. | The same `src.api.v1.main:app` string names different apps under different service working directories/PYTHONPATH. CLI scripts, factories, plugin registration, workers, callbacks, and conditional startup need separate evidence. Anchor entry points to deployment/source scope. [rag Dockerfile](../../rag_orchestrator/Dockerfile), [ingestion Dockerfile](../../ingestion_service/Dockerfile), [Gradio Dockerfile](../../gradio/Dockerfile) |

Package layout and manifests are useful evidence, but current instructions overstate their uniformity: this checkout has root, ingestion, orchestrator, LLM, and Gradio `pyproject.toml` files, but no `vector_store_service/pyproject.toml`. Service identity cannot require a manifest in every service directory. Likewise [shared URL configuration](../../shared/config/service_urls.py) is not the sole source: service Settings classes and hardcoded helpers also define URLs, so a single-file scan would be incomplete.

**Judgment:** favor a **derived architecture projection over source-backed facts**, with separate deployment and code views. High-confidence endpoint/service entities can live in the existing graph; inferred groupings can remain query-time overlays until proven useful. A separate canonical architecture database would duplicate identities, provenance, and rebuild logic without supporting evidence.

### 3. Mermaid and architecture rendering

Mermaid is a presentation format, not a new reasoning capability. A deterministic renderer over a selected graph projection gives stable node/edge IDs, reproducible output, and a direct citation for each edge. An LLM can explain or group a supplied subgraph, but any introduced edge must be validated against it or explicitly marked as a hypothesis. “Depends on” and “calls” must remain different visual relationships.

Prefer on-demand rendering initially; persist only a requested export or a cache keyed to source snapshot, projection rules, and renderer version. An export should carry `repo_id`, snapshot/ingestion reference, `derived_from` source/edge IDs, derivation version, omitted/unknown relationships, and any model/prompt identity. The canonical source remains the evidence graph/inventory. Feeding an old generated diagram back as ordinary current implementation evidence recreates the note's contamination problem.

No graph-to-Mermaid rendering stage exists in [run_rag](../../rag_orchestrator/src/core/service.py); generated text today is simply an LLM answer. The [summary endpoint](../../llm_service/src/api/v1/summarize.py#L60) can persist prose through ingestion, but records neither a per-claim evidence lineage nor a diagram snapshot contract. It is not a ready-made authoritative architecture-artifact pipeline.

### 4. ORIENT ME

The note records four different outcomes: semantic ambiguity (“repo structure” → graph schema), subject substitution (`my_test_repo`), unsupported synthesis of a plausible layout after explicit naming, and successful direct-source inspection. These support an inventory/authority investigation; they do not prove all orientation questions fail or that every answer needs an agent. The separately missed diagram document is a discovery failure, not proof of cap loss. [note, sections 3–4](../notes/20260906-repository-understanding-trace-and-structural-artifacts.md).

**Generic top-k cannot guarantee repository-global completeness.** It ranks local similarity, not coverage of directories/services/packages; the existing corpus also excludes many structural source files. It can answer orientation if a complete, suitable overview happens to be retrieved, so it is not logically incapable of every such answer. Increasing top-k does not create a missing inventory, assert the query's subject, or guarantee structural coverage. [hybrid_retrieve](../../rag_orchestrator/src/core/service.py#L231).

Existing `/v1/repos`, canonical lookup, full graph export, path metadata, and language-bearing vector metadata can seed a deterministic **indexed-repository overview** today. A complete overview requires retained inventory/manifests and source scope. A future `repository_overview` mode is justified as an experiment: an explicit request/UI mode or narrow deterministic intent rule can select an inventory-backed plan without an LLM router. Ambiguous “structure” should distinguish filesystem orientation from graph-model explanation, rather than route both to one overview. [repo API](../../ingestion_service/src/api/v1/repos.py), [graph API](../../ingestion_service/src/api/v1/graph.py), [current selector](../../rag_orchestrator/src/retrieval/traversal_selector.py).

The plan should establish selected repo identity and snapshot, enumerate required facets, fetch structural/config evidence directly, and use docs for attributed purpose/design explanations. Missing package ownership or unsupported files should be reported as gaps. An overview document left in the same generic top-k pool would not establish these guarantees.

### 5. TRACE THIS

**Already possible in the primitives:** bounded forward/reverse CALL chains, module IMPORTS neighborhoods, structural DEFINES descent, and inheritance/override neighbors for resolved symbols. Semantic retrieval remains useful to find an entry symbol from a behavior or symptom; exact canonical targets need not depend on vector matching. Current production selection uses first-match regex rules, depth-one traversals from the seed plus depth-two DEFINES anchors, then returns a ranked node set—not an ordered execution trace. [bfs_traversal](../../rag_orchestrator/src/retrieval/codebase_queries.py#L55), [execute_traversals](../../rag_orchestrator/src/retrieval/traversal_selector.py#L163).

**A concrete limit precedes HTTP boundaries.** In the in-memory probe, both current `rag_orchestrator/src/api/v1/routes.py` and `rag_orchestrator/src/core/service.py` were supplied to the existing extractor/assembler. `rag_endpoint → run_rag` became `EXTERNAL_SYMBOL:src.core.service.run_rag` with confidence 0.0. Python module names are derived from repository-relative paths, while the import uses the service-local `src` root. The resolver has no working-directory/PYTHONPATH mapping. Increasing BFS depth cannot repair that missing resolution. The probe also confirmed route-symbol text excludes its decorator, and metadata contains no route path/method; generic decorator CALL records retain no path arguments. [module convention](../../ingestion_service/src/core/codebase/module_conventions.py#L26), [import resolution](../../ingestion_service/src/core/codebase/graph_assembler.py#L288), [Python extractor](../../ingestion_service/src/core/extractors/python_extractor.py#L155).

**Not represented today:** endpoint-to-handler registration edges, request URL/method evidence, caller-site-to-downstream-endpoint binding, service membership, and deployment scope. `CallSite` has callee/receiver/caller/span/metadata, but current Python extraction does not preserve HTTP arguments. The assembler aggregates caller/callee pairs with line numbers and confidence; graph export strips this metadata and `CodebaseGraph` stores only adjacency. Source order of calls is also not execution order through branches, loops, exceptions, asynchronous tasks, or dynamic dispatch. [IR](../../ingestion_service/src/core/codebase/ir.py), [_resolve_calls](../../ingestion_service/src/core/codebase/graph_assembler.py#L527), [export](../../ingestion_service/src/core/db_utils.py#L220), [CodebaseGraph](../../rag_orchestrator/src/retrieval/codebase_queries.py#L32).

**Bug paths and data loss:** a symbol graph can identify candidate functions to inspect, but cannot show which branch ran or which data survived a slice/filter. The prefetch document cap, three-row chunk fetch, and later context budget are implementation operations, not special graph edges. Existing evidence-survival instrumentation helps for known target documents but finalizes before text budgeting and does not prove required passage presence. A static trace must say “possible call path”; an actual execution/data-loss trace requires source reasoning plus runtime/evaluation evidence. [hybrid_retrieve/run_rag](../../rag_orchestrator/src/core/service.py), [evidence_trace](../../rag_orchestrator/src/retrieval/evidence_trace.py), [earlier audit](2026-09-07-current-state-retrieval-audit.md).

**Judgment:** a deterministic, bounded path workflow is a stronger default than generic RAG for explicit symbol traces. It needs path records, edge evidence, scope-aware resolution, and explicit stopping gaps. Behavioral explanation can use semantic retrieval and LLM synthesis after path evidence is assembled; deeper traversal alone is insufficient.

### 6. ASSESS IMPACT

| Question | Current support | Missing for a reliable answer |
|---|---|---|
| What callers may break? | Reverse CALL, with the resolution limitations above | Signature/contract comparison, dynamic dispatch, call-site arguments, snapshot diff; adjacency proves possible exposure, not breakage |
| What imports/packages are affected? | Reverse module IMPORTS | Package/source-root identities, re-export/alias resolution, runtime versus type/dev dependency distinctions; import evidence is lost from graph export |
| What tests are relevant? | Test functions are ordinary code artifacts; a resolved test CALL can be traversed | Test-role metadata, fixture/setup/dependency edges and optional observed coverage; no TESTS/COVERS model currently establishes relevance or completeness |
| What docs/specs mention the symbol? | DOCUMENTS edges exist for exact heading-name matches | General prose/code-reference and doc-to-doc REFERENCES/MENTIONS edges, ambiguity handling, source roles; production selector does not use DOCUMENTS |
| What downstream services are affected? | No first-class service graph | Service/endpoint/contract edges, caller-to-endpoint binding, deployment scope and change semantics |

Sources: [reverse traversals](../../rag_orchestrator/src/retrieval/codebase_queries.py), [selector](../../rag_orchestrator/src/retrieval/traversal_selector.py), [import/call/doc assembly](../../ingestion_service/src/core/codebase/graph_assembler.py), [IR](../../ingestion_service/src/core/codebase/ir.py).

DOCUMENTS needs particular caution: `_link_docs_to_code()` uses `SymbolTable.lookup()`, whose ambiguous-name behavior chooses the lexicographically smallest canonical ID, then labels the edge confidence 1.0. A deterministic match is not necessarily the correct referent. References in arbitrary prose or wikilinks are not extracted by [MarkdownSectionExtractor](../../ingestion_service/src/core/extractors/markdown_extractor.py); even module targets advertised by ADR-048 are not indexed by `build_symbol_table()`. [SymbolTable.lookup/build_symbol_table](../../ingestion_service/src/core/codebase/symbol_table.py).

Impact can begin as a bounded **candidate affected-set** with evidence and uncertainty. Reliable cross-service impact and “tests that will fail” are materially further away. Renames/deletions also require an old/new snapshot mapping, not just lookup in the latest rebuilt graph.

### 7. Repository identity and source authority

| Distinction | What survives now | What is missing |
|---|---|---|
| Selected repo vs fixture described inside it | Repo-scoped vector search and graph load; repo identity API | Subject binding in the LLM payload and embedded-subject roles; corpus membership does not mean every sentence describes the selected repo |
| Implementation vs tests/test results | Relative path, canonical ID, coarse `doc_type`; tests parse as code | Explicit artifact/section role and evidence-use policy |
| Current docs vs archives | Paths and raw Markdown text | Parsed lifecycle/status/version metadata and a trusted snapshot association |
| Implementation vs ADR/design intent | Markdown/source distinction | ADR front matter is not interpreted as authority; accepted intent can still disagree with implementation |
| Fixture/example vs real structure | Sometimes path hints; examples remain text within a parent section | Span/section-level subject and role, explicit unknown/mixed classifications |
| Deterministic fact vs generated summary | Separate `summary` field exists | Derivation kind, inputs, producer/model/prompt/version, and source-snapshot lineage |

Sources: [seed scoping and generation payload](../../rag_orchestrator/src/core/service.py), [source labels](../../rag_orchestrator/src/retrieval/agent_adapter.py#L12), [Markdown extraction](../../ingestion_service/src/core/extractors/markdown_extractor.py), [node model](../../shared/models/document_node.py), [summary persistence](../../ingestion_service/src/api/v1/summary.py).

**The schema has useful carriers, not a complete provenance contract.** `IngestionRequest.ingestion_metadata`, vector `source_metadata`, and relationship JSON can carry extensible fields. But `DocumentNode` has no generic metadata field, `persist_graph()` drops emitted node metadata, and `_embed_repo_artifacts()` forwards selected fields rather than the full metadata. Merely adding `source_role` to extractor IR would not make it survive to retrieval. [ingestion model](../../ingestion_service/src/core/models.py), [persistence](../../ingestion_service/src/core/codebase/codebase_persistence.py#L114), [embedding metadata](../../ingestion_service/src/api/v1/codebase_ingest.py#L79), [vector write path](../../vector_store_service/src/core/vectorstore/pgvector_store.py#L43).

A principled candidate model separates **origin** (repo/path/span/snapshot), **role** (implementation/config/test/design/evaluation/example/history), **subject** (selected repository or embedded example), and **derivation** (source, deterministic projection, LLM synthesis with inputs). These are not one universal authority score. For “what runs now,” current implementation/config dominates conflicting design; for “why was this chosen,” an ADR may be the right authority. Tests remain authoritative about asserted behavior, not a replacement for the runtime filesystem. Paths/front matter can supply versioned deterministic hints with an unknown/mixed fallback; do not hard-exclude all tests/archives or label every unfamiliar directory as a fixture.

### 8. Evidence sufficiency and agentic evolution

| Loop step | Current implementation | Nature of extension |
|---|---|---|
| Retrieve | Scoped vector search, graph expansion, chunk fetching | Already supported |
| Inspect evidence | Canonical labels, counts, optional known-target survival trace | Orchestration can inspect existing results; exact payload/chunk coverage and snapshot provenance need a better result contract |
| Determine sufficiency | Prompt asks the model to report missing answers | Mode-specific obligations can be deterministic: required overview facets, resolved entry point, supported trace hops/sink. General semantic sufficiency is not implemented or guaranteed |
| Identify gaps | Some trace drop reasons; unresolved external nodes | Structured gap records must distinguish not indexed, unresolved, capped, failed fetch, missing passage, conflicting snapshot, and unknown behavior |
| Retrieve/traverse again | Functions are callable, but `run_rag` performs one retrieval phase | A bounded orchestration loop can reuse them; add visited-target state, per-stage budgets, stopping rules, and snapshot consistency |
| Reconcile conflicts | No explicit reconciliation stage | Needs claim/evidence relationships and source-role/version policy; may use an LLM for interpretation while retaining conflicting evidence |
| Answer/report gaps | Grounding prompt and labeled sources | Return verified evidence references and unresolved obligations, not model confidence as proof |

Sources: [run_rag](../../rag_orchestrator/src/core/service.py#L378), [RetrievalPlan](../../shared/retrieval/retrieval_plan.py), [RetrievedContext](../../rag_orchestrator/src/retrieval/types.py), [evidence_trace](../../rag_orchestrator/src/retrieval/evidence_trace.py), [grounding prompt](../../llm_service/src/core/prompts/rag_answer.v1.txt).

`AgentPromptPipeline` is a prompt/chunk adapter, not an autonomous investigator, and it is not used by production `run_rag`. Model retries/fallbacks address provider failures, not missing evidence. A bounded workflow stays inside existing HTTP ownership; persistent multi-step investigations, tool selection by a model, cross-repository discovery, or autonomous actions would materially expand the product/architecture and need separate evidence and contracts. [adapter](../../rag_orchestrator/src/retrieval/agent_pipeline.py), [completion](../../llm_service/src/core/llm_client.py).

## Concrete design options

These comparisons are alternatives to test, not implementation commitments.

| Decision | Option A | Option B | Option C / assessment |
|---|---|---|---|
| Repository structure | Structured inventory returned by ingestion, rendered on demand: least graph growth; separate coverage contract needed | DIRECTORY/PACKAGE/SERVICE nodes linked to existing file artifacts: traversable; more identity/invalidation work | Graph/inventory plus derived document view: useful for RAG/export if there is one factual source. Avoid an independently authored duplicate tree. Compare A and C first |
| Architecture | Add only explicit source-backed entities/edges to unified graph: reusable traversal, but schema/export contracts must preserve provenance | Derive scoped architecture overlays from source/config facts: clear separation and cheaper experimentation, with projection cost | Separate persistent architecture graph: duplicate identity/storage/rebuild machinery; unjustified today |
| Structural query mode | Explicit `repository_overview`/`trace` request mode: clear intent and no router ambiguity | Deterministic classifier chooses a specialized plan: natural language convenience, but ambiguous wording needs fallback/clarification | General agent chooses retrieval tools: flexible, much harder sufficiency/cost evaluation. Explicit mode or plan is enough for the strongest cases |
| Source authority | Retrieval-time path/front-matter hints: small experiment, limited for mixed-subject sections | Persisted roles/provenance propagated through node/vector/edge APIs: stronger auditability, requires schema and producer/consumer changes | Typed stable fields plus extensible derivation metadata: useful if measurements show repeated need; avoid a rigid global numeric authority hierarchy |
| Mermaid | Deterministic on-demand renderer: reproducible, always tied to selected snapshot | Persisted derived export/cache: useful for sharing, needs invalidation and explicit provenance | LLM rendering from structured evidence: useful narrative grouping, but must validate entities/edges and label omissions/inference; not the canonical representation |

## Interaction with the current roadmap

No sequencing changes are proposed. Phase 3 currently marks IR/GraphAssembler and TS/JS complete; Rust/Java and Python migration remain open, with the language UI portion unfinished. Phase 4 plans ingestion jobs, incremental snapshots, bounded graph traversal, retrieval/observability work. Phase 5 plans private-host/PR integration and a graph-capable UI. These are roadmap statements, not proof of working behavior. [current roadmap](07-Roadmap.md#phase-3--multi-language-46-weeks).

| Idea | Classification | Relationship to planned work |
|---|---|---|
| Typed-edge symbol traversal | **Already supported**, bounded | Phase 3 language additions extend coverage; language-neutral traversal does not imply complete language/runtime resolution |
| Structural inventory / ORIENT | **Independent future capability** | Can reuse Phase 3 assembly and Phase 4 snapshot lineage; not already promised by another extractor or the graph explorer |
| Manifest/framework/endpoint facts | **Natural extension of existing planned work**, scope not committed | Reuses IR/extraction concepts but needs framework/deployment evidence beyond Phase 3's language list |
| Snapshot-aware projections / bounded TRACE | **Natural extension of existing planned work** | WP-S6/S7 support freshness and bounded traversal; ordered path evidence and HTTP joins are additional capability requirements |
| Caller-impact candidates | **Already supported in primitives; natural extension for product use** | WP-E4 explicitly anticipates caller-impact PR comments, but reliable test/contract/service impact is not implemented by that aspiration |
| General cross-service impact | **Independent future capability** | Needs service/endpoint contracts and revision mapping; not a guaranteed consequence of Phase 5 integration |
| Source-role/subject provenance | **Independent future capability** | Complements evaluation, snapshot lineage, and enterprise auditing; not interchangeable with authentication or observability |
| Mermaid projection/export | **Independent future capability** | Can complement WP-E6's graph explorer without making a new renderer a prerequisite for it |
| General evidence-sufficiency agent | **Premature / unsupported by present evidence as a required architecture** | Bounded mode-specific checks may fit orchestration; [technique gates](09-Retrieval-Technique-Decision-Gates.md) preserve broader agentic ideas as hypotheses |
| Canonical LLM-authored graph or separate authoritative graph store | **Potentially conflicting with current architecture** | Ingestion-time synthesis conflicts with deterministic ADR-030; separate canonical storage conflicts with unified identity/persistence unless explicitly reconsidered |

Two planning details need qualification when interpreting these ideas: WP-S8 still lists repo document-fetch concurrency as future work although `_fetch_expanded_doc_chunks()` already implements it; WP-S6's suggested node metadata/file hashes are not current persisted node fields. Similarly, old Phase 3 prose calling extraction Python-only is superseded by the registry and completed-status overlay. These are implementation/status distinctions, not requests to rewrite or reorder plans. [WP-S6/S8](04-Scalability-Plan.md), [current fetch](../../rag_orchestrator/src/core/service.py#L169), [current registry](../../ingestion_service/src/core/codebase/repo_graph_builder.py#L34).

## Risks and explicit deferrals

- **Do not put LLM synthesis inside deterministic repository ingestion.** Parsing a declaration mechanically and inferring architecture probabilistically have different reproducibility guarantees.
- **Do not treat diagrams, summaries, plans, archives, or evaluation answers as current implementation truth.** Preserve source snapshot, subject, role, and derivation; a generated map is a view.
- **Do not fill the graph with unqualified low-confidence architecture edges.** Compose startup dependencies, imports, HTTP calls, and ownership are different claims; deterministic heuristics can still be wrong.
- **Defer a graph database.** Measure indexed bounded traversal/projection needs first, consistent with WP-S7; it cannot fix missing identities or provenance.
- **Defer an LLM retrieval router/general supervisor.** Explicit modes and deterministic plans cover the strongest hypotheses without autonomous tool selection.
- **Do not solve orientation or trace completeness with larger top-k alone.** Missing inventory, wrong subjects, absent edges, arbitrary chunk selection, and actual branch behavior require different evidence.
- **Defer universal runtime traces and confident breakage predictions.** A static possible-call graph neither observes executed branches nor establishes contract compatibility, test coverage, or dataflow.

## Future investigation questions and decision gates

1. **Does an inventory-backed overview solve the observed orientation failures?** On this repo and one differently organized repo, compare generic RAG with a deterministic inventory-backed overview for actual structure, graph-schema explanation, and fixture-specific questions. Record directory/service/package coverage, invented paths, correct subject, citations, and explicitly unknown facets. **Gate:** repeated coverage/subject improvement without harming fixture/design questions supports a specialized overview plan; adding an embedded overview alone must demonstrate survival through retrieval/context caps.

2. **Which architecture relations are precise enough to promote to facts?** Hand-label a small set from Compose, Dockerfiles, manifests, literal router registration, and actual HTTP/DB call sites; include shared code, Gradio's source location, service-local import roots, and environment overrides as ambiguity controls. Record evidence per edge, false positives, unresolved cases, and distinction between declaration and runtime observation. **Gate:** promote only relation kinds with reproducible, source-auditable derivation and no unsupported edges in the controls; leave ownership/dynamic calls as qualified projections when ambiguity remains.

3. **How much TRACE/IMPACT is recoverable through existing edges versus missing resolution?** Compare several exact-symbol paths and `/v1/rag`'s cross-service path against a source-reviewed reference. Preserve edge metadata, inspect unresolved endpoints, and separately count traversal omissions, source-root resolution gaps, HTTP-boundary gaps, and passage loss. Grade reverse callers/test candidates without claiming breakage. **Gate:** if existing edges suffice, investigate orchestration only; repeated unresolved imports justify scope-resolution work, while absent endpoint/service evidence justifies narrowly typed extraction. Neither is fixed by raising depth blindly.

4. **What minimum provenance prevents subject and authority substitution?** Compare current labeling, deterministic role hints, and structured role/subject/snapshot records on current-implementation, design-intent, archive, mixed-example, and generated-summary questions. Pin runtime and corpus snapshots separately; inspect the actual generation payload. **Gate:** sustained improvement on conflicting/mixed-subject cases supports persisted provenance; broad exclusions that suppress valid design/test answers fail the gate.

5. **Can bounded evidence obligations improve answers without a general agent?** For overview and trace cases, define required facets/hops, then compare single-pass retrieval with at most one targeted follow-up for a named missing item. Keep snapshot, model, and evidence budgets fixed; record gap classification, added evidence, answer changes, cost, and unnecessary follow-ups. **Gate:** reliable recovery from explicit gaps supports a bounded orchestration loop; inability to define/test sufficiency means report gaps and defer autonomous investigation. Only persist/render diagrams once every asserted edge can be traced to the same evaluated evidence snapshot.
