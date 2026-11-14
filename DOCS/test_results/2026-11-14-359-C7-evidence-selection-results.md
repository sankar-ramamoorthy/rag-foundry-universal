---
title: "#359 C7 results: route-grounded evidence selection on three independently sealed routes"
date: 2026-11-14
type: test-results
status: current
summary: "Frozen #359 protocol on three Codex-sealed C7 routes in the self-repository. Of 3 attempted questions, 2 are evaluable and 0 pass end to end in any arm, unit or budget. The primary arm G2 fails at both 4 KB and 16 KB. For both evaluable routes the minimum evidence needed exceeds 4 KB, so the 4 KB budget cannot hold the required trace whatever the traversal. At 16 KB the binding losses are discovery gaps: cross-service hops and handlers not reached through CALL edges. Development evidence only."
tags: [evaluation, results, code-intelligence, evidence-selection, overfitting, issue-359, issue-342, issue-194]
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[#359 protocol (frozen at 45f34e1)](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)"
  - "[#359 diagnostic harness](/DOCS/evaluations/2026-11-13-359-diagnostic-harness.md)"
  - "[C7 questions and revealed sealed files](/DOCS/evaluations/359-C7/)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #359 C7 results: route-grounded evidence selection

**Evidence class: development evidence (ADR-054); not a generalization
result.** C7 is the within-repository overfitting check (C7). Generalization
still requires the held-out `mealie` run (C10).

**Scope of the result.** **3** routes were attempted, **2** were evaluable and
scored, and **1** was a preflight failure. This check does **not** meet a
three-scored-route standard, and the smaller scored sample weakens it (owner
decision on #359, 2026-11-14).

## 1. Integrity of the run

| Item | Value |
|---|---|
| Protocol | `45f34e1`, sha256 `ca1d1ed5…`, verified on `HEAD` at every stage |
| Harness | `main` @ `c6dd8a0`; the rules file hash is identical in the E2E, ORACLE-ENTRY and score records |
| Repository / generation | `f7641840…` / `8cbedbb9` (commit `9f039c4`), ready and unchanged before and after every stage and again after scoring |
| Services | all four reported `git_sha` `9f039c4` at every check |
| Questions (step 1) | `0c587a72…`, matching the hash posted on #359 |
| Oracle entry points (sealed; revealed at step 4) | `36dedd5c…`, matching the sealed hash. Revealed only after the E2E hash was posted. |
| Expected chains (sealed; revealed at step 5) | `0e8b22ec…`, matching the sealed hash. Revealed only after the ORACLE-ENTRY hash was posted. |
| Raw records | preflight `da9e3d41…`, E2E `e925ad17…`, ORACLE-ENTRY `90b390dc…`, score `6ee9ce4c…`, all in [`raw-index.json`](/DOCS/test_results/raw-index.json) |
| Generation and embedding | none: A0 was not run (P4), and passages were fetched with the stored vector |

The revealed files are committed under `DOCS/evaluations/359-C7/` byte for
byte. They are marked `-text`, so line-ending normalization cannot change the
hashed bytes.

### C3 rescan with the revealed terms: flagged, owner ruling needed

The score command exited with code 4: the C3 rescan of the selection-rules
module found four ground-truth terms. Per the harness contract, a hit would
invalidate the outputs, so the results below stand **pending the owner's
ruling** on these hits. Evidence for each:

| Term | Source in the revealed files | Occurrence in the rules module |
|---|---|---|
| `return` | witness regexes C7-1/R18 and C7-3/R12 | the Python keyword in `return` statements |
| `result` | witness regexes C7-3/R4 and C7-3/R8 | a local variable in Stage RI |
| `chunk` | a question word that also occurs in an identifier | docstring and comment text ("chunk order"), the frozen protocol's own term (§3, §5) |
| `simple` | the C7-1 route `/v1/rag/simple` | "simple name" in interpretation strings, the frozen protocol's wording (§5: "child simple name") |

- None of the four is a ground-truth canonical ID, symbol name or file path.
- The rules file has not changed since its first commit (`49fde85`).
- I did not read the C7 questions until after that commit, and the chains
  until step 5.
- The scanner does not exclude Python keywords that appear outside attribute
  position. That limitation explains `return`.
- The scanner was **not** changed after the reveal.

## 2. Question status

| Question | Route (question text) | Status | Stage RI | Oracle entry point |
|---|---|---|---|---|
| C7-1 | `POST /v1/rag/simple` | **preflight_failure** (`source_valid_index_missing`: R14, R15) | `resolved` → `simple_rag_endpoint` (correct) | same |
| C7-2 | `GET /v1/models` | evaluable | **`ambiguous_route`**: two route nodes, in `llm_service` and `rag_orchestrator` | `llm_service/…/main.py#list_models` |
| C7-3 | `POST /v1/summarize/{ingestion_id}` | evaluable | `resolved` → `generate_summary` (correct) | same |

- No expected witness failed the pinned-source check, so no question is
  `ground_truth_invalid`.
- No arm produced an `unwarranted_disambiguation`.
- Where the RI handler equals the oracle handler (C7-1, C7-3), the ORACLE-ENTRY
  selection is byte-identical to E2E, which is the §5b consistency check.

## 3. End-to-end result (official)

**0 of 2 evaluable questions pass end to end, in every arm, passage unit and
budget.**

- C7-2 fails at Stage RI, so evidence selection never ran for it under E2E.
- C7-3 resolves at RI but fails sufficiency everywhere.
- C7-1 is `NOT_EVALUABLE` and is counted neither way.

## 4. Primary arm G2 (declared before the run; C8)

Core relationships supported:

| Question | Condition | P-whole 4 KB | P-whole 16 KB | P-call 4 KB | P-call 16 KB |
|---|---|---:|---:|---:|---:|
| C7-3 | **E2E** | 4/19 | 7/19 | 4/19 | 12/19 |
| C7-2 | E2E | not run (RI `ambiguous_route`) | | | |
| C7-2 | ORACLE-ENTRY | 6/13 | 10/13 | 6/13 | 10/13 |
| C7-3 | ORACLE-ENTRY | 4/19 | 7/19 | 4/19 | 12/19 |
| C7-1 | E2E (diagnostic, NOT_EVALUABLE) | 5/17 | 12/17 | 2/17 | 10/17 |

**G2 fails at 4 KB and at 16 KB.** ORACLE-ENTRY rows are oracle-assisted and
are not end-to-end results (C12).

## 5. All arms (C8: reported, not selected)

No arm passes anywhere. Where another arm supports more relationships than G2,
that is reported as a hypothesis, not as the finding (C8). Examples: G0/G1 on
C7-2 at 4 KB (8/13 against 6/13), and G0 on C7-3 P-whole at 16 KB (10/19
against 7/19). G3 is never better than G2 on an evaluable question, and on
C7-3 P-call at 16 KB it is worse (9/19 against 12/19), because its extra
cross-service reach is cut by the budget.

### All arms, core relationships supported

| Question | Condition | Unit | Budget | G2 (primary) | G0 | G1 | G3 |
|---|---|---|---:|---:|---:|---:|---:|
| C7-1 | E2E | P-whole | 4096 | 5/17 | 5/17 | 5/17 | 5/17 |
| C7-1 | E2E | P-whole | 16384 | 12/17 | 13/17 | 12/17 | 12/17 |
| C7-1 | E2E | P-call | 4096 | 2/17 | 2/17 | 2/17 | 4/17 |
| C7-1 | E2E | P-call | 16384 | 10/17 | 10/17 | 10/17 | 11/17 |
| C7-1 | ORACLE-ENTRY | P-whole | 4096 | 5/17 | 5/17 | 5/17 | 5/17 |
| C7-1 | ORACLE-ENTRY | P-whole | 16384 | 12/17 | 13/17 | 12/17 | 12/17 |
| C7-1 | ORACLE-ENTRY | P-call | 4096 | 2/17 | 2/17 | 2/17 | 4/17 |
| C7-1 | ORACLE-ENTRY | P-call | 16384 | 10/17 | 10/17 | 10/17 | 11/17 |
| C7-2 | E2E | — | — | not run (RI `ambiguous_route`) | | | |
| C7-2 | ORACLE-ENTRY | P-whole | 4096 | 6/13 | 8/13 | 8/13 | 6/13 |
| C7-2 | ORACLE-ENTRY | P-whole | 16384 | 10/13 | 10/13 | 10/13 | 10/13 |
| C7-2 | ORACLE-ENTRY | P-call | 4096 | 6/13 | 8/13 | 8/13 | 6/13 |
| C7-2 | ORACLE-ENTRY | P-call | 16384 | 10/13 | 10/13 | 10/13 | 10/13 |
| C7-3 | E2E | P-whole | 4096 | 4/19 | 6/19 | 4/19 | 4/19 |
| C7-3 | E2E | P-whole | 16384 | 7/19 | 10/19 | 8/19 | 7/19 |
| C7-3 | E2E | P-call | 4096 | 4/19 | 6/19 | 4/19 | 4/19 |
| C7-3 | E2E | P-call | 16384 | 12/19 | 12/19 | 12/19 | 9/19 |
| C7-3 | ORACLE-ENTRY | P-whole | 4096 | 4/19 | 6/19 | 4/19 | 4/19 |
| C7-3 | ORACLE-ENTRY | P-whole | 16384 | 7/19 | 10/19 | 8/19 | 7/19 |
| C7-3 | ORACLE-ENTRY | P-call | 4096 | 4/19 | 6/19 | 4/19 | 4/19 |
| C7-3 | ORACLE-ENTRY | P-call | 16384 | 12/19 | 12/19 | 12/19 | 9/19 |

C7-1 rows are diagnostic only (NOT_EVALUABLE).

## 6. G2: type of support and where evidence was lost

Core relationships, by category:

| Question | Condition | Unit | Budget | graph_and_source | source_only | not discovered | not selected | cut by budget | index missing | relevant / delivered bytes |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| C7-1 | E2E | P-whole | 4096 | 1 | 4 | 2 | 0 | 8 | 2 | 3,366 / 3,969 |
| C7-1 | E2E | P-whole | 16384 | 5 | 7 | 2 | 0 | 1 | 2 | 12,611 / 16,232 |
| C7-1 | E2E | P-call | 4096 | 1 | 1 | 2 | 3 | 8 | 2 | 3,378 / 4,086 |
| C7-1 | E2E | P-call | 16384 | 5 | 5 | 2 | 3 | 0 | 2 | 10,121 / 16,379 |
| C7-2 | ORACLE-ENTRY | P-whole | 4096 | 2 | 4 | 3 | 0 | 4 | 0 | 1,424 / 4,047 |
| C7-2 | ORACLE-ENTRY | P-whole | 16384 | 4 | 6 | 3 | 0 | 0 | 0 | 4,728 / 16,109 |
| C7-2 | ORACLE-ENTRY | P-call | 4096 | 2 | 4 | 3 | 0 | 4 | 0 | 1,424 / 4,047 |
| C7-2 | ORACLE-ENTRY | P-call | 16384 | 4 | 6 | 3 | 0 | 0 | 0 | 4,728 / 8,172 |
| C7-3 | E2E | P-whole | 4096 | 3 | 1 | 7 | 0 | 8 | 0 | 3,171 / 4,031 |
| C7-3 | E2E | P-whole | 16384 | 4 | 3 | 7 | 0 | 5 | 0 | 5,048 / 16,285 |
| C7-3 | E2E | P-call | 4096 | 3 | 1 | 7 | 0 | 8 | 0 | 2,455 / 4,048 |
| C7-3 | E2E | P-call | 16384 | 7 | 5 | 7 | 0 | 0 | 0 | 9,458 / 15,144 |

ORACLE-ENTRY rows for C7-1 and C7-3 are identical to E2E (the consistency
check) and are omitted here; the raw score record has them.

**Unproven core relationships for G2, P-call, 16 KB:**

| Question | Relationships | Cause | Where |
|---|---|---|---|
| C7-3 | R13–R19 (2 route, 1 static, 4 SQL) | not discovered | `ingestion_service` handlers behind the orchestrator's HTTP calls: `chunks.py#get_chunks_by_ingestion`, `db_utils.py#get_chunk_texts_by_ingestion_id`, `summary.py#save_summary` |
| C7-2 | R12–R14 (external HTTP) | not discovered | `model_catalog.py#_fetch_openrouter`, `#_fetch_openai_compatible`, `#_fetch_ollama`: not reached through CALL edges from `list_models` |
| C7-1 (diagnostic) | R17, R18 | not discovered | `llm_service/…/main.py#generate`, across an HTTP hop |
| C7-1 (diagnostic) | R4–R6 | not selected | P-call kept no passage of `run_simple_rag` with these witnesses (an indirect reference and HTTP calls, not `name(` calls) |
| C7-1 (diagnostic) | R14, R15 | index missing | see §8 |

**Source-only support is large.** In G2 at 16 KB P-call, C7-3 supports 12
core relationships: 7 `graph_and_source` and 5 `source_only`. For C7-2 the
split is 4 and 6. Much of what is supported rests on delivered caller text
rather than a graph edge to the callee (§5a.5).

## 7. Budget: attribution and minimum-evidence bound

### G2 budget attribution, 4 KB → 16 KB

| Question | Condition | Unit | Relationships gained | Relevant bytes gained | Non-relevant bytes gained |
|---|---|---|---:|---:|---:|
| C7-1 | E2E | P-whole | 7 | 9,245 | 3,018 |
| C7-1 | E2E | P-call | 8 | 6,743 | 5,550 |
| C7-2 | ORACLE-ENTRY | P-whole | 4 | 3,304 | 8,758 |
| C7-2 | ORACLE-ENTRY | P-call | 4 | 3,304 | 821 |
| C7-3 | E2E | P-whole | 3 | 1,877 | 10,377 |
| C7-3 | E2E | P-call | 8 | 7,003 | 4,093 |

Relationships are only gained, never lost, with the larger budget. Under
P-whole most of the added bytes are not relevant (C7-3: 10,377 against
1,877). P-call spends the extra budget much better.

### Minimum-evidence bound (ORACLE BOUND: uses ground truth, not a selector result)

| Question | Route relationships | Bytes | Fits 4,096 | Fits 16,384 | Uncoverable |
|---|---|---:|---|---|---|
| C7-1 | witness passage / structural | — | no | no | R14, R15 (index missing) |
| C7-2 | witness passage | 5,591 | no | yes | — |
| C7-2 | structural | 5,591 | no | yes | — |
| C7-3 | witness passage | 9,544 | no | yes | — |
| C7-3 | structural | 8,741 | no | yes | — |

**For both evaluable routes, the 4,096-byte budget is structurally
insufficient.** The smallest possible set of caller passages covering every
core witness is 5,591 bytes (C7-2) and 8,741–9,544 bytes (C7-3). No traversal
or selection rule could pass these questions at 4 KB.

At 16 KB both bounds fit, yet no arm passes. In G2 the binding losses at 16 KB
are discovery (§6), not budget: C7-3 P-call at 16 KB has 7 relationships not
discovered and 0 cut by budget.

## 8. Separate diagnostic finding: nested-function evidence gap (C7-1)

C7-1's R14 and R15 have the caller
`rag_orchestrator/src/core/simple_service.py#run_simple_rag._list_outgoing`, a
function nested inside `run_simple_rag`.

- **Source:** both witnesses are valid at their recorded lines at `9f039c4`.
- **Index:** no stored text exists under that canonical ID in `8cbedbb9`.

This points at nested-function extraction, canonical identity, or
stored-chunk lookup, **not** at retrieval selection, and it is not counted as
a selector miss. It has not been investigated further in this run.

## 9. Findings (no implementation proposed here)

1. **Route identification without service context is ambiguous on real
   routes.** `GET /v1/models` exists in two services. RI correctly refused to
   guess, which costs C7-2 its end-to-end result.
2. **4 KB cannot hold these traces at all.** This is a property of the
   evidence, independent of traversal quality (§7).
3. **At 16 KB, discovery is the bottleneck for G2.** The missing evidence
   sits across HTTP service hops (C7-3, and C7-1 diagnostically) or in
   functions that CALL edges do not reach from the handler (C7-2's provider
   fetchers).
4. **Passage unit matters at 16 KB.** P-call reaches 12/19 on C7-3 where
   P-whole reaches 7/19, and P-whole spends most of its added budget on
   non-relevant text.
5. **Much of the support is source-only,** so graph edges explain only part of
   what is delivered.
6. **Nested-function indexing gap** (§8). It is separate from selection.
7. **G3** (C5, designed knowing the primary case's gap) does not improve on G2
   on any evaluable question.

## 10. Limitations

- Development evidence, self-repository only, with **2 scored routes**.
- The primary `POST /v1/rag` case has not been run under this harness.
  It needs a separate authorization.
- The C3 rescan flags in §1 need an owner ruling.
- A0 (the current `/v1/rag` path) was not run for these questions (P4), so
  there is no same-question comparison with today's retrieval.
- The ground truth reflects one independent author's reading of the
  implementation; the tiers (core or supporting) are that author's.
