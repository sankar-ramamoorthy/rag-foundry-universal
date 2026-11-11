---
title: "RAG-FOUNDRY-UNIVERSAL — Engineering review and decisions, November 10–11, 2026"
date: 2026-11-11
type: note
status: complete
source: "Owner-supplied retrospective in Downloads; reviewed for repository integration on 2026-11-11"
authority: "Historical narrative and reported evidence summary; linked ADRs, specifications and deployment guides remain authoritative"
summary: "Narrative record of the architecture audit, documentation governance, CI-01 and CI-06 engineering, independent reviews, and the decision to defer deployment"
tags: [code-intelligence, architecture, review, engineering, decisions, ci01, ci06]
related:
  - "[Technical evidence and Linux handoff](/DOCS/notes/2026-11-11-ci01-ci06-technical-evidence-and-linux-handoff.md)"
  - "[Final independent CI-06 verification](/DOCS/audit/2026-11-11-ci06-pr339-final-verification.md)"
  - "[Supplied final-review assessment](/DOCS/notes/2026-11-11-ci06-final-review-assessment.md)"
  - "[Agent execution boundaries](/DOCS/deployment/agent-execution-and-verification.md)"
  - "[Production release procedure](/DOCS/deployment/production-docker-compose.md)"
  - "[November 10 architecture audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[Independent audit review and response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md)"
  - "[CI-01 investigation](/DOCS/audit/2026-11-10-ci01-generation-snapshot-investigation.md)"
  - "[CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)"
  - "[CI-06 independent review](/DOCS/audit/2026-11-10-ci06-pr339-independent-review.md)"
  - "[CI-06 verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[Documentation conventions](/DOCS/proposals/2026-11-10-documentation-conventions.md)"
---

# RAG-FOUNDRY-UNIVERSAL — Engineering review and decisions

**Period:** November 10–11, 2026
**Purpose:** Preserve the *intent, reasoning, sequence, achievements, limits, and decisions* from two days of engineering work. This is a retrospective, not an implementation spec or a claim of production readiness.
**Status at the end:** CI-01 and CI-06 merged to `main`, documentation conventions accepted; neither CI change deployed; no cleanup or re-ingestion performed. GitHub and CI statuses in this record reflect the agent reports in the project conversation, not a fresh GitHub verification.

Model names, effort settings and autonomous-run timing in this supplied narrative
are conversation-reported attributions, not independently verified model
attestations or a controlled benchmark. Local Git contains merge `e38c783`
with parent `60f7f7e`; current remote CI was not queried during this import.
The independent implementation review covered `770e3c9`; the subsequent heads
record review documentation and ADR acceptance. See the linked final review
for the exact independently executed checks and their limits.

## Executive summary

The project is shifting from **building capabilities** to **making cross-service correctness guarantees explicit, testable, and trustworthy**. The November 10 architecture audit established that the foundation—shared language-neutral intermediate representation, canonical repository graph, ORIENT/TRACE/IMPACT, provenance, generation-aware lifecycle, and bounded evidence sufficiency—should generally be preserved. The most consequential gaps were not missing features; they were assumptions at interfaces among storage, graph export, caching, embedding, and retrieval.

Two findings were selected for immediate engineering action:

- **CI-01:** A graph cache could label data with a generation ID obtained from an earlier, separate lookup; graph nodes and edges could be read from different database snapshots. We defined and implemented a **generation-identified, one-snapshot graph export**, with real PostgreSQL concurrency verification.
- **CI-06:** Some stored source passages contained text that never reached the embedding model. We measured approximately **10–12% uncovered non-whitespace artifact text** on two development corpora, built a strict **stored-passage = model-input** contract, corrected provider truncation and incremental-reuse defects revealed by independent review, and measured both discovery and downstream evidence delivery.

A separate, short governance intervention clarified the repository knowledge base's document taxonomy, authority, placement, and navigation. It was implemented in the existing OKF standard rather than turned into another planning framework.

The explicit end-of-period decision is **to pause further engineering and defer Linux deployment**. When work resumes, inspect and preserve evidence, back up PostgreSQL, deploy the coordinated service set, clean the existing development indexes carefully, and selectively re-ingest. There are no external users whose historical embeddings must be preserved, but correctness rules for *future* incremental generations still matter.

## 1. Why we undertook this work

### The architectural inflection point

The platform has moved past many obvious implementation gaps. The risks now tend to be **compositional**: individual components appear reasonable, yet their interfaces fail to establish the guarantee a user or consuming service relies upon.

A small code change can affect the interpretation of repository generation IDs, which text a vector represents, whether a graph is ready, how evidence survives context limits, and whether an answer is entitled to claim absence. Progress therefore requires **contracts, adversarial counterexamples, realistic failure tests, and bounded quality measurements**, not simply more endpoints or green unit tests.

This does **not** imply that all improvements must be large or that the architecture is complete. It means effort and risk must be assessed from the invariant and its blast radius rather than the diff size.

### Audit scope and priorities

The independent November 10 architecture audit identified nine findings, with different dispositions:

| Finding | Core concern | Disposition at end of period |
|---|---|---|
| CI-01 | Generation label and graph snapshot can diverge | **Implemented and merged**, deployment pending |
| CI-02 | Blocking work in async structural handlers | Still open; narrower implementation/verification concern |
| CI-03 | Incomplete identity for extraction, passages, embeddings and reuse | **Partially mitigated by CI-06**; remainder #313 open |
| CI-04 | IMPACT can underreport incomplete/depth-limited analysis | Still open |
| CI-05 | Extraction failures can masquerade as absence/complete coverage | Still open |
| CI-06 | Stored passages not fully represented in embeddings | **Implemented and merged**, deployment pending |
| CI-07 | Full graph loading/concurrency can exceed bounded-work intent | Still open; measure before redesign |
| CI-08 | Structural sufficiency ≠ behavioral answer sufficiency | Research/product-quality direction, not a single fix |
| CI-09 | Orchestration policy complexity and incomplete payload accounting | Defer broad refactor; clarify as evidence warrants |

The selected priority was to make existing correctness contracts observable, not to replace the graph store, redesign retrieval, or implement every audit suggestion simultaneously.

## 2. Documentation-governance intervention

### Problem identified

During the CI-01 investigation, it became clear that repository documents could have ambiguous placement, vocabulary, and authority: an investigation under `DOCS/audit/` might be mistaken for an accepted architecture decision; indexes were not consistently discoverable; `type` and `status` values varied widely. This was **not evidence that SDD had been abandoned**. The constitution, Spec Kit, ADRs and OKF already carried meaningful requirements, but their documentation relationships needed clarification.

### Decision and result

- Claude Sonnet 5.5 conducted the read-only knowledge-base conventions review.
- Issue **#332** and PR **#333** produced a review note and a minimal convention proposal, then amended `DOCS/standards/okf-documentation.md`.
- Accepted conventions define eleven document types, a six-value status vocabulary **for new documents**, their evidentiary/decision authority, existing directory placement, and **predictable discoverability** without compulsory exhaustive index entries.
- `spec.md` retains Spec Kit's native headers; `investigation` and `audit` remain distinct; no new approval states, bulk migration, validator, or duplicate authority framework was introduced.
- PR #333 was squash-merged as **`562de0b`**; #332 closed.
- Independent maintenance defects were separated into **#334** (broken links, log gaps, stale release reference, missing navigation), rather than conflated with governance.

**Intent:** An agent should learn normal work conventions from persistent project instructions and standards, *without their being repeated in every prompt*. Our task prompts should identify the desired outcome and only exceptional constraints.

## 3. CI-01 — graph snapshots have an honest identity

### Original failure mode

The orchestrator checked generation **A** and later fetched a full graph independently. If a rebuild intervened, the export could contain generation **B** while the cache stored it as **A**. Within the export, ownership/status, nodes, and relationships were read across separate sessions or statements; under concurrent rebuild or deletion, the results were not necessarily one database snapshot.

Synthetic probes demonstrated cache-control-flow defects, while carefully **not** claiming a live PostgreSQL reproduction of every interleaving.

### Architectural decision

An export reported as `ready` must be attributable to **one completed generation G and one database snapshot S**. Ownership, completed status, node values, and relationship values must all be read consistently from S. The producer must return G (`ingestion_id`), and consumers cannot cache the graph under a different identity.

The selected approach was a **single export-scoped PostgreSQL read-only `REPEATABLE READ` transaction**, materializing response data before releasing its connection. Expected-generation mismatch, missing identity, unavailable data, and valid symbol absence must remain distinct. This is deliberately **graph snapshot consistency**, not a promise that a multi-service RAG request never sees generation drift; existing whole-request fences remain.

Current ownership semantics do not establish a `ready` generation with zero graph nodes. Zero-node results are treated as unavailable rather than silently asserting an empty, complete repository. A graph with nodes and zero edges is valid.

### Engineering and verification

- GPT-6.1 Sol CLI completed the investigation and contract clarification, then implemented #335.
- PR **#336** merged as **`75c3b4c`** after lint, unit, PostgreSQL integration, and bounded-memory checks passed.
- Local verification included **28 CI-01 PostgreSQL/HTTP tests**, **57 database regression tests**, and deterministic reader/writer barriers across rebuild, deletion, completion, rollback, and cache-load races.
- The tests also checked cleanup, connection reuse, read-only isolation, expected-generation conflicts, and producer/consumer envelope validation.
- CI-01 was **not deployed**. Real large-repository costs and deployed-stack behavior remain unmeasured.

**Outcome:** A previously implied consistency claim was replaced by an explicit contract and a tested implementation, without changing canonical IDs, requiring multi-generation graph storage, or broadening the architecture.

## 4. CI-06 — source coverage is not automatically embedding coverage

### Why the initial audit understated the problem

The original illustration compared a 1,000-character window against an 800-character client cut. Investigation found a larger cause: sentence/paragraph chunking could generate **unbounded units**, such as an entire function, while the embedder shortened them before inference. Ollama could also truncate at the model's 512-token context limit.

Across development snapshots of RAG-FOUNDRY-UNIVERSAL and LightRAG, approximately **10–12% of non-whitespace indexed text never reached an embedding input**. The initial numerical claim about how many inputs exceeded the 512-token limit was later **withdrawn** after Codex showed the offline tokenizer was not faithful to the serving model.

### Initial autonomous implementation

Claude **Opus 5.5, Medium effort**, was given CI-06 as an end-to-end engineering goal in a fresh session, to test goal-driven software engineering rather than step-by-step prompting. In its first autonomous turn, it investigated, compared chunk sizes, implemented the initial contract, performed development-corpus discovery experiments, added tests, and opened **PR #339** under issue **#337**.

The original implementation chose approximately 800-character line-aligned windows for repository artifacts. That recovered text coverage and substantially improved correct-file discovery for previously omitted source lines. It deliberately did not equate those retrieval proxies with answer quality.

### Why an independent review mattered

A separate **Codex GPT-6 Astra** adversarial review found two high-severity defects despite green CI:

1. **R1 — exact-input violation:** the token-budget heuristic could accept inputs that Ollama rejected. The adapter retried with server truncation but kept the full passage, contradicting the central invariant.
2. **R2 — generation-mixing path:** if cleanup of obsolete vectors failed, later incremental reuse could retag stale vectors by document ID without fencing to the expected prior generation. This could occur even when all generations used the same embedding contract.

Codex also identified an inaccurate offline token counter (R3), missing downstream delivery evidence (R4), and narrower CI-03/rollout risks (R5). The initial PR was **held**, and ADR-056 remained proposed. The review was not a failure of the overall direction; it exposed what the original tests had not established.

### Corrective engineering

Opus continued autonomously and revised the implementation:

- **Exact-input v3:** indexed passages are never stored with truncated embeddings. A strict provider rejection triggers **lossless splitting** into smaller passages and re-embedding; if a piece cannot be split, ingestion fails. Query truncation is separately handled and logged.
- **Generation-fenced reuse:** SQL retagging requires membership in the **expected previous generation**, for both relevant update paths. If an artifact has no eligible previous vectors, ingestion embeds it instead of falsely treating it as reused.
- **Model-grounded fit evidence:** the inaccurate offline token counts were withdrawn; the serving model was asked to accept the new passages with `truncate: false`. **All 80,819 unique passages** across the two development corpora were accepted; the pathological test cases exercised the split path.
- **Identity and performance:** embedding dimension was added to reuse identity; batch failure handling was improved by bisection; long-line splitting was made linear. Remaining extractor and immutable model-digest identity work remains in CI-03 / **#313**.
- **Controlled delivery evaluation:** criteria were committed in **`01cba02` before results**, then a bounded development-corpus evaluation measured evidence delivery and multilingual behavior under fixed budgets.

The long autonomous run exposed a **harness efficiency problem**: legacy oversized inputs were retried one at a time, driving throughput to about six seconds/input. The agent diagnosed and fixed this, recovering about 0.05 seconds/input in the reported run. That delay is a genuine efficiency lesson even though the engineering result was strong.

### What the evaluation actually established

| Measure | Legacy | New CI-06 | Interpretation |
|---|---:|---:|---|
| Missing indexed source text reaching embeddings | ~10–12% | 0% on measured development corpora | Core defect corrected for evaluated inputs |
| Previously omitted lines: correct file in top five (Foundry) | 42% | 81% | Strong discovery-proxy gain |
| Previously omitted lines: correct file in top five (LightRAG) | 52% | 84% | Strong discovery-proxy gain |
| Expected expressions in final context | 48 / 112 | 61 / 112 | Better delivery in bounded simulation; **not** answer quality |
| Multilingual repository docs top-five hits | 102 / 150 | 94 / 150 | Decline exactly at pre-registered allowable margin |
| Primary targets discovered | 14 / 14 | 14 / 14 | No loss in this development evaluation |

**Accuracy correction:** No evaluated *case's total delivered-expression count* declined. This does **not** mean every individual expression survived; one case lost an individual expression while gaining others. The verification narrative and PR wording were corrected.

A follow-up Codex review verified that the original R1 and R2 blockers were resolved. It identified a **nonblocking evaluation-harness cache-provenance flaw**, separately filed as **#340**; it strictly checked 4,505 potentially affected upload passages against the serving model and reported no rejection. The harness should still be corrected. The independent reviewer recommended acceptance of the revised ADR and merge.

### Decision and merge

- **ADR-056 accepted** on November 11, 2026; it specifies the embedding-input contract and development-stage clean-rebuild approach.
- **PR #339 merged** to `main` as regular merge commit **`e38c783`**; final premerge checks passed at **`60f7f7e`** (lint, unit, integration, bounded memory).
- The regular merge intentionally retained preregistration commit **`01cba02`** in `main` history, supporting the chronology of the evaluation protocol.
- Issue **#337** closed. **No deployment, index deletion, or re-ingestion** occurred.

## 5. What we learned about autonomous agents

The experiment was not just “can an LLM write code?” It tested whether a model could take a repository-grounded **engineering goal** and carry it through investigation, trade-offs, implementation, tests, and PR preparation with little supervision.

**Observed strengths:** Opus Medium handled a substantial end-to-end task without repeated prompting, reported quality regressions rather than concealing them, and corrected issues revealed by adversarial review. Codex independently constructed live/provider and SQL-lifecycle counterexamples that green tests had missed. The second reviewer pass then verified the corrective work and narrowed residual findings.

**Observed weakness:** Autonomous execution also needs **cost/time-budget judgment**. The multi-hour evaluation delay came partly from an avoidable harness retry pattern. Long-running experiments need bounded designs, caching discipline, and transparent progress checks.

**Important limitation:** This was not a controlled model benchmark or proof that either model is generally superior. The concrete lesson is the value of **goal-driven implementation plus independent falsification**. A green PR is not automatically evidence that an architectural invariant holds.

## 6. Decisions we intentionally did *not* make

- We did **not** deploy CI-01 or CI-06 to Linux during this period.
- We did **not** delete current repository/vector/graph data or re-ingest.
- We did **not** require historical embedding compatibility: this is a development system without external users; **clean rebuilding the indexes is an acceptable rollout strategy**.
- We did **not** remove generation identity or generation-fenced reuse: those protect **future incremental ingestions even after a clean rebuild**.
- We did **not** substitute a graph database, stage multiple persistent graph generations, or undertake a broad orchestrator rewrite.
- We did **not** choose 400-character passages solely on needle-retrieval results; 800 remains the accepted starting point until delivery-side comparisons justify a change.
- We did **not** claim end-to-end answer-quality or held-out-corpus gains from development-only discovery and simulated delivery evaluations.
- We did **not** initiate a documentation validator merely because conventions had been adopted.

## 7. Stopping point and next phase

The user elected to **pause project work until there is time to operate on the Linux box**. The next session is operational, not another open-ended design cycle: capture the current state; preserve pinned E1/WP-R4 and held-out evidence; back up PostgreSQL; decide the exact cleanup boundary; deploy compatible ingestion/vector-store services with CI-01 already merged; selectively rebuild indexes; and verify the live graph/export, embedding-input and RAG evidence paths.

The broader roadmap and cloud/macOS/model portability goals remain directional planning, not completed deliverables or deployment promises.

### Related open work

- **#313 / CI-03:** extractor identity, immutable model identity, and fuller representation/reuse contracts.
- **#338:** uploaded Markdown / Docling-section ingestion defect found during CI-06; separate scope.
- **#340:** evaluation cache may treat legacy server-truncated vectors as strictly validated; separate harness correction.
- **#334:** documentation-link, log, release-reference and discoverability maintenance.
- **CI-02, CI-04, CI-05, CI-07, CI-08, CI-09:** remain separately prioritized audit findings; no claim of closure.

## 8. Source trail

Principal repository sources: `DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md`; `DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md`; CI-01 investigation and graph-snapshot contract; CI-01 verification report; CI-06 investigation and verification report; `DOCS/audit/2026-11-10-ci06-pr339-independent-review.md`; ADR-050/051/056; CI-06 delivery evaluation protocol; relevant KB review and OKF amendment. See the companion technical handoff for issue/PR numbers, acceptance boundaries, and a precise Linux restart plan.
