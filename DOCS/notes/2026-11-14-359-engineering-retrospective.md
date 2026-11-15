---
title: "Issue #359 — Route-Grounded Repository Evidence: Engineering Retrospective"
date: 2026-11-14
type: note
status: complete
summary: "Historical engineering retrospective of the closed #359 evaluation (final merge efe973d). It is a narrative synthesis of frozen evaluation results, not a description of current implementation and not an authority on it. The test-result reports remain the source of truth for every measurement; this note decides nothing."
tags: [retrospective, evaluation, code-intelligence, evidence-selection, overfitting, issue-359, issue-342, issue-194]
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[#359 final report and recommendation](/DOCS/test_results/2026-11-14-359-final-report-and-recommendation.md)"
  - "[#359 primary development case results](/DOCS/test_results/2026-11-14-359-primary-development-case-results.md)"
  - "[#359 C7 results](/DOCS/test_results/2026-11-14-359-C7-evidence-selection-results.md)"
  - "[#359 held-out mealie results](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md)"
  - "[#359 protocol (frozen at 45f34e1)](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)"
  - "[Issue #370: query-time transparency proposal](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/370)"
  - "[Issue #371: evaluation documentation competing with implementation evidence](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/371)"
---

> **Historical evaluation record, not current implementation.** This
> retrospective summarizes a closed, frozen evaluation as of `efe973d`. Where
> it differs from the linked test-result reports, the reports govern.
> Statements about code describe the commits tested (`9f039c4`, `mealie` @
> `1624c22`), not later code.

# Issue #359 — Route-Grounded Repository Evidence: Engineering Retrospective

- **Project:** RAG-FOUNDRY-UNIVERSAL
- **Investigation:** November 10–14, 2026 (issue closed November 15, 2026 UTC)
- **Disposition:** Evaluation complete; retrieval improvement **not** implemented
- **Evidence class:** One previously studied primary development case, three independently authored C7 development cases, and three questions from one frozen held-out repository
- **Key result:** The frozen selection strategy did **not** deliver a sufficient execution trace at either 4 KB or 16 KB. The limiting mechanism depends on the case: route discovery, graph connectivity, and—in the original development trace—context allocation.

> **Interpretation boundary.** This was a *read-only, source-evidence selection* experiment, not an end-to-end test of generated answers, a model benchmark, a GPU benchmark, or a production load test. “0/48” describes 48 **oracle-assisted selector configurations**, not 48 distinct questions. The study provides strong diagnostics for the tested cases, not a population-wide failure-rate estimate.

## 1. Executive summary

The immediate problem was straightforward: when asked to explain how an API request actually executes through the repository, the system could retrieve documentation or isolated snippets while omitting essential implementation functions, call relationships, and cross-service hops. Its canonical graph, route inventory, and source chunks offered a promising alternative to vector similarity alone—but it was unknown whether a *generic*, route-anchored graph selector could reliably select enough **caller-scoped source evidence** to reconstruct an execution path.

Issue #359 converted that intuition into a falsifiable experiment. Its protocol and harness were frozen before testing; correct handlers (ORACLE-ENTRY) were withheld until end-to-end predictions were frozen; expected chains were independently prepared and cryptographically committed; 4 KB and 16 KB passage budgets, four graph traversal strategies, and two passage units were compared. The original self-repository trace was explicitly treated as a studied development case. A second, independently authored C7 development set checked other endpoints in the same repository. A pinned, never-before-used Mealie repository supplied the held-out test.

The experiment showed three different limits:

1. **Route identity:** some externally exposed public API paths did not exist as complete route identities in the graph; other route paths were ambiguous across services.
2. **Call graph connectivity:** with the correct Mealie handler supplied, traversal reached the handler or one additional class, then hit unresolved external symbols. The right implementation text nevertheless existed in the index.
3. **Selection and budget:** on the original `POST /v1/rag` case, traversal reached many nodes, but seven core relationships were never discovered; at 16 KB, a large `run_rag` function consumed much of the passage allocation, and an additional relationship was excluded by budget. A 4 KB budget was structurally too small for the complete ideal primary trace.

**Architectural conclusion:** prioritize faithful route composition, internal call-target resolution, and truthful partial-trace reporting before optimizing BFS versus DFS or raising token limits. **No new query-time policy was validated or deployed** under #359.

## 2. The original problem and desired outcome

### What users wanted to ask

The motivating question, the Step 0 question used verbatim in [`DOCS/evaluations/359-primary/questions.json`](/DOCS/evaluations/359-primary/questions.json), was: **“Trace the execution path from POST /v1/rag through the orchestrator to vector retrieval. Identify the actual Python functions and files involved, explain the call sequence, and distinguish direct function calls from HTTP service calls. Base the answer on implementation code rather than documentation or historical reports.”** This is not satisfied by an overview of the services or by naming the route handler. The answer needs source evidence of the causal chain, including callers, callees, dispatch boundaries and service transitions.

### Why the existing RAG approach struggled

Earlier diagnostics identified several separable failure stages:

- **Discovery:** semantic vector seeds could rank documentation ahead of the code that implements the requested behavior. Lexical searches and exact structural lookup could identify different candidate entry points.
- **Navigation:** graph edges were incomplete. Service-local imports, injected services, receiver attributes, callbacks, and cross-service HTTP calls were not reliably connected to implementation functions.
- **Selection:** even after locating a correct function, its surrounding relevant functions could be omitted or outranked.
- **Survival:** a passage selected upstream might be eliminated during context assembly because of the 4,096-byte evidence budget.
- **Assessment:** “not truncated” or “not depth-limited” could be mistaken for “complete enough to answer,” although those properties do not establish execution-chain sufficiency.

The question for #359 was not “Can an LLM write a plausible explanation?” It was **“Can a frozen, reproducible query-time evidence selector deliver every core implementation relationship needed to justify the explanation?”**

### Success criteria

The protocol required a correctly resolved public route **and** evidence supporting **all** core, caller-scoped relationships for an end-to-end pass. Partial coverage was recorded but never called a pass. ORACLE-ENTRY tests separately measured what happened when the correct handler was supplied; oracle-assisted results were explicitly prohibited from inflating end-to-end success.

## 3. System boundary and ASCII architecture

The source architecture reviewed on November 10 included language-specific extractors feeding a common intermediate representation (IR), graph assembly/persistence, paged embeddings, a generation-aware vector store, deterministic structural APIs, and an orchestrator/LLM boundary. The diagnostic harness evaluated **stored graph/source evidence**, not model-generated prose.

```text
                         REPOSITORY INGESTION
   Git repository @ pinned SHA
              |
              v
   +-----------------------------+
   | Python / TS / JS / other    |
   | source extraction -> IR     |
   +-----------------------------+
              |
              v
   +-----------------------------+    +------------------------+
   | Graph assembly + symbol    |--->| Canonical node/edge    |
   | resolution                 |    | persistence            |
   +-----------------------------+    +------------------------+
              |                                  |
              |                                  +----> /trace, route nodes
              v                                  |      and graph export
   +-----------------------------+               |
   | Paged chunking / embedding  |               |
   | and persisted source text   |---------------+
   +-----------------------------+               |
              |                                  |
              v                                  v
        Vector index                     READY GENERATION
              |                                  |
              +---------------+------------------+
                              |
                 NORMAL QUERY PATH (reference)
                              |
               Question -> vector seeds -> graph
                  expansion -> passages -> LLM
                              |
                    (A0 primary only)

                  FROZEN #359 DIAGNOSTIC
   Public question: "POST /api/... how does it execute?"
                              |
                              v
                  [RI: Route identification]
                         /            \
              resolved /              \ unresolved/ambiguous
                       v                v
              unique handler       E2E stops and FAILS
                       |
                       v
              [ES: Evidence selection]
                       |
        +--------------+---------------+
        | G0 trace order | G1 BFS       |
        | G2 DFS/callsite| G3 DFS + URL |
        +--------------+---------------+
                       |
             whole-function OR call-site
                       |
                 4 KB OR 16 KB
                       |
              bounded context assembly
                       |
              caller-scoped witnesses
                       |
              [Scorer: all core present?]
                       |
                 PASS / FAIL + cause

   Separate diagnostic path:
   CODEX SEALED ORACLE HANDLER --(only after E2E freeze)-->
       same ES arms -> independently labelled ORACLE-ENTRY

   Expected chains are revealed ONLY after both prediction sets freeze.
   No LLM generation occurs in the frozen selector comparisons.
```

### Where the experiment actually failed

```text
   Mealie public URL         route node?      downstream CALL links?
   POST /api/users/...  -->  prefix missing  --> E2E stops
   GET /api/recipes/... -->  route absent    --> E2E stops

   Given correct handler (oracle):
   handler --> external / unresolved target   X --> implementation
       |             ^                             ^
       +-- its own caller text is delivered        | indexed source exists,
                                                   | but is not discovered

   Primary self-repo:
   route --> handler --> many graph nodes --> missing service/dispatch hops
                                |
                                +--> large function + bounded context
```

## 4. Work performed and solutions attempted

| Period / work item | Intervention or experiment | What it established | What it did **not** establish |
|---|---|---|---|
| September groundwork; lifecycle and provenance improvements | Bounded embedding batches, generation-aware corpus lifecycle, repository inventory, provenance and evidence diagnostics | Built the prerequisite infrastructure for reproducing evidence tests | End-to-end graph memory boundedness or sufficient execution traces |
| November 10 code-intelligence audit and independent review | Source examination of graph construction, retrieval, TRACE/IMPACT, evidence delivery and generation contracts | Identified architectural contracts and suspected gaps in generation identity, extraction completeness, traversal, and workload scale | Live #359 outcomes; audit was static review/synthetic probing |
| November 12 retrieval-mechanism diagnostics | Compared semantic/vector discovery with lexical and structural navigation on recorded questions | Exact endpoint anchoring could find an implementation entry point missed by vector-first seeds; ranked discovery and link navigation are distinct concerns | A deployable winning retrieval policy |
| #354, validated November 13 | Corrected service-local import resolution; rebuilt self-repository graph | In controlled comparison, 1,335 formerly unresolved CALL edges became resolved; `rag_endpoint -> run_rag` became exact; trace reached 7/13 relevant chain nodes with `HANDLED_BY,CALL` | Complete cross-service and dynamic call paths |
| #359 protocol and harness (#360, #364) | Pre-registered scoring, route anchoring, selector arms, byte budgets, frozen rules and tests | Made discovery, selection, survival and sufficiency distinguishable and auditable | An improvement to the production query path |
| C7 independent development questions | Codex independently authored three questions and sealed their answers; Claude predicted before reveal | Exposed nested-function indexing, cross-service route ambiguity, missing evidence paths and budget limits | Unseen-repository generalization |
| Held-out Mealie ingestion and evaluation (#366–#368) | Pinned fork/commit, full ingestion, separate E2E and ORACLE-ENTRY runs, sealed ground truth, scoring | 0/3 E2E; 0/48 oracle-assisted selector cells; 57/57 witnesses present in stored source | Model answer quality, alternate extractors, or scale guarantees |
| Primary `POST /v1/rag` completion (#369) | Ran previously studied motivating case under same frozen harness, then documented final recommendation | Correct route, nonzero traversal, 0/1 E2E, G3 modestly improved coverage but did not pass; 4 KB insufficient | Demonstrated generalizable retrieval improvement |

**Scope note:** The prior #354 fix was an implementation correction, not a modification made in response to the held-out Mealie answers. Under #359 itself the team deliberately **did not** fix route extraction, retune ranking, change graph traversal, expand evidence budgets beyond the prescribed pair, or deploy a new query-time policy.

## 5. Experimental design and anti-overfitting controls

### Frozen inputs

- **Protocol:** pre-registered at merge `45f34e1`; recorded protocol SHA-256 prefix `ca1d1ed5…`.
- **Harness:** diagnostics and tests merged as `c6dd8a0`; selection rules, scoring and runner were held unchanged through the evaluation.
- **Service build:** all four services reported `9f039c43604b2e96a6f96351e00afa178c9c81f8` (`9f039c4`).
- **Self-repository:** repository `f7641840-ba13-5f9d-9ae6-87e1f924709d`, generation `8cbedbb9-9ad6-4c63-83f7-2b7d7659f7e5`, source commit `9f039c4`.
- **Held-out repository:** `mealie-recipes/mealie`, evaluated through a fork whose HEAD was pinned to `1624c22bf70988c7fe404ad586e2f9689f77748d`; repository ID `7da95a1b-11dc-5f74-8d3b-fabe24489ad7`, full generation `611fce96-93f4-4869-b176-2ab668fd2483`.

### Conditions

| Dimension | Arms and interpretation |
|---|---|
| Entry identification | E2E resolves the public `METHOD /path` from graph route nodes; ORACLE-ENTRY is handed the independently sealed correct handler *after* E2E is frozen |
| Graph traversal | G0 deployed `/trace` hop order; G1 breadth-first in call-site order; **G2** depth-first/pre-order in call-site order (**primary preregistered hypothesis**); G3 G2 plus exact URL-literal route hop |
| Evidence unit | P-whole: all chunks of each selected function, in `chunk_index` order; P-call: the first chunk (signature or decorator), plus every chunk containing `<child simple name>(` for a child the arm selected, plus (G3 only) any chunk containing the matched URL literal (protocol §5) |
| Evidence budget | 4,096 versus 16,384 bytes, both assembled under the frozen accounting rules; 16 KB was diagnostic, **not** a deployment proposal |
| Reference | A0: existing vector-seeded `/v1/rag` route, **primary case only**, executed offline with stubs |
| Scoring | Every caller-scoped **core** witness must be supported; “supporting” witnesses separately counted; failures attributed to not discovered, not selected, or budget-cut |
| Traversal constraints | Depth 6 and cap of 300 nodes; never guess through external placeholders or ambiguous targets |

### Independent answer sealing sequence

```text
    Codex (source-based ground truth)       Claude (frozen selector)
       |                                       |
       |-- public questions + SHA-256 -------->|
       |-- oracle / expected hashes ---------> |  hashes only
       |                                       |-- E2E predictions + hash
       |-- reveal oracle handlers -----------> |
       |                                       |-- ORACLE-ENTRY + hash
       |-- reveal expected chains -----------> |-- score frozen output
       |                                       |
       +---------- GitHub issue + PR audit trail -----------+
```

Under ADR-054, the primary question and C7 were **development evidence**. Mealie was the **held-out** repository chosen on structural eligibility before answers were inspected. Even in Mealie, this is a small purposive sample, not a statistically representative benchmark.

### C3 leakage scanner adjudication

The generic-rule scanner returned **exit code 4 twice**:
- **C7 scoring:** it flagged `return`, `result`, `chunk` and `simple`.
- **Mealie scoring:** it flagged `delete`, `file`, `return` and `with`.

In both cases the owner ruled all four terms generic false positives. The automated exit code 4 was **preserved**, rather than editing the rules or pretending the scan passed. The primary case's C3 preflight and score rescans were clean (exit code 0). Raw results and adjudications were retained; this matters to auditability.

## 6. Measurements

### 6.1 Summary of outcomes

| Set | Source / evidence class | E2E | Oracle-assisted outcome | Key distinction |
|---|---|---:|---|---|
| Primary | Previously studied self-repo route `POST /v1/rag` | **0/1** | Selector also failed across its 16 graph-arm cells | Route resolved, but chain remained incomplete |
| C7 | Three independently authored self-repo questions | **0/2 evaluable**; third not evaluable | Partial evidence on evaluable cases; no full sufficient chain | Ambiguous route, nested callback not indexed, cross-service gaps |
| H (Mealie) | Three held-out questions from pinned unseen repository | **0/3** | **0/48 cells** (3 × 4 strategies × 2 passage units × 2 budgets) | All route identification failed; with oracle entry, downstream call resolution failed |

**Do not combine these denominators into a single “accuracy” rate.** The sets have different origin, eligibility, and scoring statuses; the 48 cells are correlated configurations of only three questions.

### 6.2 Primary `POST /v1/rag` — correct route, insufficient graph evidence

- **Preflight:** 18/18 recorded witnesses valid; C3 clean.
- **Route identification:** found the correct `rag_endpoint` handler.
- **E2E:** 0/1 question passes; all 16 G0–G3 × evidence-unit × budget cells fail.
- **Traversal:** 94 functions discovered by G0/G1/G2, 122 by G3. **Seven core relationships never discovered**, notably the embedder dispatch and vector-store side of an HTTP hop.
- **Passage pressure:** 16 KB whole-function context was heavily occupied by `run_rag` (18 of 22 delivered passages), and another core relationship was cut by the budget.
- **Minimum ideal evidence:** 6,452 bytes to cover the complete primary trace, making a 4 KB complete trace impossible under the frozen cost model.
- **A0 baseline:** the existing vector-first path, executed offline with stubs, retrieved documentation rather than the required code evidence and supported 0/12 primary core relationships. No generated answer was evaluated.

**Core witness coverage (out of 12):**

| Selector | 4 KB whole | 16 KB whole | 4 KB call sites | 16 KB call sites |
|---|---:|---:|---:|---:|
| G0, G1, G2 | 2/12 | 4/12 | 4/12 | 4/12 |
| G3 | 3/12 | 5/12 | 5/12 | 5/12 |

G3's extra URL-literal hop helped this **known** development case but did not pass and cannot be claimed to generalize. The primary investigation informed the G3 design; the protocol explicitly disclosed that dependency.

### 6.3 C7 independent development cases

| Case | Intended endpoint | Outcome and interpretation |
|---|---|---|
| C7-1 | `POST /v1/rag/simple` | `NOT_EVALUABLE`: a nested callback (`run_simple_rag._list_outgoing`) could be verified in source but was not represented as required canonical index evidence; two expected witnesses were unavailable |
| C7-2 | `GET /v1/models` | Ambiguous public route across LLM and orchestrator services; with an oracle handler, limited partial coverage (reported 6/13 at 4 KB and 10/13 at 16 KB in the whole-function comparison) |
| C7-3 | `POST /v1/summarize/{ingestion_id}` | Incomplete cross-service execution trace; source relationships beyond service HTTP hops remained hard to discover; increasing budget improved partial coverage but did not yield sufficiency |

C7 diagnosed more than one failure mode, but only **two** cases were evaluable for the official end-to-end denominator. The C7 cases belong to the same source ecosystem that received earlier implementation attention, so they do **not** constitute unseen-repository validation.

### 6.4 Mealie held-out — route and call resolution fail before budget matters

**Frozen ingestion:** 1,728 files; 21,621 graph nodes; 36,983 graph edges; 17,676 saved chunks; 7,758/7,758 embedding-stage nodes processed; 30 extracted route nodes. The completed generation was non-incremental and ready. An initial ingestion attempt failed during embedding at 66/7,758 nodes; a second attempt completed. The exact first-attempt failure cause was **not** established.

**Public questions:**

| Case | Public endpoint | E2E route result |
|---|---|---|
| H-1 | `POST /api/users/forgot-password` | `unresolved_route`; graph had only `POST /forgot-password` without included-router prefix |
| H-2 | `POST /api/users/reset-password` | `unresolved_route`; graph had only `POST /reset-password` without included-router prefix |
| H-3 | `GET /api/recipes/{slug}/exports` | `no_route_node`; class-based controller endpoint absent from extracted route inventory |

All **57/57 expected witnesses** were confirmed both in persisted stored text and at their recorded lines in the pinned source. Codex verified them before sealing, and the scorer rechecked them independently after the reveal (P3). Thus the observed losses were not explained by an absent source corpus. The three questions covered password reset twice, with shared helpers, and recipe export once; breadth is limited.

**ORACLE-ENTRY scores were identical across G0–G3, both passage units, and both budgets:**

| Case | Supported core | Supported supporting | Missing evidence classification |
|---|---:|---:|---|
| H-1 | **2/16** | 0/4 | 18 relationships not discovered; 0 budget-cut |
| H-2 | **2/17** | 0/3 | 18 relationships not discovered; 0 budget-cut |
| H-3 | **5/14** | 0/3 | 12 relationships not discovered; 0 budget-cut |

Only the handler's own caller-scoped relationships were supported. The oracle search reached the handler alone in H-1/H-3, and the handler plus a class in H-2. Calls through `bg_tasks.add_task`, `f_service.reset_password`, `self.service.render_template`, `self.mixins.get_one`, and even an in-repository module-qualified dependency remained unresolved as graph-call destinations. The reason each resolver failed is a **hypothesis to investigate**, not established for all cases by #359.

**Minimum ideal evidence by case:** H-1 5,691 bytes; H-2 4,034 bytes; H-3 4,218 bytes. Only H-2's ideal minimum fits 4 KB. Yet in the actual run, no missing relationship was cut by the budget: all were *not discovered*. Increasing a byte budget cannot surface source passages that graph traversal never selected.

### 6.5 A misleading completeness signal

In the final report, the deployed `/trace` path was reported as “not truncated” and “not depth-limited” on all seven distinct traces, although none of the six evaluable questions had sufficient evidence. Two Mealie traces stopped at the handler. The inspected `assess_trace` logic treated reaching a resolved starting point as satisfying its narrow traversal condition. This is **not** evidence that execution-chain sufficiency was satisfied. A traversal can end cleanly because there are no *resolved* outgoing edges, even while semantically important calls remain external.

The proposed repair was therefore **transparency about incomplete evidence**, not an assertion that every unknown chain can be fully reconstructed.

## 7. What was learned — measured fact versus hypothesis

| Finding | Evidence status | Consequence |
|---|---|---|
| Public prefixes absent from two Mealie route identities; third public route missing | **Measured** | Exact route grounding can fail before selecting any evidence |
| Correct Mealie handlers were present but downstream calls remained external/unresolved | **Measured** | BFS vs DFS comparisons have little effect without usable call edges |
| 57/57 Mealie witnesses available in stored source text | **Measured** | The tested problem is discovery/connection, not wholesale absence of source text |
| In the primary trace, 94–122 functions discovered but seven core relationships unseen | **Measured** | Large traversal reach does not guarantee relevant relationship reach |
| Primary 4 KB capacity insufficient (minimum ideal evidence 6,452 bytes) | **Measured under frozen costing** | A smaller budget is impossible for the full ideal primary trace |
| No Mealie relationship was budget-cut in the frozen runs | **Measured** | Extra context cannot remedy those particular selection failures by itself |
| Route composition does not propagate configuration-derived included-router prefixes | **Likely explanation; partially supported by measured node paths** | Validate composition across FastAPI configurations and multi-hop includes |
| Attribute/DI/background callback resolution is under-modeled | **Hypothesis supported by unresolved call examples** | Investigate binding/dispatch with targeted development fixtures |
| Constructor-to-class navigation strands execution beyond initialization | **Hypothesis supported by H-2 traversal** | Evaluate constructor and method resolution separately |
| Cross-service HTTP targets need an explicit service-to-route connection | **Hypothesis supported by self-repo trace gaps** | Test service topology edges and exact endpoint mapping |
| A stricter trace assessor will improve user trust without false alarms | **Not yet demonstrated** | Needs independent preregistered evaluation including complete chains |

### Useful categorization

- **Representation/completeness defects:** Missing route identities and unresolved intra-repository references.
- **Query-time discovery defects:** Evidence exists but cannot be reached through permitted graph edges.
- **Selection/delivery defects:** Relevant evidence reached but not selected or retained within a context budget.
- **Evaluation/contract defects:** Diagnostic metadata implies operational completion without verifying enough source evidence for the actual question.
- **Separate scaling/operations risks:** Whole-graph materialization, memory peaks, cold-load costs, resource contention, latency.

This categorization prevents treating every failure as “choose a better model,” “add more tokens,” or “switch graph databases.”

## 8. Untested constraints and counterfactuals

| Dimension | What the study measured | What remains unknown / how to test |
|---|---|---|
| **Larger or different generation models** | **No generated answers**; deterministic/source-evidence runs only | Whether better reasoning over the *same evidence* improves correctness, citation quality, or calibrated abstention. Test fixed evidence sets with controlled prompts, model versions and human-verified answers |
| **Larger embedding models** | No controlled comparison between embedding providers or model dimensions | Whether better candidate discovery improves A0/semantic seeds; it cannot alone guarantee that graph edges resolve. Hold corpus, questions, budgets and embedding identity fixed per arm |
| **Stronger GPUs** | No GPU comparison in the selection harness | GPU upgrades could speed Ollama embedding/generation, but are not expected to correct missing route/call edges. Measure ingestion throughput, peak VRAM/RAM, batch time and model latency separately |
| **Longer model context / larger passage budgets** | Only **4 KB and 16 KB** source evidence allocations; 16 KB diagnostic | >16 KB, multi-pass gathering, per-function caps and relevance-aware allocation were not tested. For primary, larger budget might recover some *selected-but-cut* evidence, but **not** seven undiscovered relationships. For Mealie, nothing new is delivered without discovery changes; that is an inference, not an observed >16 KB run |
| **Repository scale** | Two generations with approximately **13,458** and **21,621** graph nodes; successful full Mealie ingestion | No established maximum repository size, complexity distribution, peak graph-build RAM, cold-load latency, sustained query throughput, or simultaneous-user behavior |
| **Graph persistence / memory-boundedness** | Paged artifact embedding was observed; Mealie chunks were persisted incrementally | Graph construction, transactional persistence, export, and TRACE may materialize large graphs. Successful 21K-node ingestion **does not** prove end-to-end bounded memory or O(1) growth |
| **Concurrency and failure recovery** | One held-out ingestion failed; second completed; evaluation read-only | Multiple simultaneous ingestions, failed-job diagnosis, retry idempotence and concurrent queries were not tested under controlled load in #359 |
| **Language and framework portability** | Python/FastAPI-style routes in two repositories | TypeScript/JavaScript, Java, Rust, alternate router frameworks, indirect/reflective calls, RPC/event systems and monorepos require separate ground truth |
| **Statistical representativeness** | One held-out repository, three paths, two with shared helpers | Many repositories and independent feature families, preregistered selection and stratification, uncertainty intervals, and an untouched second holdout |
| **Working-tree evolution** | Frozen commits and ready generations | Edits after ingestion, stale-source detection, branch switching, continuous incremental graph maintenance, and changed-working-tree agent tasks |
| **Useful coding-agent outcomes** | No code patches generated or evaluated | Whether improved retrieval actually improves code changes, tests, debugging task completion, cost or human trust; requires task-level evaluation |

### Scale is multidimensional

```text
   Repository size (files, source bytes, nodes, edges)
                  |
                  +--> extraction/build peak RAM
                  +--> persistence transaction size
                  +--> chunk/embedding throughput + VRAM
                  +--> graph cold-load memory/latency
                  +--> traversal fan-out (degree distribution)
                  +--> retrieved evidence volume and byte caps
                  +--> concurrency, tail latency, restart/recovery

   "Mealie ingested" validates a concrete workload at one scale.
   It does NOT establish linear growth, bounded memory, or production SLOs.
```

The November 10 audit specifically recorded that embedding artifacts were paged and batch-buffered while whole-graph memory remained elsewhere. That context prevents conflating the earlier embedding OOM remediation with graph-streaming architecture.

## 9. Proposed next work (not authorized by #359)

The final #359 deliverable recommended **the smallest defensible query-time transparency change** rather than claiming G2 or a larger budget was successful:

1. Report whether a public endpoint was identified **uniquely**.
2. Show where traversal stopped and which outgoing calls remained unresolved/external or ambiguous.
3. Report relevant service hops that were not followed, when detectable from the graph/source metadata.
4. Report which *already selected* passages/relationships were excluded by the budget.
5. Avoid equating “not truncated / not depth-limited” with “execution trace complete.” Return an explicit **partial/unknown** assessment when material gaps are observable.

**Caveat:** A partial/unknown signal should not pretend to know the full expected chain. The proposed change would recover **zero** missing graph evidence. Its false-positive rate is unknown, because #359 did not include a proven-complete comparison case. It therefore requires **its own issue, a pre-registered independent evaluation, and owner approval before implementation**. That issue is now [#370](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/370) (Phase 6). The project cites roadmap phases rather than GitHub milestones.

### Suggested remediation sequence

| Priority | Separate workstream | Required verification before adoption |
|---|---|---|
| 1 | Route identity completeness: composed prefixes, service scope, class-based controllers | Source-grounded routes; exact public-path resolution and collision/ambiguity tests; no Mealie-specific shortcuts |
| 2 | Internal call resolution: module-qualified calls, injected variables, `self.*`, callbacks, constructors | Independent language/framework fixtures, target disambiguation, unknown preservation, no guessed edges |
| 3 | Cross-service execution graph: HTTP route hops and service topology | Correct request-to-handler mapping and provenance across services; avoid speculative hops |
| 4 | Calibrated trace completeness/uncertainty reporting | Preregistered complete **and** incomplete traces, false-positive/false-negative analysis, no answer leakage |
| 5 | Selection and context allocation after graph improvements | Matched 4 KB/16 KB/>16 KB trials; relevant-byte yield, costs, latency, and task-level success |
| 6 | Workload scaling | Repeated repository-size sweeps, memory/VRAM, graph-load, indexing throughput, query latency and concurrent-user testing |

**Overfitting guard:** Now that Mealie's held-out expected chains have been revealed, these precise three cases are **no longer pristine holdout material for future algorithm selection**. They can become a regression/diagnostic set, but a genuinely unseen repository and sealed questions must be reserved for future generalization claims.

## 10. Artifact integrity, provenance, and governance ledger

### Commit and issue chronology

| Artifact | Reference |
|---|---|
| Issue #359 | https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359 |
| Frozen protocol | `45f34e1` (protocol SHA-256 prefix `ca1d1ed5…`) |
| Diagnostic harness | `c6dd8a0` |
| Held-out public questions | PR #366; squash merge `da917147d837c04e4ae80dae3b790b6e7a96504b` |
| Held-out expected chains | PR #367; squash merge `65eb2960c7cb340d61bfc423a53f24f25d75b08a` |
| Held-out report and raw index | PR #368; squash merge `dec60cec0ab8ad7642085fd57c8e99824a7ee39a` |
| Primary-case report/final recommendation | PR #369; squash merge `efe973d310490e92b20b2759c0145bd19e2aa354` |
| Closure | Issue #359 closed 2026-11-15 03:25 UTC, all deliverables merged |

### Frozen question and answer commitments

| Artifact | SHA-256 |
|---|---|
| Held-out public questions | `711e0d691b0d2296bb8177e0980808e5f1387ebaff5f0f2cc2921eaa9bc497c3` |
| Held-out oracle entry points | `6783da7b20b2f4550917042ac4605e053704c688e7561659267af402b1d43705` |
| Held-out expected chains | `a7279b78e56a6c078ccaeb61c569a643e86d7148fbb31eaa124d344ce6566c36` |
| Held-out graph export (18,870,037 bytes) | `6b636fd72d2df9f8c757ecab85a0a72e179efc90f441ae3eff0b924c39547076` |

### Raw run records

| Case | Preflight | E2E | ORACLE-ENTRY | Score |
|---|---|---|---|---|
| Held-out H | `aad5bbfa…` | `0929dc27…` | `6788c90e…` | `332b5f90…` |
| Primary | `488581f6…` | `39146b27…` | `0078e772…` | `d46a03df…` |

| C7 | `da9e3d41…` | `e925ad17…` | `90b390dc…` | `6ee9ce4c…` |

The table gives **abbreviated** hashes, for identification only. The full hashes, sizes and provenance of all twelve records are tracked in [`DOCS/test_results/raw-index.json`](/DOCS/test_results/raw-index.json) and were posted on issue #359.

The raw files themselves live in `DOCS/test_results/_raw/`. That directory is **git-ignored and is not in the repository**; it exists only on the machine that ran the evaluation. Do not substitute the abbreviations for a checksum verification.

### Source-of-truth documents

All paths are on `main`:

- [Final report and recommendation](/DOCS/test_results/2026-11-14-359-final-report-and-recommendation.md): the three perspectives, the proposal (now issue #370), architectural limitations and untested dimensions.
- [Primary development case results](/DOCS/test_results/2026-11-14-359-primary-development-case-results.md).
- [C7 results](/DOCS/test_results/2026-11-14-359-C7-evidence-selection-results.md) and the revealed C7 files under `DOCS/evaluations/359-C7/`.
- [Held-out mealie results](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md): complete held-out scoring and limitations.
- `DOCS/evaluations/359-H/questions.json` and `DOCS/evaluations/359-H/expected-chains.json`: the released, hash-verified held-out artifacts.
- [Frozen protocol](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md) and [diagnostic harness](/DOCS/evaluations/2026-11-13-359-diagnostic-harness.md).
- [Code-intelligence architecture audit (2026-11-10)](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md): the earlier source and synthetic review; a different evidence class.
- [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md): the evaluation-isolation rationale.
- [`DOCS/status.md`](/DOCS/status.md): the current project record.

**Reproducibility rule:** Keep the original frozen artifacts immutable. Any revised scorer, graph extractor, budget allocation, or traversal design must be run as a *new, versioned evaluation*, with its own preregistered questions and disclosures.

## 11. Final assessment

This investigation did **not** establish that graph-aware repository retrieval is the wrong architectural direction. It established something narrower—and more operationally useful:

> **At the tested commits, with the frozen selector and 4 KB/16 KB budgets, the pipeline could not reliably connect already-indexed implementation evidence into complete execution traces. The next limiting contracts lie at route identity, graph call resolution, cross-service navigation, and evidence-completeness reporting.**

The result does not authorize an implementation. It does establish a defensible ordering of future research: **represent relationships faithfully → expose unresolved boundaries truthfully → select and budget relevant passages → test generated answers and coding-agent outcomes → measure scale.**

No more sophisticated traversal algorithm, larger model, larger GPU, or bigger context should be presented as a demonstrated cure until those dimensions receive independent, controlled measurements.
