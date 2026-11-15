---
title: "#359 primary development case: POST /v1/rag under the frozen harness"
date: 2026-11-14
type: test-results
status: current
summary: "Previously studied primary development case (ADR-054 development evidence; not independent or held-out validation). The frozen #359 protocol on POST /v1/rag in the self-repository, generation 8cbedbb9. Stage RI resolves correctly and discovery reaches 94 functions (122 in G3), yet every arm, unit and budget fails sufficiency. G2 supports 2–4 of 12 core relationships, and G3 at most 5/12. At 16 KB, 7 core relationships are not discovered (dispatch into the embedder, and the vector-store side of an HTTP hop) and 1 is cut by budget, which one large function consumes. The minimum evidence is 6,452 B, so 4 KB cannot hold the trace. A0 (today's /v1/rag path) delivers only documentation: 0/12. The C3 rescan was clean."
tags: [evaluation, results, code-intelligence, evidence-selection, overfitting, issue-359, issue-342, issue-194]
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[#359 protocol (frozen at 45f34e1)](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)"
  - "[#359 diagnostic harness](/DOCS/evaluations/2026-11-13-359-diagnostic-harness.md)"
  - "[Primary case files (§4, public)](/DOCS/evaluations/359-primary/)"
  - "[#359 C7 results](/DOCS/test_results/2026-11-14-359-C7-evidence-selection-results.md)"
  - "[#359 held-out mealie results](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md)"
  - "[#359 final report and recommendation](/DOCS/test_results/2026-11-14-359-final-report-and-recommendation.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #359 primary development case: `POST /v1/rag`

> **Classification: previously studied PRIMARY DEVELOPMENT CASE (ADR-054
> development evidence).** This is the route that motivated #342 and #359,
> and it has been studied repeatedly. Generation `8cbedbb9` contains our own
> reports that name its chain. **It is not independent or held-out
> validation.** It is reported separately from C7 (within-repository routes,
> independent author) and from `mealie` (held-out repository).

Run authorized by the owner on #359 (2026-11-14, decision 1) under the
unchanged protocol, harness, service revision and generation.

## 1. Integrity of the run

| Item | Value |
|---|---|
| Protocol | `45f34e1`, sha256 `ca1d1ed5…`, verified at every stage |
| Harness | rules `b8e90173…`, scoring `43f2e7c3…`, runner `9b4fa777…`: the same bytes as the C7 and `mealie` runs. Rules unchanged across stages. Checkout `dec60ce` |
| Repository / generation | `f7641840…` / `8cbedbb9` (commit `9f039c4`), ready and unchanged before and after every stage |
| Services | all four at `9f039c4` |
| Inputs (public, §4) | questions `02d770a2…`, oracle `30c0555c…`, chains `0d79f3e3…` |
| Stage order | preflight, E2E (hash posted on #359 before ORACLE-ENTRY), ORACLE-ENTRY, score. There is no sealing, because the primary inputs are public |
| Raw records | preflight `488581f6…`, E2E `39146b27…`, ORACLE-ENTRY `0078e772…`, score `d46a03df…`, all in [`raw-index.json`](/DOCS/test_results/raw-index.json) |
| Model calls | none. A0 ran with embedding and generation stubbed (P4: primary set only), and passages were fetched with the stored Step 0 vector |
| C3 | preflight scan clean; rescan at scoring clean (`hits: []`, exit code 0) |

- **Witnesses:** 18/18 §4 witnesses are in stored text and valid at their
  recorded lines at `9f039c4`.
- **Status:** the question is evaluable, with no index gap.
- **Consistency check:** Stage RI's handler equals the oracle handler, and
  ORACLE-ENTRY's evidence selection is identical to E2E's
  (`es_identical: true`).

## 2. Stage RI and end-to-end result (official)

Stage RI is `resolved`: `route:rag_orchestrator:POST:/v1/rag` → `HANDLED_BY`
→ `rag_orchestrator/src/api/v1/routes.py#rag_endpoint`, which is correct.

**End to end: 0/1, in all 16 cells (4 arms × 2 units × 2 budgets).**

## 3. All arms, core relationships supported (E2E)

12 core and 6 supporting relationships (§4).

| Unit | Budget | G2 (primary) | G0 | G1 | G3 |
|---|---:|---:|---:|---:|---:|
| P-whole | 4096 | 2/12 | 2/12 | 2/12 | 3/12 |
| P-whole | 16384 | 4/12 | 4/12 | 4/12 | 5/12 |
| P-call | 4096 | 4/12 | 4/12 | 4/12 | 5/12 |
| P-call | 16384 | 4/12 | 4/12 | 4/12 | 5/12 |

- G0, G1 and G2 score identically.
- G3 is one relationship better everywhere. Its URL-literal hop reaches the
  vector-store route handler, so R15 becomes `graph_and_source`.
- No cell passes.
- ORACLE-ENTRY gives the same counts. The only difference is that the route
  relationship R1 is `source_only` there rather than structural (fixed
  interpretation 7).

**A0 (today's `/v1/rag` retrieval, offline with stubs):** 0/12 core, 0/6
supporting at both budgets, and 0 relevant bytes. Its 38-chunk pool and
delivered context are documentation, including this project's own
diagnostic reports, not implementation code.

## 4. G2: where evidence was lost (E2E, P-call, 16 KB)

| Relationship | Tier | Class | Outcome |
|---|---|---|---|
| R1 route, R2 `rag_endpoint→run_rag`, R11 `run_rag→hybrid_retrieve` | core | route / static | `graph_and_source` |
| R7 `run_rag→embed_query` | core | indirect reference | `source_only` |
| R8 `embed_query` dispatch, R9a/R9b `OllamaEmbedder.embed→_strict→_post`, R10 `_post→Ollama /api/embed` | core | dynamic dispatch / static / external HTTP | **not discovered** |
| R14 `hybrid_retrieve→POST /v1/vectors/search` | core | cross-service HTTP | **cut by budget** |
| R15 route, R16 `similarity_search→PgVectorStore.similarity_search`, R17 SQL `<=>` | core | route / indirect / SQL | **not discovered** (the far side of the HTTP hop) |
| R3, R5 | supporting | static | `graph_and_source` |
| R4, R6, R12, R13 | supporting | HTTP / static | cut by budget |

**Budget is binding here, unlike `mealie`.**
- Discovery reaches 94 functions. Their P-call passages total 103,788 B, and
  P-whole 171,708 B.
- At 16 KB, **18 of the 22 delivered passages come from one function,
  `run_rag`**. The rest are `rag_endpoint`, `get_settings`, `_new_trace_id`
  and one utility.
- So 97% of delivered bytes are from chain callers (`relevant_share` 0.97),
  but most are `run_rag` passages that do not hold the missing witnesses.
- `hybrid_retrieve` (DFS position 11) never gets budget.

**Budget attribution, G2:**
- P-whole gains core R7 and R11, plus supporting R3 and R5, from 4 KB to
  16 KB.
- P-call gains no core relationship.

## 5. Minimum-evidence bound (ORACLE BOUND: uses ground truth, not a selector result)

| Route relationships | Bytes | Passages | Fits 4,096 | Fits 16,384 |
|---|---:|---:|---|---|
| witness passage | 6,452 | 9 | no | yes |
| structural | 6,452 | 9 | no | yes |

4 KB cannot hold this trace whatever the traversal. 16 KB could, but no arm
gets there: 7 core relationships are never discovered, and the budget goes to
one large function.

## 6. Findings (measured)

1. **RI succeeds on the familiar route.** It resolves the correct handler,
   unlike all three `mealie` routes.
2. **Discovery is broad but incomplete.**
   - G0–G2 reach 94 functions, and G3 reaches 122.
   - The missing core evidence sits behind dynamic dispatch into the
     embedder (R8–R10) and across the HTTP hop to the vector store
     (R15–R17).
   - G3's literal hop crosses that hop structurally (R15) but cannot deliver
     the evidence beyond it within budget.
3. **Selection is the second loss.** DFS order plus a single large function
   (`run_rag`) consumes the 16 KB budget, so P-call does not improve from
   4 KB to 16 KB.
4. **4 KB is structurally insufficient** (bound 6,452 B), as on both C7
   routes.
5. **Today's `/v1/rag` path (A0) retrieves documentation, not code,** for
   this question: 0/12.

## 7. Limitations

- Development evidence only, on a single route that has been studied
  repeatedly. The corpus contains our own reports naming the chain, which A0
  retrieves.
- The rules were designed with this case in view (C5). G3's literal hop in
  particular was designed knowing this case's H13 gap.
- The §4 ground truth was written by the protocol author, not by an
  independent author.
- One question.
