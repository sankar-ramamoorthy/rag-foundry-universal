---
title: "#354 service-root import resolution: validation on the pinned self-repo revision"
date: 2026-11-12
type: test-result
status: complete
summary: "On a disposable corpus at 8e06335, src.-prefixed CALL placeholders fall from 1,245 to 18. 1,227 CALL edges resolve, all replacing a same-name placeholder from the same caller. No real node ID changes, and no real edge is lost, retargeted or cross-project. 36 of 36 sampled edges verified against source."
tags: [code-intelligence, graph, import-resolution, validation]
authority: "Observed in-memory graph builds of one repository snapshot; not a re-ingestion of any database"
related:
  - "[ADR-032 amendment 2026-11-12](/DOCS/adr/ADR-032-symbol-resolution-call-graph.md)"
  - "[#342 A/B/C diagnostic](/DOCS/test_results/2026-11-12-342-abc-discovery-diagnostic.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #354 service-root import resolution: validation

## Method

- **Corpus:** `git archive 8e06335` (the commit of the self-repo generation
  `e423d1bb` on the Linux development host), extracted to a disposable scratch
  directory.
- **Builds:** the graph was built twice, in memory, with this branch's ingestion
  code, once with project-root discovery disabled (pre-#354 behaviour) and once
  enabled. Nothing was persisted. No database or service was contacted, and the
  Linux database was not touched.
- **Harness:** `scripts/validate_354_import_resolution.py`. The raw record is
  `2026-11-12-354-import-resolution-validation.json` in the
  [raw index](/DOCS/test_results/raw-index.json).

**Fidelity check.** The pre-#354 build reproduces the ingested generation
exactly: 10,251 CALL edges, 8,221 placeholder targets and 1,245 `src.`-prefixed
placeholders, the same as the graph export from the development database. The
deployed export has 10,973 nodes against 10,786 here. The difference is the
route, compose and service-topology nodes, which are added outside
`RepoGraphBuilder`.

Project roots discovered: `gradio`, `ingestion_service`, `llm_service`,
`rag_orchestrator` and `vector_store_service`. `vector_store_service` qualifies
through `pytest.ini`, since it has no `pyproject.toml` at this commit.

## Results

| Measure | Before | After |
|---|---:|---:|
| CALL edges | 10,251 | 10,251 (one-for-one replacements) |
| CALL edges to placeholders | 8,221 | 7,015 |
| `src.`-prefixed CALL placeholders | 1,245 | **18** |
| IMPORTS edges | 1,485 | 1,783 |
| OVERRIDES edges | 8 | 21 |
| Nodes | 10,786 | 10,562 (234 placeholder nodes no longer needed, 10 re-spelled) |

**Newly resolved CALL edges: 1,227.** By stratum:

| Service | src | tests |
|---|---:|---:|
| ingestion_service | 196 | 476 |
| llm_service | 15 | 71 |
| rag_orchestrator | 59 | 385 |
| vector_store_service | 1 | 24 |

That is 271 from non-test code and 956 from tests.

## Correctness checks

| Check | Result |
|---|---|
| Real (non-placeholder) node IDs added or removed | **0** |
| Existing edges to real nodes lost or retargeted | **0**. All 1,423 removed edges pointed at `EXTERNAL_*` placeholders. |
| Kept edges whose metadata changed | **0** for CALL, INHERITS, DEFINES and the rest. 1 IMPORTS edge gained name pairs, because its file imports `service.py` under both spellings. |
| New CALL, IMPORTS or INHERITS edge without a same-caller, same-name placeholder it replaces | **0** |
| New edges whose target is in a different project root than the caller | **0** |
| Repository-root interpretation shadowing a different project-root module | **0** |
| Dangling edges (endpoint not a node), before and after | **0** and **0** |

**The 13 new OVERRIDES edges are derived, not stray.** Each one's class gained a
newly resolved INHERITS edge to the class defining the overridden method. Seven
are in source (`PgVectorStore` → `VectorStore`, `PDFExtractor`, `TesseractOCR`)
and six in `vector_store_service/tests/core/vectorstore/test_base.py`.

**21 edges were re-spelled, not resolved.** In these, the module now resolves
but the called member is an attribute of a module-level object, for example
`ownership_check.set`. The placeholder is now spelled from the module's
repository-root path, as already happens for imports that resolved before
#354. This affects 10 placeholder IDs. Placeholders are never embedded.

**18 `src.` placeholders remain, correctly.** Seventeen are calls from files
under no project root (`DOCS/test_results/*.py` and `scripts/*.py`, which put a
service on `sys.path` themselves). One is `src.rstrip` in a test, where `src` is
a local string variable, not an import.

## Manual source verification (36 newly resolved CALL edges)

The sample is deterministic: sha256 order, round-robin across the eight
service × {src, tests} strata. For each edge, three things were checked against
the corpus source:

- the call line in the caller;
- the import statement that binds the called name in that file;
- the definition line in the resolved target.

**36 of 36 are correct.** In every case the caller's own service import (for
example `from src.core.config import get_settings`, `from src.core import
model_registry`, or `import src.core.llm_client as llm_client`) binds the name
to the resolved module, and the target defines it. There were no incorrect or
ambiguous resolutions. All 36 rows are in the raw record (`sample`).

| # | Caller → resolved target (abridged) | Binding |
|---:|---|---|
| 1 | `treesitter/rust.py#RustExtractor.extract` → `treesitter/base.py#language_for_path` | `from src.core.extractors.treesitter.base import (language_for_path` |
| 2 | `tests/api/test_ingestion_recovery.py` → `api/v1/ingest.py#background_ingest_file` | `from src.api.v1 import ingest` |
| 3 | `llm_service …/main.py#_endpoint_inventory` → `model_catalog.py#get_catalog` | `from src.core import model_catalog` |
| 5 | `rag_orchestrator …/service.py#_fetch_repository_overview` → `config.py#get_settings` | `from src.core.config import get_settings` |
| 7 | `vector_store_service …/config.py#get_vector_store` → `pgvector_store.py#PgVectorStore` | `from src.core.vectorstore.pgvector_store import PgVectorStore` |
| 13 | `simple_service.py#run_simple_rag` → `service.py#_fetch_expanded_doc_chunks` | `from src.core.service import _add_chunks, _fetch_expanded_doc_chunks` |
| 26 | `tests/core/test_llm_client_litellm.py` → `llm_client.py#generate_completion` | `import src.core.llm_client as llm_client` |
| 34 | `api/v1/routes.py#impact_endpoint` → `trace_impact.py#resolve_start_symbol` | `from src.retrieval.trace_impact import (… resolve_start_symbol` |

## Effect on the #342 chain

In the post-#354 graph, a CALL traversal from `rag_endpoint` reaches:

- depth 1: `run_rag`;
- depth 2: `resolve_repo_id_http`, `get_embedder`, `hybrid_retrieve`;
- depth 3: `OllamaEmbedder`, `_query_generation`.

This matches the query-time counterfactual in the #342 diagnostic.
`embed_query`, `OllamaEmbedder.embed` and `PgVectorStore.similarity_search` are
still unreachable, because they are reached through `asyncio.to_thread` or
abstract dispatch, which is out of scope here.

## Observations outside scope

- **Nested-class identity quirk (pre-existing).** A class defined inside a
  function gets the canonical ID `file#fn.Cls`, but its methods get `file#Cls.m`,
  without the function. The edges are consistent: there are no dangling edges.
  The identity is just asymmetric. #354 does not change it; it only makes
  OVERRIDES edges from such classes visible. Worth a separate ADR-031 review.
- **Re-ingestion rebuilds all edges.** Incremental ingestion reuses vectors by
  content hash, but `RepoGraphBuilder.build()` assembles the whole repository
  every time. A later re-ingestion will therefore apply the fix to unchanged
  files too, without a forced full rebuild. This is based on reading
  `codebase_ingest.py` and `repo_graph_builder.py`, not on running an
  ingestion.

## Limits

- One repository at one revision; other layouts are covered only by the unit
  fixtures. One layout is not addressed by this rule at all: a single
  `src/`-layout package (`src/pkg/…` imported as `pkg.…`) whose marker sits at
  the repository root. The repository root is excluded from project roots, and
  the import does not start with `src.` anyway. That would be a separate
  convention.
- The disposable corpus is a `git archive`, which contains exactly the tracked
  files an ingestion clone would see. Untracked or ignored local files were not
  part of it.
