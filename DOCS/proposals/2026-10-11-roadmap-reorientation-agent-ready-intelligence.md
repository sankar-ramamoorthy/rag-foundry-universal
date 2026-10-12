---
title: "Roadmap Reorientation — Evidence-Driven Repository, Document, and Coding-Agent Intelligence"
date: 2026-10-11
type: proposal
status: integrated
tags:
  - roadmap
  - architecture
  - repository-intelligence
  - document-intelligence
  - coding-agents
  - mcp
  - evaluation
  - evidence
  - research
related:
  - "[Roadmap — Sequenced Delivery Plan](/DOCS/audit/07-Roadmap.md)"
  - "[Project Status](/DOCS/status.md)"
  - "[Documentation Index](/DOCS/index.md)"
  - "[Repository Intelligence Architecture Audit](/DOCS/audit/2026-09-07-repository-intelligence-architecture-audit.md)"
  - "[Repository Intelligence Research Lessons](/DOCS/research/2026-10-04-repository-intelligence-research-lessons.md)"
  - "[Document Intelligence Research Lessons](/DOCS/research/2026-10-04-document-intelligence-research-lessons.md)"
  - "[Evaluation and Experimental Method Lessons](/DOCS/research/2026-10-04-evaluation-and-experimental-method-lessons.md)"
  - "[ADR-053: source authority / subject / provenance model](/DOCS/adr/ADR-053-source-authority-provenance-model.md)"
  - "[ADR-054: evaluation dataset isolation and generalization](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Issue #257/#254 production verification](/DOCS/test_results/2026-10-11-issue-254-257-production-verification.md)"
---

# Roadmap Reorientation — Evidence-Driven Repository, Document, and Coding-Agent Intelligence

> [!important] Integrated 2026-10-12
> Reconciled against the live repository, GitHub issue state, the OKF documentation standard, and accepted ADRs. **Option B (careful in-place reorganization) was approved** and executed in [`DOCS/audit/07-Roadmap.md`](/DOCS/audit/07-Roadmap.md)'s Phase 6 section — every existing issue number, dated decision, and shipped-history checkbox was preserved; nothing was replaced. This document now stands as the historical rationale/research record for that integration, not a live planning document — see Phase 6 for the current, maintained plan. Four decisions were made during integration: **#200 stays under Repository Intelligence (R)**, not Coding-Agent Integration (A3); **#254 stays explicitly linked to parent #202**, with the normal-mode symptom recorded as production-verified resolved; the two-week milestone (§13) was added as a provisional "Next Evaluation Gate" checkpoint, not a permanent roadmap commitment, without auto-creating issues for its individual tasks; and the roadmap's strategic introduction now names human users and coding agents as RAG-FOUNDRY-UNIVERSAL's two primary long-term consumers. This proposal's own `[[wikilink]]`s (a documentation-standard violation for a new document) and three mis-rooted research-document paths were corrected as part of integration — see the links above for the corrected paths.

> [!abstract] Original decision request (superseded by the integration above)
> This is a **proposed roadmap reorientation**, not an accepted ADR, approved implementation specification, or a replacement for current status. Ask Codex or Claude Code to **reconcile this document against the live repository, the OKF documentation standard, current issues, and accepted ADRs**, and then recommend whether to integrate it into or replace `DOCS/audit/07-Roadmap.md`. **Do not silently overwrite** the existing roadmap, create issues, or implement any capabilities while performing that reconciliation.

## 1. Purpose and strategic goal

RAG-FOUNDRY-UNIVERSAL began as a relatively conventional vector-and-document RAG stack and evolved into a graph-aware, versioned repository/document intelligence system. The next roadmap should not be organized primarily around adding popular RAG techniques. It should be organized around **verified user capabilities** and **end-to-end evidence correctness**.

Three long-term outcomes define the direction:

1. **Repository intelligence:** reliably orient to an unfamiliar repository, identify exact implementation evidence, explain architecture and execution paths, and conservatively identify possible change impacts.
2. **Document intelligence:** preserve page/layout/table structure, selectively invoke expensive OCR or visual processing, and produce claims grounded in precise, versioned document evidence.
3. **Coding-agent intelligence backend:** expose machine-consumable repository evidence and bounded investigation tools that external coding agents can use for bug localization, change-impact assessment, and eventually evidence-backed patch proposals. **MCP is a transport/integration surface, not sufficient functionality on its own.**

A shared foundation supports these: generation/snapshot identity, graph/vector persistence, provenance, bounded evidence workflows, model/provider routing, evaluation, lifecycle correctness, security, and operations.

> [!important] Core distinction
> **Retrieval relevance is not source authority. Source discovery is not evidence delivery. Evidence delivery is not answer correctness. Bug localization is not proof that a patch is correct.** Each boundary needs explicit contracts and evaluation.

## 2. Evidence hierarchy and status rules

Use four distinct states throughout planning:

- **Shipped / production-verified:** directly supported by current merged code, release evidence, and live validation.
- **Implemented / validation incomplete:** merged or locally available but not proven against the applicable acceptance gate.
- **Investigate / experiment:** an evidence-supported hypothesis requiring frozen comparisons and a GO / NO-GO / INVESTIGATE decision.
- **Deferred / vision:** valuable future direction without current justification to implement.

Do not infer production status from an issue checkbox, an old document's `status: current`, a green unit test suite, or a GitHub merge alone. Pin separate **runtime SHA, ingested source SHA, generation ID, model/prompt/settings**, and any relevant parser/index versions when making claims.

Source-of-truth precedence for reconciliation: **current running code and production verification for operational claims; current `DOCS/status.md` for the maintained summary; accepted ADRs/contracts for intended invariants; current GitHub issue/PR state; dated test results for exact evidence; historical roadmap and research notes for rationale and proposals.** If these disagree, report the conflict and the date/revision rather than silently choosing.

## 3. Current baseline — validate against current main

The following are **working assumptions based on the October 11, 2026 project discussion and uploaded documents**, not a substitute for checking the live repository:

- Structural extraction for Python, TypeScript/JavaScript, Rust, and Java; a common graph/IR; typed graph traversal and repository-aware retrieval exist.
- Incremental ingestion and snapshot lineage (#196), deterministic ORIENT inventory (#197), TRACE/IMPACT (#198), provenance/authority surfaces (#199), and bounded structural evidence sufficiency (#200) have shipped substantial implementations. Verify completeness of *separate* formal evaluation gates and remaining sub-scope.
- Production-correctness and evidence-survival work has made ingestion, retrieval, generation fencing, and diagnostics much more observable. Some lifecycle gates and follow-ups remain independent.
- Issue #240 advanced repository-overview answer quality and structured facts. The self-repository frozen gate improved, but cross-repository generalization remains incomplete.
- Issue #254's normal-mode exact implementation failure was repaired by #257 / PR #258 (bounded query-driven `DEFINES` child-method discovery) and PR #259 (bounded explicit-method context priority), with PR #260 documenting production verification. On the same ingested generation, `agent.py#Agent.run` reached final context and was directly cited by the live generated answer. **No re-ingestion was needed.** #257 is closed; #254 remains open for separate questions.
- Still unresolved: whether `repository_overview` should exclude method passages for explicit code-behavior questions; historical deployed/local seed-set discrepancy for the same logical generation; and broader held-out repository generalization. Do not present inferred generation-retag drift as a demonstrated cause.

The October 10 independent Python coding-agent repository ingestion checked 99 tracked Python files and 573 relevant top-level/immediate-method symbols against source, while retrieval/answer behavior still showed substantial problems with historical/backup evidence and code-flow or diagram questions. **Indexed completeness alone did not establish answer quality.**

### Design lessons already earned

- A graph can recover code missed by vector similarity; earlier baseline reported vector Recall@5 70% versus vector+graph 90% **on that measured set**, not a universal guarantee.
- Graph structure can be correct while retrieval fails to traverse the necessary edge (#257).
- Correct evidence can be discovered/fetched yet discarded in context assembly (#254).
- Claim-dependent authority and typed facts matter for current-versus-historical questions and repository-wide aggregation.
- A correct natural-language explanation may still be unusable by a coding agent unless identities, source spans, uncertainty, and evidence are machine-readable.
- A document parser can extract words correctly while destroying tables, reading order, or contextual grouping; a 202/OCR pipeline can still fail later with resource exhaustion.

## 4. Workstream model and dependencies

Do not serialize everything as six monolithic phases. Track **three vertical capabilities** supported by **three cross-cutting workstreams**:

| Workstream | Objective | Initial posture |
| --- | --- | --- |
| **R — Repository correctness and intelligence** | Trustworthy orientation, exact code evidence, authority, typed architecture, TRACE/IMPACT | Highest immediate priority |
| **D — Document intelligence** | Structured pages, bounded OCR/vision, coherent chunks, page provenance | Baseline and narrow prototype in parallel |
| **A — Coding-agent integration and bug investigation** | Agent-consumable evidence, read-only MCP, bug-localization gains, later patch-impact/proposals | Start contracts + experiment early; advanced capabilities gated |
| **E — Evaluation and experiment infrastructure** | Pinned trajectories, holdouts, claim/evidence gates, ablations and regressions | Continuous, not a terminal phase |
| **O — Operations, scaling, and security** | Release correctness, ingestion resilience, performance, access controls | Continuous; scale by measurement |
| **P — Product experience and explanation** | Derived architecture views, trace explorer, demos, blog/video | Incremental after evidence correctness |

**Dependency rule:** A coding-agent tool must not claim stronger correctness than its underlying R/E capabilities. A proposed patch or impact report must not turn static graph adjacency or an LLM hypothesis into a factual runtime claim.

## 5. R — Repository correctness and intelligence

### R1. Generalization and existing defect closure — next priority

**Existing threads:** #243, #254, #240, #251, #180, #91, #202; confirm current status before carrying forward.

Tasks:

1. Freeze a matched repository-overview versus normal-mode evaluation for explicit implementation questions and repository-global orientation. Determine whether `overview_policy` excludes required method-level passages incorrectly **before changing the policy**.
2. Evaluate independently pinned repositories of different styles: self-repository, a separate Python project, a polyglot project, and configuration-heavy cases where feasible. Keep at least one held-out corpus under [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md).
3. Score per task family: repository inventory, exact-symbol implementation, code-flow/TRACE, architecture, purpose/design, historical behavior, and diagram/document references.
4. Distinguish **missing indexed evidence**, seed failure, graph traversal, candidate ranking, chunk fetch, final-context rejection, authority policy, and generation/synthesis.
5. Verify Compose `!override` / effective-production configuration (#251), source-revision provenance (#180), and other explicitly outstanding gaps on their own terms.

**Exit gate:** predeclared case-by-case answer and exact-source obligations across multiple pinned repositories; negative and historical controls; baseline versus candidate; acceptable latency/regression profile. Do not infer generalization from the self-repository alone.

### R2. Claim-specific authority and typed repository facts

**Relevant existing work:** #199, #203, ORIENT/TRACE/IMPACT, ADR-053, #240.

- Separate raw declarations from normalized entities (e.g., multiple Compose service declarations versus distinct logical services).
- Capture supported facts: services, packages, manifests, routes, configuration, service-to-service calls, datastores, tests, deployment relationships, evidence spans, and explicit unknowns.
- Resolve current implementation versus historical design/test/backup/fixture **relative to claim intent**, not a filename-only rule or universal numeric authority score.
- Keep deterministic facts canonical; text summaries and Mermaid diagrams are **derived views**, not independent sources of truth.
- Treat dynamic imports, DI, reflection, plugins, and incomplete static analysis as unknown/conditional unless corroborated.

**Gate:** typed facts preserve raw source provenance; cross-repository questions avoid unsupported universal statements and false negatives; known ambiguity is reported rather than guessed.

### R3. TRACE, IMPACT, and snapshot-aware analysis

- TRACE: enrich bounded paths with route registration, source roots, endpoint/service membership, HTTP calls, configuration, ordered relations, and supporting code spans. **Not simply deeper BFS.**
- IMPACT: list **candidate affected** callers, contracts, services, and tests. Do not claim confirmed breakage from adjacency alone.
- Investigate diff-aware analysis later: align changed symbols between pinned snapshots, compare signatures/contracts, and map likely affected tests.

**Gate:** exact path provenance, termination/unknown states, bounded runtime; precision and recall against verified cross-file/cross-service cases.

## 6. A — Coding-agent integration and debugging assistance

> [!important] Strategic addition
> Make **coding agents a first-class external consumer** of the repository-intelligence layer. Do not make RAG-FOUNDRY-UNIVERSAL a competing full coding agent by default.

### A0. Agent-ready evidence contracts (begin alongside R1)

Define additive, versioned machine-readable contracts for repository/snapshot identity, canonical symbol ID, file path and line/span when available, evidence type, relationship, role/authority facets, source hashes, confidence/unknown status, completeness/limits, and causal trace IDs. Avoid returning only prose or exposing internal undocumented database schemas as tools.

- Support errors, ambiguity, partial/unknown results, and generation changes explicitly.
- Make evidence sufficient for an external agent to verify the cited source **in its checkout**.
- Avoid stale-index patching: require source revision agreement or explicit mismatch warnings before suggesting edit locations.
- Preserve read-only default and independent authorization for any future write-capable workflow.

**Gate:** one external client reliably resolves tool results to exact source spans and detects a deliberately mismatched source revision.

### A1. Read-only MCP proof of value

Expose a **small selected tool set**, reusing existing validated services rather than designing a broad new control plane:

- `orient_repository`
- `find_symbols` / `get_symbol_evidence` (implement only missing machine contracts)
- `trace_execution`
- `analyze_impact`
- perhaps `assess_evidence` / bounded follow-up when supported

Names are illustrative, **not existing MCP tool promises**. Secure repo scoping, explicit resource/time bounds, source identity, schema versions, and least-privilege access. Avoid one-to-one endpoint wrapping as the sole success metric.

**Gate:** run a real coding agent with and without the read-only MCP over **matched source snapshots and permissions**; establish measurable improvement, not merely successful tool invocation.

### A2. Bug-localization benchmark and diagnostic workflow

Prepare held-out, reproducible issue scenarios with: bug report or failing test, known root cause, expected symbol/file, relevant tests, realistic distractors, and source revision. Compare the same coding agent without versus with RAG-FOUNDRY-UNIVERSAL. Record correctness, root-cause localization, wrong-file/backup selections, time, tool calls, tokens, and quality of evidence citations.

Expected structured diagnostic outputs, **not asserted truth**: hypotheses, supporting/contradictory evidence, missing evidence, candidate locations, next justified step, and uncertainty. A model hypothesis is not a verified bug.

**Gate:** meaningful, repeatable lift versus the agent's native code search and grep; account for index build/refresh costs and additional infrastructure.

### A3. Bounded retrieval repair and sufficiency

Extend #200/#202 concepts carefully from structural endpoints to ordinary repository queries. Prefer deterministic obligation checks and **at most one or a few bounded, targeted follow-ups** when an expected symbol, route, test, or necessary claim facet is missing. Re-evaluate evidence after each permitted step; answer, report ambiguity, or abstain.

- Preserve existing implemented #200 semantics and avoid relabeling its narrow TRACE repair as a general agentic loop.
- Reserve #207 for adaptive multi-step investigation **only after bounded approaches measurably fail**.
- Keep the loop subject to time, token, query, depth, and graph limits; prohibit silent uncontrolled recursion.

### A4. Patch-impact analysis (later, evidence gated)

Given a **proposed diff**, compare stable source snapshots and changed symbols, inspect candidate callers/dependencies/tests/contracts, and return conservative structured impact plus unknowns. The calling coding agent should still edit and run tests.

**Gate:** verified diff-to-symbol mapping and tests on known edits; low false-confidence rate for impact claims.

### A5. Evidence-backed fix proposals (vision; not committed)

Only after A2/A4 demonstrate quality, experiment with proposing small patch plans and candidate diffs. Require exact target SHA, explicit hypothesis/evidence chain, relevant tests, sandboxed execution where allowed, and human review. No implicit production writes, autonomous merge, or unsupported guarantee of correctness.

**Gate:** controlled fix benchmarks with tests and regression checks; demonstrate benefit over the underlying coding agent without the system.

## 7. D — Document intelligence as a separate track

**Existing research:** [Document Intelligence Research Lessons](/DOCS/research/2026-10-04-document-intelligence-research-lessons.md); #204 is related to selective JIT OCR, but does not automatically cover this entire track.

Sequence:

1. **D0: pinned document corpus and reliability baseline.** Include born-digital PDFs, scans, tables/forms, screenshots, low-resolution pages, multi-column layouts, and formulas. Measure text fidelity, structure, retrieval, answer correctness, latency, RAM/VRAM, failure stages.
2. **D1: bounded ingestion lifecycle.** Make accepted/parsing/OCR/chunking/embedding/ready/failed observable; enforce raster DPI, page concurrency, memory and OCR limits; preserve failures rather than treating HTTP 202 as success. Follow up on observed OOM/Exit 137 behavior.
3. **D2: structured page/block representation and provenance.** Preserve headings, reading order, table cells, image/region locations, page/region IDs, parser/version, confidence and uncertainties.
4. **D3: structure-aware chunking.** Keep tables, headings, rows and captions coherent; evaluate parser **through the actual chunker and retrieval pipeline**.
5. **D4: selective OCR/visual escalation.** Cheap/native first pass, page-quality assessment, bounded OCR or vision for suspect/complex pages; never use pure lazy OCR if weak first-pass indexing makes pages undiscoverable.
6. **D5: provider comparison and optional isolation.** Compare Docling/Tesseract baseline, LiteParse-style first pass, WeVisDoc and other visual/OCR candidates against actual hardware, licensing and measured downstream value; consider a separate optional document-vision service if GPU/resource isolation justifies it.

**Non-goals now:** automatic replacement of Docling, always-on high-cost vision, default PaddleOCR on unsupported GPU assumptions, mandatory hosted parsing, learned OCR router before deterministic page-quality rules, or a new embedding model without controlled evidence.

**Gate:** correct structured evidence survives from page to answer across held-out difficult documents within defined resource budgets.

## 8. E — Shared evaluation, experimentation, and research gates

Evaluation is a **cross-cutting product capability**, not merely testing performed after implementation. See [Evaluation and Experimental Method Lessons](/DOCS/research/2026-10-04-evaluation-and-experimental-method-lessons.md) and [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md).

Required evaluation trajectory:

`source → parser/extractor → index → vector/structural seed → graph expansion → candidate selection → chunk fetch → context survival → claim use in final answer`

- Pin runtime/indexed-source/generation and retrieval/model/prompt/parser settings.
- Freeze development and held-out question sets, expected evidence, forbidden unsupported claims, and controls before experiments.
- Preserve raw traces, exact passage hashes, alternative experimental arms, negative/ambiguous cases, and timing/resource measurements.
- Separate mechanism quality (recall, candidate survival, graph path correctness) from answer quality, confidence, unsupported claim rate, and cost.
- Use deterministic checks for deterministic facts and LLM judges only for genuinely semantic criteria.
- Require **GO / NO-GO / INVESTIGATE** decisions; no PR/merge after a failed applicable quality gate.
- Capture verified incidents, including #254/#257, as general regression cases rather than special-case prompts.
- Include coding-agent A/B benchmarks as a **new evaluation family**, with matched tools and source permissions.

**Decision-model experiment (Jev / Laya / Kev / AnyJev / CLM):** preserve as a **research candidate**, not a commitment or prerequisite. Compare off-the-shelf models to deterministic sufficiency rules and a generative-LLM decision baseline using pinned evidence states and allowed actions (answer / retrieve_more / abstain / flag_conflict). Begin in **shadow mode**, with emphasis on false sufficiency, safe abstention, calibration, latency, RAM/VRAM, and correctness under repository-specific distractors. Promote only if repeatable, task-specific gains justify integration. This is not synonymous with #207.

## 9. O — Scaling, production, and security

Confirm the active status and actual acceptance evidence for #171, #176, #180, #181, #191, #205, #206, #208 and related WP-E work before reprioritizing.

- Preserve manual/operator-controlled production releases, exact runtime provenance, generation fences, health validation, release records, rollback rules, and non-destructive deployment defaults.
- Verify incremental ingestion equivalence and **publication/readiness consistency** at scale. The historical same-generation seed-set discrepancy is still unresolved; do not claim lifecycle drift without new direct proof.
- Characterize embedding throughput, graph cache memory, ingestion RSS, query latency, ANN recall, post-delete behavior, and per-stage failure rates before selecting new infrastructure.
- Introduce a durable job queue only if ownership/recovery and measured throughput require it; consider bounded graph-query infrastructure before automatically adding a different graph database.
- Make authorization, repository isolation, credentials/secrets, auditable tool execution, and security review prerequisites for shared or external MCP clients.
- Keep CPU-friendly basic functionality; treat GPU-assisted document vision as optional and bounded.

**Gate:** production scenarios validate the *same accepted revision* as CI/evaluation; failures and costs observable; no unexpected re-ingestion or data mutation during retrieval-only deployment.

## 10. P — Derived user experience and communication

- Display ORIENT facts, typed architecture/service relationships, TRACE paths, IMPACT candidate dependencies, evidence spans and uncertainty. Derive diagrams from current structured facts; never let generated diagrams silently become independent source truth.
- Prototype a focused evidence/graph explorer before committing to wholesale Gradio replacement or enterprise UX.
- Prepare public educational material: (1) ingestion-to-answer overview; (2) why graph retrieval helps, using #254/#257; (3) context survival and evidence authority; (4) a candid AI-assisted engineering retrospective, distinguishing Claude Code's execution/investigation, ChatGPT's hypotheses/review, and the operator's authorization/deployment.
- Productization (identity/SSO, multi-tenancy, private Git integration, PR comments, web UI) remains a gated future track under #208, not a reason to defer quality work.

## 11. Suggested relative order and effort ranges (planning estimates, not commitments)

| Work item | Suggested position | Approximate elapsed effort | Qualification |
| --- | --- | --- | --- |
| R1: overview-policy evaluation + cross-repo gate | **Now** | 2–4 weeks | Highest immediate uncertainty |
| A0/A1: agent-ready contracts + read-only MCP/A-B pilot | **Start alongside R1** | 1–3 weeks exploratory | Only continue on measurable usefulness |
| R2/R3: typed facts, authority, TRACE/IMPACT follow-ups | **After R1 evidence** | 3–6 weeks bounded | Scope driven by failures |
| A2/A3: bug-localization benchmark + bounded repair | **After A1/R1** | 2–5 weeks exploratory | Do not conflate with #207 |
| D0–D3: document benchmark and structural baseline | **Parallel next tranche** | 3–6 weeks | Document OOM/structure risks |
| D4/D5: selective OCR/vision prototype | **After D0–D3** | 2–5 weeks | Hardware/license/quality gates |
| E: shared evaluation improvements | **Continuous** | 2–4 weeks of concentrated initial investment | Avoid duplicating existing test infrastructure |
| O: scaling/security work | **Continuous + later scale gate** | 4–8 weeks focused scope | Product-ready breadth takes longer |
| P: demo/explainability/blog and initial UX | **Start small, expand after quality** | 2–6 weeks initial | Broad productization separate |
| A4/A5: patch-impact and candidate fix proposals | **Later, conditional** | Not responsibly estimable yet | Depends on bug-localization proof |

These ranges are **judgmental estimates from recent AI-assisted project pace**, not logged engineering-hour calculations; substantial integration and held-out validation uncertainty remains. Parallel work changes elapsed time; the rows cannot be summed into one promise. A credible technical demonstration may be reachable in months; a secure multi-user enterprise product is a separate longer-term milestone.

## 12. Priority rules and explicit deferrals

Prioritize in this order:

1. **Correctness and evidence survival on unfamiliar inputs.**
2. **Machine-readable, snapshot-verifiable contracts that support external coding agents.**
3. **Measured improvements to structural facts, TRACE/IMPACT, and bounded sufficiency.**
4. **Document-structure preservation and selective resource-bounded parsing.**
5. **Measured operational scale, secure access, useful visualization.**
6. **More autonomous investigation and fix proposals only when baseline tools prove insufficient.**

Retain but do **not** schedule as default changes: universal reranking, default embedding swap, unbounded `top_k`/context budgets, universal numerical authority scoring, a replacement graph database, generic LangGraph supervisor, arbitrary multi-hop traversal, unrestricted coding agent, always-on visual OCR, mandatory hosted parsing, or learned routing without a baseline and decision gate.

## 13. Proposed next two-week planning milestone

**Objective:** establish the next measurable release gate, not immediately add another large feature.

- [ ] Reconcile current issues, merged PRs, published status and deployment verification against this proposal; correct stale issue/roadmap claims.
- [ ] Freeze overview-policy explicit-code versus global-overview control cases and record baseline.
- [ ] Prepare at least one independent-repository regression/held-out plan under ADR-054.
- [ ] Draft the additive A0 machine-readable evidence contract (no breaking API change) and identify one safe read-only MCP tool pilot.
- [ ] Define the agent A/B experiment (same checkout, source revision, tools/permissions, issue set, metrics) **before** building the integration.
- [ ] Start D0 document benchmark case inventory with OOM/table/layout cases.
- [ ] Publish GO/NO-GO/INVESTIGATE decisions and issue mappings, without silently expanding implementation scope.

## 14. Instructions for Codex / Claude Code: reconciliation and integration handoff

> [!warning] Review-only handoff — do not implement features or overwrite the roadmap in this pass.

1. Read `DOCS/standards/okf-documentation.md`, `DOCS/audit/07-Roadmap.md`, `DOCS/status.md`, `DOCS/index.md`, accepted ADRs, issue contracts, and the dated research/test notes linked here. Check the actual GitHub issues and merged code. **This proposal's frontmatter/wiki links are provisional until checked against the repository's exact OKF rules and relative linking conventions.**
2. Produce a **reconciliation table**: existing roadmap entry → actual current state and evidence → keep/reword/resequence/retire → proposed workstream mapping. Explicitly identify stale checkboxes or old status text, and preserve history instead of rewriting what was believed at earlier dates.
3. Recommend one of: **(A) minimal update** to `07-Roadmap.md` linking a separate strategy document; **(B) careful reorganization** of the existing roadmap preserving original WPs/issue history; or **(C) replacement**, only if a clear migration/redirect/archival and issue-reference plan is provided. Give tradeoffs and a minimal diff plan **before editing**.
4. Preserve existing issue identities (#196–#208 and subsequent follow-ups). **Do not invent GitHub issue IDs.** Proposed labels R/A/D/E/O/P and suggested MCP tool names are conceptual and should not be treated as shipped APIs or preapproved issues.
5. Validate YAML syntax, permitted frontmatter fields, Obsidian `[[wiki links]]`, relative paths, tags, headings, OKF status/type vocabularies, and the documentation index/link-graph rules. Fix links to match actual target paths/names. Avoid duplicate authoritative status documents; continue using `DOCS/status.md` for the current snapshot.
6. Separate **confirmed production behavior**, **unverified acceptance gates**, **candidate experiments**, and **long-term vision**; cite current local evidence records and preserve source/revision identity. Flag disagreements for owner decision.
7. Propose an updated dependency diagram and short-term milestone gates emphasizing unfamiliar-repository correctness and agent A/B value, with document intelligence in a parallel track. Evaluate impact on issue #207, #200/#202, #203, #204, #205/#206, and #208 without automatically expanding them.
8. **Stop at plan/reconciliation for owner approval.** No mass issue creation, refactor, new agent/MCP service, database migration, deployment, re-ingestion, or roadmap replacement in this step.

### Requested review deliverables

- One concise roadmap migration recommendation with reasons and risks.
- Current-state reconciliation table (evidence and gaps).
- Proposed documentation diff/file plan with exact links and OKF compliance.
- Suggested next 2–4 GitHub issues or amendments **only if the owner approves**.
- A frozen first milestone evaluation plan and explicit acceptance criteria.

## 15. Links and evidence trail

### Roadmap, project status, standards

- [Roadmap — Sequenced Delivery Plan](/DOCS/audit/07-Roadmap.md) — existing sequenced plan and work packages.
- [Project Status](/DOCS/status.md) — maintained current-state snapshot.
- [Documentation Index](/DOCS/index.md) — documentation navigation.
- [OKF Documentation Standard](/DOCS/standards/okf-documentation.md) — normative formatting/linking standard.
- [Repository Intelligence Architecture Audit](/DOCS/audit/2026-09-07-repository-intelligence-architecture-audit.md) — repository intelligence scope/architecture findings.

### Research input — not automatically accepted designs

- [Repository Intelligence Research Lessons](/DOCS/research/2026-10-04-repository-intelligence-research-lessons.md) — claim authority, typed facts, TRACE/IMPACT, staged retrieval/agent behavior. Read in full during integration; internally consistent with live repo state, no contradictions found.
- [Document Intelligence Research Lessons](/DOCS/research/2026-10-04-document-intelligence-research-lessons.md) — page/structure preservation, selective OCR, hardware/license/resource constraints. Read in full during integration.
- [Evaluation and Experimental Method Lessons](/DOCS/research/2026-10-04-evaluation-and-experimental-method-lessons.md) — pinned trajectories, holdouts, exact evidence survival, decision gates. Read in full during integration.

### Current milestone and accepted evaluation contracts

- [Issue #257/#254 production verification](/DOCS/test_results/2026-10-11-issue-254-257-production-verification.md) — October 11 production result.
- [ADR-053: source authority / subject / provenance model](/DOCS/adr/ADR-053-source-authority-provenance-model.md) — confirmed `status: proposed` during integration.
- [ADR-054: evaluation dataset isolation and generalization](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md) — confirmed `status: accepted` during integration.
- [Issue #254](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/254), [Issue #257](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/257), [PR #258](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/258), [PR #259](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/259), [PR #260](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/260).
- [Issue #207](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/207) — deferred general agentic investigator, not equivalent to basic sufficiency repair or the MCP pilot.

---

> [!summary] Proposed strategic principle
> **Build and validate trustworthy evidence first; expose it to humans and coding agents second; permit adaptive investigation only where bounded methods fail; propose code changes only when the underlying source and impact evidence can be verified.**
