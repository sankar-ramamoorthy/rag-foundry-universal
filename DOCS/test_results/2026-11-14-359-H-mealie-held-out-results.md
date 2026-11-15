---
title: "#359 held-out results: route-grounded evidence selection on mealie"
date: 2026-11-14
type: test-results
status: current
summary: "Held-out result (ADR-054 §5). The C3 scanner returned exit code 4 for four generic terms, which the owner manually adjudicated as false positives; the automated scan did not pass. The frozen #359 protocol ran on three Codex-sealed held-out routes in mealie @ 1624c22. All 3 questions are evaluable, and 0 pass end to end: Stage RI resolved none of them (2 unresolved_route from router prefixes, 1 no_route_node). Under ORACLE-ENTRY all 48 cells fail (3 questions x 4 arms x 2 units x 2 budgets), with identical scores in G0-G3. Discovery never leaves the entry handler, because its onward calls are stored as external symbols. All losses are not-discovered; none is a budget cut. The frozen strategy does not generalize to this repository."
tags: [evaluation, results, code-intelligence, evidence-selection, overfitting, held-out, issue-359, issue-342, issue-194]
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[#359 protocol (frozen at 45f34e1)](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)"
  - "[#359 diagnostic harness](/DOCS/evaluations/2026-11-13-359-diagnostic-harness.md)"
  - "[#359 C7 results (development evidence)](/DOCS/test_results/2026-11-14-359-C7-evidence-selection-results.md)"
  - "[Public questions: PR #366](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/366)"
  - "[Revealed expected chains: PR #367](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/367)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #359 held-out results: evidence selection on `mealie`

> **C3: the automated scanner returned exit code 4, and the scan did not
> pass.** It flagged four generic terms: `delete`, `file`, `return` and
> `with`. The owner **manually adjudicated all four as false positives**
> (#359, 2026-11-14). The scanner, its exit status and its raw output in the
> score record are unchanged (§1).

**Evidence class: held-out (ADR-054 §5).** This is the generalization test
(C10) for the strategy frozen at `45f34e1`. Nothing was tuned against
`mealie`. The extractor, rules, retrieval code and protocol were unchanged
throughout.

**Scope.** **3** routes were attempted and **3** were evaluable and scored.
None was a preflight failure or `ground_truth_invalid`. H-1 and H-2 share
password-reset helpers, which narrows the application breadth. Codex
disclosed this in PR #366.

The report separates **verified measurements** (§2–§6), which are read
directly from the frozen records, from **architectural interpretations**
(§7), which are explanations not established by this run.

## 1. Integrity of the run

| Item | Value |
|---|---|
| Protocol | `45f34e1`, sha256 `ca1d1ed5…`, verified at every stage |
| Harness | rules `b8e90173…`, scoring `43f2e7c3…`, runner `9b4fa777…`: byte-identical to the C7 run. The rules were unchanged across stages (`rules_unchanged_across_stages: true`). Checkout `16fc0d5` (differs from C7's `c6dd8a0` in documentation only) |
| Repository / generation | `7da95a1b-11dc-5f74-8d3b-fabe24489ad7` / `611fce96-93f4-4869-b176-2ab668fd2483`, commit `1624c22b…`; full non-incremental build; ready and unchanged at every stage |
| Services | all four at `9f039c4` (`prod-2026-11-13-806am`) at every check |
| Embedding configuration | **not verified**: not exposed over HTTP, and not inferred from code defaults (#359) |
| Questions (step 1) | PR #366, `711e0d69…`, matching the posted hash |
| Oracle entry points (revealed at step 4) | `6783da7b…`, matching the sealed commitment; revealed only after the E2E hash was posted |
| Expected chains (revealed at step 5) | PR #367, `a7279b78…`, matching the sealed commitment; revealed only after the ORACLE-ENTRY hash was posted |
| Pinned source for the P3 check | blobless clone of `sankar-ramamoorthy/mealie`, commit `1624c22b…`, tree `996bb999…`, matching the recorded tree hash |
| Raw records | preflight `aad5bbfa…`, E2E `0929dc27…`, ORACLE-ENTRY `6788c90e…`, score `332b5f90…`, all in [`raw-index.json`](/DOCS/test_results/raw-index.json) |
| Generation and embedding calls | none: A0 was not run (P4), and passages were fetched with the stored vector |

The E2E and ORACLE-ENTRY records were re-hashed before and after scoring, and
both were unchanged.

**Input PRs.** This report does not commit the questions or the revealed
chains. They live in two PRs:
- [PR #366](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/366)
  publishes `DOCS/evaluations/359-H/questions.json` (step 1).
- [PR #367](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/367)
  adds `DOCS/evaluations/359-H/expected-chains.json` (step 5). It is
  **stacked on #366**: its base is #366's branch, so #366 merges first.

Both were read from their branches and verified by hash; neither was merged
for this run. Until they merge, those files are reachable only through the
PRs.

### C3 rescan with the revealed terms: exit code 4, manually adjudicated

**The automated scan did not pass.** It returned exit code 4. Its raw output
is preserved unchanged in the score record (`c3_rescan_with_revealed_terms`:
`hits: [delete, file, return, with]`, `clean: false`). The owner ruled each
hit a false positive. That ruling is a manual adjudication and does not change
the scanner or its result. C3 compliance (adjudicated) and the scanner result
(exit code 4) are recorded separately.

| Term | Occurrence in the frozen rules module | Type | Source in the revealed files | Owner ruling |
|---|---|---|---|---|
| `delete` | line 28, `ROUTE_IN_QUESTION` regex: `(GET\|POST\|PUT\|DELETE\|PATCH)` | HTTP method name in the generic route pattern | Match-pattern fragments H-1/R10 and H-2/R17 | False positive: generic HTTP DELETE method |
| `file` | docstring, line 9 ("…file…"), and an `INTERPRETATIONS` string, line 83 ("the file stem for a module node") | Generic English and protocol vocabulary | H-3/R14 | False positive: generic documentation and interpretation terminology |
| `return` | 23 `return` statements | Python keyword | Match-pattern fragments H-1/R13, R20; H-2/R20; H-3/R15–R17 | False positive: standard Python keyword |
| `with` | `INTERPRETATIONS` strings, lines 42–43 ("With zero matches…", "with the same method…") | English preposition | H-1/R3 | False positive: ordinary English terminology |

`service` overlapped too, and the scanner reported it under the fixed generic
list, as designed (`allowed_generic_overlap`). As in C7, the rules file has
been byte-identical since `49fde85`, which predates these questions.

## 2. Question status and Stage RI (measured)

| Question | Route | Status | Stage RI (E2E) | Oracle entry point |
|---|---|---|---|---|
| H-1 | `POST /api/users/forgot-password` | evaluable | **`unresolved_route`**; suffix candidate `route:mealie:POST:/forgot-password` | `mealie/routes/users/forgot_password.py#forgot_password` |
| H-2 | `POST /api/users/reset-password` | evaluable | **`unresolved_route`**; suffix candidate `route:mealie:POST:/reset-password` | `mealie/routes/users/forgot_password.py#reset_password` |
| H-3 | `GET /api/recipes/{slug}/exports` | evaluable | **`no_route_node`** | `mealie/routes/recipe/exports.py#RecipeExportController.get_recipe_as_format` |

- **57/57** expected witnesses (20 + 20 + 17) are in stored text and valid at
  their recorded lines in the pinned source (P3).
- Index evidence gaps: none.
- Unwarranted disambiguations: none.
- RI produced no wrong handler; it refused, as the rules require (5a.6).

## 3. End-to-end result (official)

**0 of 3 evaluable questions pass end to end, in every arm, passage unit and
budget.** Stage RI resolved none of them, so evidence selection never ran
under E2E. `official_summary.ri_not_resolved` lists all three questions.

`end_to_end_pass_counts` is empty in the score record, because no E2E cell
exists to count. The 0/3 is read from `ri_not_resolved` with
`denominator: 3`. The scorer was not changed to print it.

## 4. ORACLE-ENTRY: all arms (oracle-assisted, never end-to-end; C12)

Core relationships supported. Each row holds for G2 (primary), G0, G1 and G3
alike, in both units and at both budgets:

| Question | Core supported | Supporting supported | Sufficiency |
|---|---:|---:|---|
| H-1 | 2/16 | 0/4 | FAIL everywhere |
| H-2 | 2/17 | 0/3 | FAIL everywhere |
| H-3 | 5/14 | 0/3 | FAIL everywhere |

- **The arms are indistinguishable.** G0 (deployed `/trace`), G1 (BFS), G2
  (DFS) and G3 (G2 plus the URL-literal hop) reach the same functions and
  deliver the same passages for every question.
- **G3's hop fired** on H-1 and H-2, but it matched the handler's own route
  decorator literal and led back to the entry.
- **Whole function vs call site:** they score identically. Only H-2's bytes
  differ (P-whole 4,179 B vs P-call 1,234 B).
- **4 KB vs 16 KB:** they score identically. Budget truncation occurs only for
  H-2 P-whole at 4 KB (5 of 6 passages, 3,817 B), and it costs no
  relationship.

## 5. G2: type of support and where evidence was lost (measured)

Core and supporting relationships, G2, both units, both budgets:

| Question | graph_and_source | source_only | not discovered | not selected | cut by budget | index missing |
|---|---:|---:|---:|---:|---:|---:|
| H-1 | 0 | 2 | 18 | 0 | 0 | 0 |
| H-2 | 0 | 2 | 18 | 0 | 0 | 0 |
| H-3 | 0 | 5 | 12 | 0 | 0 | 0 |

- **Every loss is "not discovered"; none is a budget cut.**
- **Every supported relationship is `source_only`.** Each has the entry
  handler as its caller and is supported by the handler's own delivered text,
  not by a graph edge. Under ORACLE-ENTRY the route relationship (R1) has no
  structural edge.
- **Every expected relationship whose caller is the entry handler is
  supported.** All unproven relationships have a caller one or more hops
  beyond the entry.

**Discovery from the entry handler** (from the ORACLE-ENTRY record):

| Question | Functions reached | CALL edges followed | Calls recorded as `EXTERNAL_SYMBOL` (suppressed) |
|---|---:|---:|---|
| H-1 | 1 | 0 | `bg_tasks.add_task`, `fastapi.Header`, `router.post` |
| H-2 | 2 (handler + class `PasswordResetService`) | 1 | `f_service.reset_password`, `fastapi.Depends`, `router.post` |
| H-3 | 1 | 0 | `mealie.core.dependencies.get_temporary_path`, `router.get`, `self.mixins.get_one`, `self.service.render_template`, `starlette.background.BackgroundTask`, `starlette.responses.FileResponse` |

The next functions in the expected chains are not CALL targets of the entry
handler in this generation. Examples:
- H-2/R2's callee `PasswordResetService.reset_password` is reached only as
  `EXTERNAL_SYMBOL:f_service.reset_password`.
- H-3/R2's in-repo callee `mealie/core/dependencies/dependencies.py#get_temporary_path`
  appears as `EXTERNAL_SYMBOL:mealie.core.dependencies.get_temporary_path`.
- H-2's one CALL edge targets the class node, not a method in the chain
  (`chain_positions`: the class is not a chain function).

Edges beyond the first hop were not examined, so this run does not establish
whether discovery would have continued past the first hop.

## 6. Minimum-evidence bound (ORACLE BOUND: uses ground truth, not a selector result)

| Question | Bytes | Passages | Fits 4,096 | Fits 16,384 | Uncoverable |
|---|---:|---:|---|---|---|
| H-1 | 5,691 | 10 | no | yes | — |
| H-2 | 4,034 | 9 | **yes** | yes | — |
| H-3 | 4,218 | 7 | no | yes | — |

The bound is the same with route relationships counted as witness passages or
as structural. Unlike C7, one held-out trace (H-2) fits 4 KB. At 16 KB every
bound fits, yet the selectors deliver at most 4,179 bytes, because discovery
supplies nothing more to deliver.

## 7. Architectural interpretations (hypotheses, not established by this run)

**Measured (§2, §5):**
- No question's route resolved.
- Every unproven relationship is not discovered.
- The entry handlers' onward calls end at `EXTERNAL_SYMBOL` nodes or, in H-2,
  at a class node.
- The next chain functions are not CALL targets of the entry handler.

**Not measured:** *why* the extractor produced those nodes and edges. The
items below are hypotheses about that, to be tested separately. None is a
proposal to change anything.

1. **Route identification needs router composition (hypothesis).** Routes are stored with
   their router-local path. The `/api/users` and `/api/recipes` prefixes come
   from router inclusion, which the extractor does not compose. H-3's
   class-based controller route produced no route node at all. The graph holds
   only 30 route nodes.
2. **Calls through injected or attribute-held objects are not resolved
   (hypothesis covering dependency injection, attribute resolution,
   background tasks and imports).** The
   unresolved calls include:
   - FastAPI dependency parameters (`f_service`, `bg_tasks`);
   - `self.service` and `self.mixins` on a controller;
   - deferred `BackgroundTask` callbacks.

   All of them end at `EXTERNAL_SYMBOL`. Even a module-qualified in-repo
   function (`mealie.core.dependencies.get_temporary_path`) did not resolve,
   which suggests an import-resolution gap as well as a type-inference gap.
3. **Constructor calls bind to the class, not to a method (hypothesis).** This explains why
   H-2's single followed edge does not continue into the chain.
4. **No traversal order or budget can recover this.** G0–G3 and both budgets
   are identical because the graph gives them one or two nodes to order. The
   C7 finding that "discovery is the bottleneck at 16 KB" holds here in a
   stronger form: discovery stops at the entry.

## 8. Findings

1. **The frozen strategy does not generalize to `mealie`.** These are two
   separate results:
   - **E2E (official): 0/3.**
   - **ORACLE-ENTRY (oracle-assisted, never end-to-end): 0/48 cells**
     (3 questions × 4 arms × 2 units × 2 budgets).
2. **The first failure is route identification** (2 `unresolved_route`, 1
   `no_route_node`). It is the anticipated router-prefix failure, measured
   rather than fixed.
3. **Given the correct handler, discovery stops at the handler.** All losses
   are not discovered, with no budget cut, no selection miss and no index gap.
4. **All support is source-only**, coming from the handler's own text. No
   held-out relationship is supported by a graph edge.
5. **Arm, passage unit and budget make no difference on this repository.**
6. **The 4 KB budget is not the binding limit here.** H-2's bound fits 4 KB,
   and the delivered bytes never exceed 4,179.

## 9. Limitations

- Three questions, two of which share password-reset helpers (H-1 and H-2),
  which narrows the application breadth.
- A single held-out repository (`mealie` @ `1624c22`).
- The C3 scanner returned exit code 4. Compliance rests on the owner's manual
  adjudication of four false positives (§1), not on the automated scan.
- The deployed embedding configuration is unverified (§1). The ORACLE-ENTRY
  findings come from graph discovery, which does not use embeddings. Passage
  text was fetched with the stored vector.
- A0 (the current `/v1/rag` path) was not run (P4).
- The first ingestion attempt (`0c28f05e…`) failed during embedding, and its
  cause is undetermined. The scored generation is the second attempt.
- The ground truth reflects one independent author's reading of the
  implementation, including the core and supporting tiers.
- Edges beyond the first hop were not examined (§5).
