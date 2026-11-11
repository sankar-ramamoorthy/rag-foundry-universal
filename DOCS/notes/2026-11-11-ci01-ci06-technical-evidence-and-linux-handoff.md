---
title: "RAG-FOUNDRY-UNIVERSAL — CI-01 / CI-06 technical evidence and Linux restart handoff"
date: 2026-11-11
type: note
status: complete
source: "Owner-supplied retrospective in Downloads; reviewed for repository integration on 2026-11-11"
authority: "Historical narrative and reported evidence summary; linked ADRs, specifications and deployment guides remain authoritative"
summary: "Verified development/CI claims, consistency and embedding contracts, independent-review outcomes, open risks and safe Linux deployment handoff"
tags: [ci01, ci06, verification, deployment, postgres, vector-store, handoff]
related:
  - "[Final independent CI-06 verification](/DOCS/audit/2026-11-11-ci06-pr339-final-verification.md)"
  - "[Supplied final-review assessment](/DOCS/notes/2026-11-11-ci06-final-review-assessment.md)"
  - "[Agent execution boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[Production release procedure](/DOCS/deployment/production-docker-compose.md)"
  - "[Two-day engineering review](/DOCS/notes/2026-11-11-two-day-engineering-review.md)"
  - "[CI-01 graph snapshot contract](/specs/005-production-correctness/contracts/repository-graph-snapshot.md)"
  - "[CI-01 verification](/DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md)"
  - "[CI-06 verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[CI-06 independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)"
  - "[ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md)"
---

# CI-01 / CI-06 technical evidence and Linux restart handoff

**Recorded:** November 11, 2026
**Audience:** Repository owner and future Claude/Codex/ChatGPT sessions
**Execution boundary:** The implementation changes are merged into the development repository. **No Linux deployment, production-data migration, delete, or re-ingestion is recorded.** This handoff is a plan for inspection and operator-controlled execution, not authorization to perform destructive actions.

## 1. Release state and provenance

| Stream | Tracking | Repository state | Decision / validation state |
|---|---|---|---|
| Knowledge-base governance | Issue #332 / PR #333 | Squash-merged `562de0b`; #332 closed | OKF conventions adopted; separate maintenance #334 |
| CI-01 | Issue #335 / PR #336 | Merged `75c3b4c` | Generation-bound graph export implemented; CI/DB tests passed |
| CI-06 | Issue #337 / PR #339 | Regular merge `e38c783`; #337 closed | ADR-056 accepted 2026-11-11; independent implementation review `770e3c9`; reported final CI head `60f7f7e`; preregistration `01cba02` retained |
| CI-03 remainder | Issue #313 | Open | Extractor/model representation identity not comprehensively solved |
| Document upload defect | Issue #338 | Open | Markdown / Docling section ingestion fault separate |
| Evaluation cache | Issue #340 | Open | Strict-fit cache provenance follow-up, not production input path |
| Documentation maintenance | Issue #334 | Open | Broken links, log/index and release reference review |

Commit, PR and CI details above were supplied from the project conversation. Repository integration confirmed the local merge object `e38c783` and its parent `60f7f7e`; it did not independently query current GitHub CI or issue state. The independent review covered implementation head `770e3c9`.

The following contract descriptions summarize the linked accepted records for
orientation; they do not introduce requirements or override them. The Linux
checklist is a planning aid subordinate to the execution-boundary and release
guides. No deployment authorization is conveyed by importing this note.

## 2. CI-01 contract and implementation checklist

### Contract summary (non-normative)

For each successful `ready` full graph export, there is **one PostgreSQL snapshot S and one completed ingestion generation G** from which actual repository graph ownership, owner completion status, all returned nodes, and all returned edges/metadata are read. The response carries `repo_id` and `ingestion_id=G`; no cache entry may assign a different generation to the payload.

### Behavior introduced

- Export uses a fresh **read-only `REPEATABLE READ` transaction** on a common session/connection, with response fully materialized before transaction close.
- An optional `expected_generation_id` is a **fence**, not access to an archived generation; mismatch against a ready graph yields **409**, while non-ready states remain explicit status-bearing responses.
- Cache/loader validates identity, status, count and shape before graph construction or insertion; old envelopes fail closed.
- Direct TRACE/IMPACT identifies the graph snapshot used and distinguishes unavailable graph from symbol absent in an analyzed ready graph.
- A completed request with **zero graph nodes** is **not** a demonstrable ready graph in the current owner model; zero-edge ready graph **is** valid.
- Earlier materialized A may remain a coherent A snapshot after B commits; **whole RAG request freshness** still requires its separate cross-service drift fences.
- No canonical ID redesign, historical snapshot storage, zero-downtime publication scheme, or graph-database replacement.

### Verification recorded

- Actual PostgreSQL 15.15 and pgvector 0.8.1 in an isolated test container.
- CI-01 suite: **28 passed**; expanded DB regressions: **57 passed**.
- Ingestion unit suite: **407 passed**, one skipped; orchestrator: **433 passed**, one skipped; root suite **202 passed** (as recorded at that stage).
- Deterministic-barrier tests for rebuild/delete interleavings, surviving node IDs with changed edge metadata, completion timing, rollback, cleanup, actual HTTP producer and consumer-cache races.
- Read-only isolation, per-transaction settings, timeout/cancellation and connection-pool cleanup checked; writer defaults preserved.
- Focused Pyright clean; repository-wide Pyright still had pre-existing errors. Do not describe this as a fully green repository-wide type check.
- Four remote CI jobs passed before merge. **Linux runtime behavior and large-export performance remain unverified.**

Reference: `DOCS/test_results/2026-11-10-ci01-graph-snapshot-verification.md`, graph contract under `specs/005-production-correctness/contracts/`, ADR-050 and ADR-051.

## 3. CI-06 contract and implementation checklist

### Original defect, not just the audit illustration

Under the former heuristics, unbounded sentence/paragraph units could exceed the embedder's 800-character client cutoff, and Ollama could subsequently truncate to the serving model's context limit. Storage retained the **full** passage. Therefore text could appear in cited/delivered passages although it did not participate in vector similarity.

Development corpus coverage observations (not live/held-out): Foundry missed **11.49% of code** and **9.97% of docs**; LightRAG **10.24% of code** and **12.15% of docs**. The offline claim of **376 model-token overflows was withdrawn**, not merely revised, after its tokenizer was falsified.

### Accepted ADR-056 contract summary (exact-input-v3; non-normative)

- **Every indexed stored passage is exactly the text the model actually encoded.** Source slicing covers artifact text; repository artifacts use about 800-character line-aligned windows, document uploads use per-unit fitting.
- Ollama embedding requests are strict: `truncate: false`. Provider overflow causes **lossless splitting and embedding of each smaller piece**, with metadata and consecutive ordinals preserved. If unsplittable, ingestion fails; silent truncation cannot count as successful indexed work.
- Query overflow is a separate allowance, logged; it must **not** weaken the indexed-passage invariant.
- Chunking and embedding contract version changes force a full repository re-embedding when contract identity changes. Embedding **dimension** was added to the current reuse gate.
- Future reuse is fenced by **expected prior generation** in both vector-store retag SQL paths. When a reusable artifact has no eligible prior vectors, it is embedded rather than being marked reused.
- Failed obsolete-vector cleanup is not permitted to undermine identity correctness. A clean initial rebuild eliminates the need to support legacy representation coexistence; it does **not** replace generation-fenced future reuse.
- Broader extractor and immutable model digest identity remain open under #313.

### Adversarial-review sequence

| Finding | Review evidence | Resolution and evidence |
|---|---|---|
| R1: stored whole, embedded truncated | Live Ollama counterexamples, including a valid ~791-character Python comment | Strict provider rejections now split exact source; real pipeline/provider tests; unsplittable input fails |
| R2: stale vectors retagged after cleanup failure | SQL/lifecycle path, then reproduced against PostgreSQL | Fence expected previous generation; three-generation failure-injection tests and both SQL branches; mutation tests fail with fence removed |
| R3: offline exact-token counter disagrees with Ollama | Long token runs and Unicode divergence | Counter removed; serving model itself strictly tested **80,819 unique** development passages, zero rejected; original legacy overflow number withdrawn |
| R4: discovery ≠ delivered evidence | Original work measured needle ranking only | Pre-registered bounded delivery evaluation; five acceptance criteria passed with qualifications |
| R5: identity/rollout/scaling | Incomplete reuse identity, costly migration, retry amplification | Dimension in gate, rollout constraints stated, batched rejection bisection, long-line splitting optimized; rest of CI-03 separate |

### Quality results: correct interpretation

| Metric | Before | After | Bound/qualification |
|---|---:|---:|---|
| Gap-line correct-file hit@5, Foundry | 42% | 81% | Single-line source needle query, not an answer |
| Gap-line correct-file hit@5, LightRAG | 52% | 84% | Development corpus only |
| Expected expressions delivered | 48/112 | 61/112 | Simulated final context under production context assembly; **generated answers not graded** |
| Multilingual repository-path top-five | 102/150 | 94/150 | Exactly the registered tolerance; real regression worth targeted follow-up |
| Multilingual upload-path top-five | 102/150 | 114/150 | Evaluation path; actual broken uploaded Markdown/section ingestion #338 remains |
| Primary targets discovered | 14/14 | 14/14 | Bounded development cases |
| Long-query targets discovered | 13/14 | 14/14 | Development cases |

**Correction to the initial claim:** No *case's total expression count* declined. One case (`R4-chain`) lost an individual expected expression while gaining others. Avoid the unqualified statement “no expressions were lost.”

The delivery evaluation used preregistered criteria at commit `01cba02`, development E1/WP-R4 cases, a fixed context budget, and the production `assemble_context` function. It **assumed graph expansion already reaches the named artifacts**; it was not a live `/v1/rag` or answer-quality benchmark. One snapshot/seed was used; no held-out tuning was performed.

### Final independent-review qualifications

- A cache in the **evaluation harness** can reuse a vector computed with legacy truncation as if it were strictly validated. Codex reproduced the issue. A targeted strict-provider check of **4,505 potentially affected upload passages** found **zero rejections** for the recorded serving version/model digest. The harness defect remains separately tracked as **#340**; it is not evidence that production ingestion silently truncates under exact-input-v3.
- The reported multilingual decrease is exactly at the allowable margin, not evidence of non-inferiority. Preserve it for later regression investigation.
- The 400-character window option performed well on needle discovery but needs more vectors and lacks delivery verification. **800 stays selected**.
- The complete source and quality tests passed on development fixtures, but not on the deployed Linux generations. No claim that 61/112 expression coverage is sufficient for all real questions.

### Verification recorded

- CI-06 ingestion unit: **472 passed**; full ingestion suite had the **same 9 failures and 3 errors on clean `main`**, not attributed to this change.
- Incremental ingestion PostgreSQL: **8 passed**, including cleanup failure and missing eligible vectors.
- Vector-store PostgreSQL suite: **48 passed**; both retag SQL branches covered.
- Orchestrator: **433 passed**; root: **202 passed**. Ruff clean; no substantive new Pyright diagnostics reported.
- Codex second review: **127 passing focused tests**, 50 additional overflow scenarios, PostgreSQL mutation verification; 13 evidence captures matched recorded hashes.
- Final PR #339 checks: lint, unit, integration, bounded-memory passed on `60f7f7e`; merged as `e38c783`.

Reference: `DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md`, `DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md`, ADR-056, independent review, `DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md`, and handoff note.

## 4. Why a clean development rebuild is appropriate—but not a replacement for correctness

The user confirmed that the system is **not serving external customers** and existing development embeddings may be recreated. Therefore CI-06 does **not** need elaborate historical vector-version compatibility or live backward-compatible coexistence of two chunking contracts.

However:

1. **Generation identity** remains required after a clean rebuild: if G2 cleanup fails and G3 reuses a file, unfenced retagging could still attach stale G1 vectors to G3.
2. **Representation identity** still matters for future changes of extractor, model digest or inference configuration. The current gate is not the final CI-03 solution.
3. **Evaluation provenance** must survive deletion. Rebuilding changes retrieval baselines and generation identifiers, even if the code repository is unchanged.
4. **Operational state** may include database objects besides repository data. “Delete everything ingested” does not necessarily mean “drop PostgreSQL volumes.” Determine the actual tables, volumes and supported deletion semantics first.

The intended approach is clean **index** reconstruction after a verified backup, not destructive database reset by default.

## 5. Restart on Linux — operator-controlled procedure

This is a checklist and decision sequence, **not commands to execute blindly**. Use the repository's current deployment scripts and release records as authoritative, and inspect live state before choosing deletion mechanisms.

### Phase A — Non-destructive inventory

- Confirm Linux checkout branch/commit and running image/service versions; compare with merged commits `75c3b4c` and `e38c783`.
- Enumerate containers, persistent Docker volumes, PostgreSQL server/version/schema revisions, and configured data paths, without changing anything.
- Capture `repo_id`, ingestion/generation IDs, status, repository counts, vector counts and graph counts; identify documents outside code repositories.
- Check current E1/WP-R4 evaluation pins, held-out corpus manifests, raw captures, result files and local Git-ignored artifacts. Avoid assuming all artifacts are in Git or all corpus metadata is in PostgreSQL.
- Identify any unfinished comparison requiring the existing indexed generation.

**Hold point:** Decide precisely what must survive, what is regenerable, and what scope “clean database” means.

### Phase B — Preserve evidence and back up

- Copy/confirm source manifests, experiment protocol, results, raw captures and relevant release records outside any target of cleanup.
- Create a PostgreSQL logical backup and retain the ability to restore it. Record backup location, tool versions, time, server/database identity, size and restoration approach.
- Verify the backup's integrity (at minimum inspectable metadata/contents; ideally test restore into an isolated database). Do not confuse a command's exit status with successful recoverability.
- Preserve deployment `.env` and secrets **privately**, never in a repository document or chat transcript.

**Hold point:** No data deletion until backup and preservation are explicitly confirmed.

### Phase C — Plan deletion and coordinated deployment

- Decide whether repository lifecycle deletion provides complete cleanup of vector rows, graph records, request lineage and caches. Do not assume a UI delete is sufficient without verifying DB counts.
- If a database reset is chosen, document exactly which database/volume/tables will be reset and what other metadata will be lost. Avoid unrelated model caches, source trees, evaluation records and deployment configuration.
- Deploy compatible **`ingestion_service` and `vector_store_service` together** for CI-06; include the already merged CI-01 orchestrator/graph-export updates in the stack deployment plan.
- Check schema migrations, environment settings, backup/rollback path and service compatibility before deployment. A producer-first graph-envelope rollout and validation sequence must not expose old payloads as trustworthy new snapshots.

**Hold point:** Approval for any actual data removal and deployment actions belongs to the operator at that time.

### Phase D — Re-ingest and verify

- Re-ingest a **small selected repository first**, rather than immediately rebuilding every past corpus.
- Verify completed generation identity, coherent graph export, expected-generation conflict behavior, TRACE/IMPACT unavailable-vs-absence semantics, and no ready zero-node misclassification.
- Verify new exact-input embedding contract, provider model/digest/configuration, no silently truncated indexed passages, correct vector counts and generation-fenced reuse across at least one incremental run.
- Exercise a representative natural-language RAG question and capture candidate retrieval, graph expansion, passage/context survival and cited answer separately. Compare only against appropriately preserved or re-baselined references.
- Measure ingestion duration, DB/VRAM/CPU/memory, and API responsiveness; the prior development tests did not establish large-corpus deployment performance.
- Record release SHA(s), migrations, retained/reset data, operator verification, smoke-test evidence and any limitations in the established release/status documentation.

### Phase E — Decide subsequent ingestion

Only after the first live validation passes, choose the repositories and documents worth re-ingesting. Do not rebuild pinned held-out/evaluation generations casually; record any new generation as a new baseline rather than overwriting the interpretation of previous results.

## 6. Open risk register and logical next work

| Item | Nature | Why separate |
|---|---|---|
| #313 / CI-03 | Extractor version, immutable model digest and effective embedding configuration in reuse identity | Broader cross-product identity contract, beyond CI-06 migration |
| #338 | Markdown / Docling-section upload breakage | Existing source-ingestion defect, not repaired by CI-06 chunker alone |
| #340 | Evaluation cache strict-vs-truncated provenance | Measurement harness flaw; independently checked impact on current captures |
| #334 | Documentation maintenance | Governance accepted; housekeeping can occur later |
| CI-02 | Blocking structural I/O | Endpoint execution behavior; not part of graph-snapshot correctness fix |
| CI-04 | IMPACT incompleteness signaling | Evidence semantics, independent of embedding-input guarantee |
| CI-05 | Extraction failure coverage | Do not conflate failed extraction with absence |
| CI-07 | Full graph memory/concurrency | Capacity evidence and scaling design, not an automatic graph-store rewrite |
| CI-08 / CI-09 | Behavioral sufficiency and orchestration policy/accounting | Separate evaluation/design work |

## 7. Read-this-first links for continuation

- [CI-01 implementation PR #336](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/336)
- [CI-06 implementation PR #339](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/339)
- [CI-06 issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)
- [CI-03 remainder #313](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/313)
- [Upload defect #338](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/338)
- [Evaluation cache #340](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/340)
- [Documentation maintenance #334](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/334)

**Next interaction when on Linux:** Start with a read-only inventory of the actual runtime and stored corpora. Then jointly decide what must be preserved and backed up. No deletion, re-ingestion, or deployment has yet been performed.
