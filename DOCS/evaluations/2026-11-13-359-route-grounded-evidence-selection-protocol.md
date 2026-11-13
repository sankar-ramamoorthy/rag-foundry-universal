---
title: "Protocol: route-grounded evidence-selection diagnostic with overfitting controls (#359)"
date: 2026-11-13
type: evaluation-protocol
status: draft
summary: "Pre-registered protocol for testing whether route-grounded traversal plus source fetching can select sufficient evidence for the POST /v1/rag trace question at 4 KB and 16 KB. It separates discovery, selection and survival, and binds the work to overfitting controls under ADR-054, including explicit handling of ambiguous and unresolved calls. Owner decisions are recorded: Codex writes sealed C7 ground truth, and the held-out repository is mealie @ 1624c22. Freezes on merge."
tags: [evaluation, protocol, code-intelligence, evidence-selection, overfitting, issue-359, issue-342, issue-194]
authority: "Draft protocol; no execution authorized until frozen"
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[Issue #342](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/342)"
  - "[Issue #194](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/194)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[#342 trace rerun after #354](/DOCS/test_results/2026-11-13-342-post-354-trace-rerun.md)"
  - "[Retrieval-side handoff](/DOCS/notes/20261112-code-intelligence-342-354-handoff.md)"
---

# Protocol: route-grounded evidence-selection diagnostic (#359)

## 1. Purpose

After #354, the graph trace from `POST /v1/rag` reaches 7 of 13 chain nodes,
but connectivity is not answerability. This diagnostic asks whether a
**route-grounded, bounded traversal plus source fetching** can select enough
implementation evidence to support the Step 0 answer. It is tested at the
current 4 KB budget and at 16 KB as a diagnostic comparison. No expected
function list is supplied to any selection rule.

Three measurements stay separate throughout:

1. **Discovery:** which functions existing graph relationships reach from the
   route named in the question.
2. **Ranking and selection:** which functions and passages each rule chooses,
   in what order, and how much budget placeholder or fan-out noise consumes.
3. **Survival and sufficiency:** which relationship witnesses survive
   production context assembly at each budget, and whether every **core**
   relationship is supported.

## 2. Evidence class (ADR-054)

`rag-foundry-universal` is a **development and diagnostic repository**. Every
result on it is development evidence. It can guide engineering and serve as a
regression test, but it **cannot** establish that route-grounded selection
generalizes. Section 8 sets out the controls that bound this.

## 3. Fixed inputs

These are frozen together with the protocol.

| Input | Value |
|---|---|
| Question | Step 0 text, verbatim (`DOCS/test_results/_raw/2026-11-12-345-step0/659139bc01fd464589a8972e50f72412.json`, after `Question:`) |
| Repository | `f7641840-ba13-5f9d-9ae6-87e1f924709d` |
| Generation | `8cbedbb9-9ad6-4c63-83f7-2b7d7659f7e5` (commit `9f039c4`). The run aborts if it is not the ready generation. |
| Services | `git_sha` `9f039c4`, recorded before and after the run |
| Budgets | 4,096 and 16,384 bytes, counted by `rag_orchestrator/src/retrieval/agent_adapter.py#assemble_context` (UTF-8 bytes including source labels and separators; oversized passages are skipped, in order) |
| Passage source | Stored chunks from `POST /v1/vectors/search-by-doc` (k ≤ 100), in `chunk_index` order. The ranking vector is the stored Step 0 query vector from `2026-11-12-345-retrieval-candidates-run3.json`, so no model call is made. |
| Graph | `GET /v1/graph/repos/{id}?expected_generation_id=…` and `GET /v1/repos/{id}/trace` |

The 16 KB budget is diagnostic only. It is not a configuration proposal.

## 4. Expected relationships (ground truth)

The ground truth is used **only by the scoring step, after selection output is
written** (control C4).

- **Witness rule.** A relationship is *source-supported* in an arm and budget
  when the witness regex matches a **delivered passage whose canonical ID is
  the relationship's caller**. Documentation that mentions a name never
  counts.
- **Verification.** Each witness was verified against the source at `9f039c4`
  (line numbers below) before this protocol was written. Each must also be
  present in the stored text of `8cbedbb9`; the preflight check (section 7)
  confirms this, and a missing witness aborts the run.
- **Route relationships.** R1 and R15 may alternatively be satisfied
  *structurally*: the `HANDLED_BY` edge was used by the rule and is recorded
  in the evidence manifest. This is declared now, not decided afterwards.

| ID | Tier | Caller (canonical ID) | Relationship | Witness regex | Line at `9f039c4` |
|---|---|---|---|---|---|
| R1 | core | `rag_orchestrator/src/api/v1/routes.py#rag_endpoint` | `POST /v1/rag` handled by `rag_endpoint` | `@router\.post\("/rag"` | 62 |
| R2 | core | same | calls `run_rag` | `\brun_rag\(` | 67 |
| R3 | supporting | `rag_orchestrator/src/core/service.py#run_rag` | calls `resolve_repo_id_http` | `resolve_repo_id_http\(` | 1249 |
| R4 | supporting | `…/service.py#resolve_repo_id_http` | HTTP to ingestion `/v1/repos` | `/v1/repos` | 152 |
| R5 | supporting | `…/service.py#run_rag` | calls `get_embedder` | `get_embedder\(` | 1251 |
| R6 | supporting | `shared/embedders/factory.py#get_embedder` | constructs `OllamaEmbedder` | `OllamaEmbedder\(` | 19 |
| R7 | core | `…/service.py#run_rag` | runs `embed_query` via `asyncio.to_thread` | `to_thread\(\s*embed_query` | 1259 |
| R8 | core | `shared/embedders/query.py#embed_query` | calls `embedder.embed` (abstract) | `embedder\.embed\(` | 32 |
| R9a | core | `shared/embedders/ollama.py#OllamaEmbedder.embed` | calls `_strict` | `self\._strict\(` | 107 |
| R9b | core | `shared/embedders/ollama.py#OllamaEmbedder._strict` | calls `_post` | `self\._post\(` | 80 |
| R10 | core | `shared/embedders/ollama.py#OllamaEmbedder._post` | HTTP to Ollama `/api/embed` (moved here from `embed`, see the #358 report) | `/api/embed` | 51 |
| R11 | core | `…/service.py#run_rag` | calls `hybrid_retrieve` | `hybrid_retrieve\(` | 1261 |
| R12 | supporting | `…/service.py#hybrid_retrieve` | calls `_query_generation` | `_query_generation\(` | 933 |
| R13 | supporting | `…/service.py#_query_generation` | HTTP to ingestion `…/generation` | `/generation` | 520 |
| R14 | core | `…/service.py#hybrid_retrieve` | HTTP to vector store `/v1/vectors/search` | `/v1/vectors/search` | 932 |
| R15 | core | `vector_store_service/src/api/v1/vectors.py#similarity_search` | handles `POST /v1/vectors/search` (router prefix `/v1/vectors`) | `@router\.post\("/search"\)` | 92 |
| R16 | core | same | runs `store.similarity_search` via `asyncio.to_thread` | `store\.similarity_search` | 101 |
| R17 | core | `vector_store_service/src/core/vectorstore/pgvector_store.py#PgVectorStore.similarity_search` | pgvector cosine SQL | `vector <=> ` | 187, 190 (excludes the docstring at 164) |

There are 12 core and 6 supporting relationships. The core set covers the
question's demands: the endpoint, the orchestrator path, query embedding
including the Ollama HTTP call, the cross-service hop, and the pgvector
operation. Each delivered passage carries a `[Source: path#symbol]` label,
which identifies the file.

## 5. Selection rules (frozen; generic only)

### Route anchor (all graph arms)

- Apply `\b(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}.-]*)` to the question.
- Look up route nodes whose ID ends in `:<METHOD>:<path>`.
- Exactly one match is required. Otherwise the arm stops with
  `unresolved_route` or `ambiguous_route`.
- The handler is the route's `HANDLED_BY` target.

### Traversal bounds (all graph arms)

- Forward edges only.
- `CALL` edges whose targets are real nodes. `EXTERNAL_*`, `route:` and
  `compose:` targets are **suppressed and counted**.
- Maximum depth 6 (the server `TRACE_MAX_DEPTH`) and node cap 300
  (`TRACE_MAX_NODES`).
- Children are ordered by their first `call_sites` line, then by canonical ID.

### Discovery and selection arms

| Arm | Rule | Role |
|---|---|---|
| A0 | The current `/v1/rag` path (vector seeds plus expansion) on `8cbedbb9`, run offline with the stored query vector and generation stubbed | reference: today's behaviour |
| G0 | Every resolved node in the deployed `/trace` hop order (`HANDLED_BY,CALL`) | reference: "use the whole trace" |
| G1 | Breadth-first from the handler, in call-site order | comparison |
| **G2** | **Depth-first pre-order from the handler, in call-site order (execution order)** | **primary hypothesis, declared in advance** |
| G3 | G2, plus a *URL-literal route hop*. When a selected function's stored text contains a string literal equal to exactly one route node's path, that route's handler is added as a child at that point. Paths matching more than one route are skipped as ambiguous. | comparison; designed with knowledge of the H13 gap (C5) |

### Passage units (each graph arm runs with both)

| Unit | Passages per selected function |
|---|---|
| P-whole | all chunks, in `chunk_index` order |
| P-call | the first chunk (signature or decorator), plus every chunk containing `\b<child simple name>\(` for a child the arm selected, plus (G3 only) any chunk containing the matched URL literal |

Passages enter `assemble_context` in function-selection order, then chunk
order. There are 1 + 4 × 2 = 9 arms, each run at 2 budgets.

### 5a. Ambiguous and unresolved call relationships

These rules bind every arm, the scoring, and the C7 and C10 runs.

1. **Placeholders are never resolved by guessing.** Traversal never follows an
   `EXTERNAL_*` placeholder, and no rule resolves a placeholder by name lookup
   (for example, `embedder.embed` → "the only non-test `embed`"). Suppressed
   placeholders are counted per arm.
2. **Ambiguity is recorded, never chosen.** A single call site or reference is
   *ambiguous* when it has more than one candidate target. That includes:
   - abstract dispatch with several overriding implementations;
   - duplicate symbol names;
   - a URL literal matching several route nodes;
   - a question route matching several route nodes.

   The rule then adds **none** of the candidates on that basis. It records
   `ambiguous` with the full candidate set. The route anchor stops with
   `ambiguous_route` (section 5).
3. **Indirect references are not followed in this version.** That covers a
   function passed as a value (`asyncio.to_thread(f, …)`, callbacks) and a
   method of an injected or untyped receiver. Such a relationship can be
   supported only *source-only*: by delivering the caller's passage that
   contains the reference.
4. **Every expected relationship carries a resolution class** in the ground
   truth: `static_direct`, `indirect_reference`, `dynamic_dispatch`
   (ambiguous), `cross_service_http`, `external_http`, `sql`, or `route`.
   In the primary case: R7 and R16 are `indirect_reference`; R8 is
   `dynamic_dispatch` (candidates `OllamaEmbedder.embed`, `MockEmbedder.embed`;
   the configured provider is established by R6); R4, R10, R13 and R14 are
   HTTP; R17 is `sql`; R1 and R15 are `route`; the rest are `static_direct`.
5. **Each relationship is scored into exactly one support category:**

   | Category | Meaning |
   |---|---|
   | `graph_and_source` | callee discovered through a graph edge, and the witness delivered |
   | `source_only` | witness delivered in the caller's passage, callee not graph-discovered |
   | `unresolved` | witness not delivered |
   | `unwarranted_disambiguation` | an arm treated one candidate of a `dynamic_dispatch` relationship as *the* callee without the configuring evidence (for R8, R6's witness). This is an **error**, not support. |

   Results are reported per class and per category, so the report shows how
   much of a pass rests on source-only evidence.
6. **Unresolved route paths.** If a route node's full public path is
   unresolved (`resolved_path` empty; the node carries the router-local path),
   the anchor matches only an exact `METHOD path` suffix. A question naming the
   public path then yields `unresolved_route`, which is reported as an
   anchoring failure. The protocol does not rewrite the question or add
   path-guessing (see section 9, held-out eligibility).

## 6. Measurements

For every arm and budget:

- **Discovery:**
  - the ordered set of functions reached;
  - placeholders suppressed;
  - whether the cap was hit.
- **Selection:**
  - candidate passages and bytes requested;
  - the position of each chain function in the order;
  - fan-out: resolved non-chain functions selected before the last chain
    function.
- **Survival:**
  - passages and bytes delivered;
  - relevant-bytes share (passages whose canonical ID is a ground-truth
    caller);
  - which relationships are source-supported.
- **Sufficiency:**
  - PASS only if **all 12 core** relationships are supported (no partial
    pass);
  - supporting coverage reported separately;
  - every unproven relationship listed, with its reason: not discovered, not
    selected, or cut by the budget.
- **Budget attribution, 4 KB → 16 KB:**
  - relationships gained;
  - relevant bytes gained versus non-relevant bytes gained;
  - this shows whether a larger budget helps by adding relevant evidence or
    only more text.
- **Minimum-evidence bound (oracle; labelled as such):**
  - the smallest-byte set of caller passages, under `assemble_context`
    costing, that covers all core witnesses;
  - this states whether 4 KB is feasible at all, independent of any selector;
  - it is not a selector result.

## 7. Procedure

1. **Preflight (read-only):**
   - confirm the generation is ready and unchanged;
   - confirm service SHAs;
   - confirm every witness in section 4 is present in the caller's stored
     text. A missing witness aborts the run; the protocol is never edited to
     fit.
2. **Run selection for all arms.** Write the selection output (ordered
   functions, passages, delivered context and manifest) to the raw record,
   with its sha256, **before** loading the ground truth.
3. **Score.** Scoring loads the ground truth and reads only the written
   selection output.
4. **Re-check and index.** Re-check that the generation is unchanged, then
   index the raw records in `raw-index.json`.

## 8. Overfitting controls

| ID | Control | Mechanism |
|---|---|---|
| **C1** | Evidence-class label | Every report states "development evidence (ADR-054); not a generalization result". |
| **C2** | Pre-registration | The protocol is merged to `main` before the first run. The run records the protocol's commit and file sha256. Any change after a run creates a new protocol version, and both versions' results are reported. |
| **C3** | Generic rules only | Selection-rule code lives in its own module. It must not import the ground-truth module, and it must not contain any ground-truth canonical ID, symbol name, file path or question-specific term. A unit test scans the module and fails otherwise. Allowed signals are the parsed route, edge types, call-site lines, chunk text matched against names *taken from graph edges*, and string literals matched against existing route nodes. |
| **C4** | Scoring separation | Ground truth is loaded only by the scoring step, after selection output is written and hashed. |
| **C5** | Disclosure of designer knowledge | G2's execution-order idea and G3's URL-literal rule were conceived knowing this question's gaps (H7, H13). This is stated in the report, and their value counts only through C6 and C7. |
| **C6** | Corpus self-description | Generation `8cbedbb9` contains our own reports, which name the chain's functions. Graph arms fetch only function passages, but A0 and any text-ranked step are contaminated; this is reported per arm. |
| **C7** | Within-repo overfitting check | The same frozen rules (no changes) run on **at least 3 additional entry-point routes** in this repository. Their expected relationships are written **before the run, by Codex from implementation source** and sealed by hash (section 9.1). The report shows per-route results. A pass on `POST /v1/rag` alone is reported as a single-case result. |
| **C8** | Primary arm and multiple comparisons | G2 is the declared primary hypothesis. All arms are reported, and the best-scoring arm is never presented as the finding unless it is G2. A non-primary arm that outperforms is reported as a hypothesis for the next protocol version. |
| **C9** | No tuning between stages | Rules are not changed between the self-repo run, the C7 routes and the held-out run. Any change starts a new protocol version, and previously held-out data is reclassified as development data (ADR-054 §6). |
| **C10** | Held-out gate | No `/v1/rag` change may be described as general, and no default may change, until the frozen rules pass on an **unseen repository** frozen per ADR-054 §5. That means freezing the commit, ready generation, questions, expected evidence, scoring, budgets and runtime. Its answers are never inspected during development. Chosen: `mealie-recipes/mealie` @ `1624c22` (section 9.2). The repository needs extractable routes (FastAPI-style decorators and a compose file). That requirement is itself a scope limit: route grounding only applies where routes are extracted. |
| **C11** | Scope statement | A positive result supports route grounding **only for questions that name an identifiable entry point**. It is not a solution for all codebase questions. LightRAG's untyped-receiver failure is a different failure mode and is out of scope. |

## 9. Owner decisions (recorded 2026-11-13)

### 9.1 Independent ground truth for C7: Codex

**Decision.** Codex independently writes the expected execution chains for
**at least three previously unstudied routes** in this repository.

**Constraints on the routes and chains:**
- Codex works **from implementation source, not from existing diagnostic
  reports**.
- *Unstudied* excludes `POST /v1/rag`, `POST /v1/vectors/search`, and any route
  named in an earlier #342/#345/#354/#359 report.
- Each chain uses the section 4 format: caller canonical ID, relationship,
  witness regex, verified source line, tier, and the resolution class from 5a.

**Sealing procedure** (keeps the answers isolated from Claude's predictions):

1. **Codex publishes the questions file:** routes and question text only. Its
   sha256 is recorded on #359. Claude may read this, because selection needs
   the questions.
2. **Codex writes the expected-chains file,** never shown to Claude. Only its
   sha256 is posted on #359 before any selection run. The file stays out of
   the repository and out of Claude's reach until step 4.
3. **Claude runs selection** for all arms on the C7 questions with the frozen
   rules. The selection outputs, with their sha256, are posted on #359. These
   are the frozen predictions.
4. **Codex then adds the expected-chains file** to the repository. The
   scoring step verifies its sha256 against step 2 and refuses to score on a
   mismatch.
5. **Codex does not see the selection outputs before step 2.** Claude does not
   see the expected chains before step 3.

The owner confirms each step on #359. Any break in this order is reported, and
the affected route is reclassified as development data.

### 9.2 Held-out repository for C10: `mealie-recipes/mealie` at `1624c22bf70988c7fe404ad586e2f9689f77748d`

**Decision.** Use a separate repository, unseen and within the supported
FastAPI/Compose domain. **Do not** use the already-examined `code-graph-rag`
questions as pristine held-out tests. Portability to other architectures is a
**separate evaluation dimension**, not part of this gate.

**Exclusions** (already examined or already reserved):
- `sankar-ramamoorthy/rag-foundry-universal`, `py-coding-agent`;
- `HKUDS/LightRAG`, `vitali87/code-graph-rag`, `paulxiep/code-rag`;
- `pallets/werkzeug`;
- `pypa/hatch` and `pdfminer/pdfminer.six` (the E1 held-out set);
- `Tencent-Hunyuan/RepoProbe`, `SoftWiser-group/RepoET`.

**Candidates and how they were checked.** Candidates came from a web search for
FastAPI + Compose repositories plus well-known FastAPI projects. They were
shallow-cloned into an isolated scratch directory and checked with
`scripts/heldout_eligibility_359.py`. That script runs this repository's own
ingestion extraction (structural inventory, service topology, and
`RepoGraphBuilder` with #354) in memory and prints **counts only**. No source
text, function names or chains were viewed, so no evaluation answer was seen
(ADR-054 §3).

Results on 2026-11-13 (handler reach = repository functions reached over
resolved CALL edges, depth ≤ 6):

| Candidate @ commit | Python files | Compose services | Route nodes (with handler) | Routes with resolved full path | Cross-service calls | Handlers reaching ≥ 3 functions (median / max reach) |
|---|---:|---:|---:|---:|---:|---|
| `GavriloviciEduard/fastapi-microservices` @ `a275614` | 21 | 4 | 10 (10) | 0 | 0 | 0 (0 / 0) |
| `fastapi/full-stack-fastapi-template` @ `aabb901` | 43 | 14 | 18 (18) | 0 | 0 | 5 (1 / 7) |
| `marttp/fastapi-microservice` @ `0aa80fe` | 11 | 5 | 0 | 0 | 0 | 0 |
| `pvfarooq/fastapi-simple-ecommerce-microservice` @ `12d6e14` | 39 | 6 | 4 (4) | 0 | 0 | 0 (0 / 1) |
| **`mealie-recipes/mealie` @ `1624c22`** | **718** | **6** | **30 (30)** | **0** | **0** | **15 (2.5 / 15)** |

Two further candidates were dropped. `letta-ai/letta`'s shallow clone checked
out incompletely (189 KB). `polarsource/polar` produced 0 extracted Python
files, an anomaly that was not investigated. Both are also far larger than the
development corpus.

**Selection rule (structural only).**
1. Require routes extracted with handler nodes, and **≥ 3 handlers with
   non-trivial chains** (reach ≥ 3), so that held-out questions can test
   selection rather than a single function.
2. Among those, prefer the candidate with more non-trivial chains.

`mealie` (15) wins over `full-stack-fastapi-template` (5). `mealie` is an
actively maintained application (FastAPI backend with Compose), not a
template, and its size is comparable to or larger than the development corpus.

**Held-out still pending, with owner approval required.**
- Ingesting `mealie` at the pinned commit on the Linux host.
- Freezing the questions, expected evidence and scoring per ADR-054 §5. The
  default is for Codex to author these under the same sealing procedure as
  9.1, unless the owner decides otherwise.

**Eligibility finding (an overfitting signal, recorded before any run).** Not
one of the analysable candidates has a route whose **full public path**
resolved. Their router prefixes come from settings variables or non-literal
include chains, so route nodes carry router-local paths. The self-repository's
literal-prefix style is the exception. Under 5a.6, a held-out question that
names a public path will give `unresolved_route`. The C10 result will measure
this as-is. Route-path resolution is a separate engineering question, and it
must not be tuned on `mealie` (C9).

Route extraction also covers only part of `mealie`: 30 route nodes, against
the many more endpoints a project that size typically exposes (not counted
here). This too will be reported rather than corrected before the held-out
run.

## 10. Boundaries

- Read-only: graph export, `/trace`, `search-by-doc`, and offline use of
  `assemble_context` and the A0 orchestrator path with the stored query
  vector.
- No LLM generation, no embedding call, no ingestion, no retrieval-policy or
  configuration change, and no SQL.
- The deliverable is a report naming the smallest defensible query-time change
  and its unresolved limitations, **before** any implementation.
