---
title: "Evidence-survival question set: 12 candidates for the frozen 8-question experiment"
date: 2026-09-07
type: evaluation
status: proposed
tags: [evaluation, retrieval, graph, context-selection, evidence-survival, rag-quality]
source_commit: 9044d68a5c1821854aaac9089d186f177ab5f937
related:
  - "[[../audit/2026-09-07-current-state-retrieval-audit]]"
  - "[[../audit/08-RAG-Quality-Evaluation-Methodology]]"
  - "[[../audit/09-Retrieval-Technique-Decision-Gates]]"
  - "[[../test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline]]"
  - "[[../test_results/2026-09-03-rag-quality-source-eval]]"
  - "[[../adr/ADR-031-canonical-identity-model]]"
  - "[[../adr/ADR-032-symbol-resolution-call-graph]]"
  - "[[../adr/ADR-045-hybrid-vector-graph-rag]]"
  - "[[../adr/ADR-048-Cross-Artifact-Linking]]"
---

# Evidence-survival question set: 12 candidates for the frozen 8-question experiment

> [!abstract] Purpose
> This is a **candidate pool, not results**. It records 12 source-grounded questions against the exact source snapshot below, from which a future experiment will freeze 8 to measure where required evidence survives or disappears across the retrieval/context pipeline described in [[../audit/2026-09-07-current-state-retrieval-audit]]. No `/v1/rag`, vector, or generation endpoint was called while writing this document; no ingestion was run. The "Known control case" candidate below was verified only by reading current source, not by re-running the historical evaluation that first surfaced it.

## Location note

This repo's existing subject buckets don't quite fit a *pre-registered candidate set*: `DOCS/test_results/` holds executed benchmark/verification evidence (a completed run), and `DOCS/audit/` holds findings/plans, not ground-truth question banks. This document is neither — it is the input artifact an evaluation run will consume. `DOCS/evaluations/` is introduced as a new sibling bucket for that role, following the existing per-subject-subdirectory pattern in [[../index]] rather than overloading `test_results` with a document that has no results yet. `DOCS/index.md` is not modified by this document (see final summary).

## Snapshot discipline

**Primary snapshot — `rag-foundry-universal` (this repo, holds all Python candidates and the pipeline-stage code the experiment will exercise):**

- Commit: `9044d68a5c1821854aaac9089d186f177ab5f937`
- Branch: `main`
- Working tree: **not clean** — two untracked files present, neither of which is read from or referenced by any candidate below: `DOCS/audit/2026-09-07-current-state-retrieval-audit.md` (already cited above; content read as part of this task) and `DOCS/audit/2026-09-07-repository-intelligence-architecture-audit.md` (not read, not relevant to any candidate here). Both are additive documentation files with no effect on ingestion or retrieval code.
- No modified tracked files.

**Secondary snapshot — `TradeForge` frontend (`C:\Users\bosto\dockerstuff\TradeForge-Project\TradeForge\frontend`), used only for the two TS/JS candidates, read under one-time user-granted authorization for this task:**

- Commit: `a2e30156ad0805036cc626e985f9f339bb7d5631`
- Branch: `feature/tf-f088-ollama-remote`
- Working tree: clean (`git status --porcelain` empty)

The future experiment must ingest **both** repositories at exactly these commits, or explicitly record new snapshots and re-verify every candidate's "Required artifact(s)" / "Canonical ID(s)" fields against the new source — per ADR-031, identity is a deterministic function of structure, so a changed line number is harmless but a renamed/moved symbol or file is not.

## Why `TradeForge` frontend instead of this repo's TS/JS test fixture

This repo's own checkout contains no first-party `.ts`/`.tsx`/`.js` source — only `ingestion_service/tests/fixtures/ts_repo/` (a deliberately tiny extractor-unit-test fixture, 8 files, used for golden-file assertions in `test_ts_repo_graph_golden.py`) and vendored third-party JS under `.venv/`. Per explicit user instruction during this task, the fixture repo is **not** used as a TS/JS evidence source here — it is a golden-test fixture, not a realistic developer question source, and reusing it would violate candidate-selection rule 4 (should resemble a realistic developer question). The user granted one-time authority to read `TradeForge/frontend` instead, which is a real multi-thousand-line TypeScript/React codebase already known (from [[../audit/2026-09-07-current-state-retrieval-audit]]'s TS control paragraph) to be a realistic ingestion/query target and the source of the historical `upsertAdvisoryContext` control. Using it means the frozen experiment is implicitly a **two-repository** evaluation (Python self-ingestion + TypeScript cross-repo ingestion), which must be reflected in however the experiment is run (two `repo_id`s, two ingestions).

---

## Candidate N — Short descriptive name (index)

1. Tree-sitter parser/query cache (`base.py`) — **known control case**
2. Evidence-survival drop-reason precedence
3. `hybrid_retrieve`'s cross-module ranking/mapping/fetch chain
4. Docs→code linking via `SymbolTable.lookup`
5. `upsertAdvisoryContext` default-record/merge logic (TS)
6. Advisory-context patch fields per acquisition handler (TS, cross-file)
7. IS8 doc-link match strategy buried in an 834-line assembler (Python long-artifact)
8. Annotation-creation error unwrapping buried in a 2,116-line API module (TS long-artifact)
9. ADR-048 vs. the actual selector: does query time really traverse `DOCUMENTS`?
10. Retrieval expansion/cap constants in `rag_orchestrator` settings
11. Same-priority tie-break order in multi-seed graph expansion
12. Ollama embedding input truncation (800 chars, then 400 words)

---

### Candidate 1 — Tree-sitter parser/query cache (known control case)

**Question**
In `ingestion_service/src/core/extractors/treesitter/base.py`, why are `_language_for`, `_parser_for`, and `_compiled_query` all wrapped in `@lru_cache`, and what would happen on every file parsed if that caching were removed?

**Category**
narrow implementation

**Difficulty**
easy control

**Required artifact(s)**
`ingestion_service/src/core/extractors/treesitter/base.py` — functions `_language_for` (line 31), `_parser_for` (line 42), `_compiled_query` (line 58).

**Canonical ID(s)**
`ingestion_service/src/core/extractors/treesitter/base.py#_language_for`
`ingestion_service/src/core/extractors/treesitter/base.py#_parser_for`
`ingestion_service/src/core/extractors/treesitter/base.py#_compiled_query`
(module docstring states tree-sitter `Language`/`Parser` objects are process-wide singletons — reconfirmed directly from current source, not assumed from history.)

**Required passage**
Lines 1–59: the module docstring's caching rationale plus the three `@lru_cache`-decorated function bodies.

**Expected answer**
Each is cached (by suffix, or by `(language, query_source)` for `_compiled_query`) because tree-sitter `Language`/`Parser`/`Query` objects are expensive, process-wide-singleton-style objects meant to be built once per grammar and reused across every file of that language — without the cache, every file of a given language would rebuild its own `Language`, `Parser`, and compiled `Query` from scratch, which is both wasteful and contrary to the tree-sitter API's intended usage.

**Expected graph relationship/path**
none required — one module, three co-located helper functions, no cross-file resolution needed.

**Known competing evidence**
`DOCS/audit/03-Multi-Language-Graph-Plan.md` §3 (WP-L2 plan referenced in the module docstring); the golden-fixture tests in `ingestion_service/tests/codebase/test_ts_repo_graph_golden.py` exercise the extractor pipeline that calls into this module but don't discuss caching. `research.md` (cited in the docstring, not independently located/verified during this task).

**Primary failure stage this tests**
expanded-document selection

**Why this candidate is useful**
This is the repo's own documented historical control: an earlier evaluation found graph expansion *could* discover these exact helper artifacts, but they were then dropped by expanded-document selection before reaching the model (per this task's brief). Re-verifying against current source before reuse matters because WP-L2 has continued to evolve since that finding — the function names, line numbers, and even the caching strategy could have changed; they have not (confirmed 2026-09-07), so this remains a valid regression control for the exact same selection-stage failure.

---

### Candidate 2 — Evidence-survival drop-reason precedence

**Question**
In `compute_partial_evidence_survival` (`rag_orchestrator/src/retrieval/evidence_trace.py`), if a target canonical ID is found by graph expansion but not by vector search, and it does **not** survive the `MAX_EXPANDED_DOCS` cap, what `drop_reason` string is recorded, and would that reason still be recorded if the document was also never fetched?

**Category**
narrow implementation

**Difficulty**
easy control

**Required artifact(s)**
`rag_orchestrator/src/retrieval/evidence_trace.py`, function `compute_partial_evidence_survival` (lines 55–107) and the four `DROP_*` constants (lines 33–36).

**Canonical ID(s)**
`rag_orchestrator/src/retrieval/evidence_trace.py#compute_partial_evidence_survival`

**Required passage**
Lines 86–92 (the `if/elif/elif` chain assigning `drop_reason`).

**Expected answer**
`"truncated_by_max_expanded_docs"` (`DROP_TRUNCATED_BY_CAP`). The condition is checked before the fetch-empty branch and the branches are `elif`, so once `found_by_graph and not found_by_vector and not survives_cap` is true, the cap-truncation reason is recorded and the fetch-empty branch is never evaluated for that entry — yes, the same reason would still be recorded regardless of fetch outcome, because a document that never survives the cap is never fetched at all.

**Expected graph relationship/path**
none required — single function, no traversal.

**Known competing evidence**
`rag_orchestrator/src/core/service.py#hybrid_retrieve`, which calls this function and is the only caller of `trace_canonical_ids`; the historical manual version of this diagnosis in `DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md` §13, referenced directly in this module's own docstring as the reason the module exists.

**Primary failure stage this tests**
expanded-document selection

**Why this candidate is useful**
It is a pure-logic, single-function question with an unambiguous answer straight from an `if/elif` chain — a strong control for whether the pipeline can correctly retrieve and reason about its *own* diagnostic code, which is unusually precise, densely-commented Python that a language model could either summarize accurately or hallucinate about specific branch ordering.

---

### Candidate 3 — `hybrid_retrieve`'s cross-module ranking/mapping/fetch chain

**Question**
After `hybrid_retrieve` (`rag_orchestrator/src/core/service.py`) computes its seed chunks, what four things happen, in order, to turn seed canonical IDs into the final set of expanded documents whose chunks get fetched — and which of those steps is where a ranked candidate can be dropped purely because of its position in the list?

**Category**
cross-file graph

**Difficulty**
diagnostic

**Required artifact(s)**
`rag_orchestrator/src/core/service.py`, function `hybrid_retrieve` (lines 231–371), specifically its calls to `_rank_expanded_canonical_ids` (line 318), `canonical_to_document_map_http` (line 322), the `MAX_EXPANDED_DOCS` slice (line 339), and `_fetch_expanded_doc_chunks` (line 341).

**Canonical ID(s)**
`rag_orchestrator/src/core/service.py#hybrid_retrieve`
`rag_orchestrator/src/core/service.py#_fetch_expanded_doc_chunks`
(`_rank_expanded_canonical_ids` and `canonical_to_document_map_http` are imported from sibling retrieval modules; this task did not re-derive their exact defining file/canonical ID and that should be confirmed at ingestion time rather than assumed.)

**Required passage**
Lines 318–341 of `service.py`.

**Expected answer**
In order: (1) rank all graph-expanded canonical IDs via `_rank_expanded_canonical_ids`; (2) map every seed-plus-expanded canonical ID to its owning `document_id` via `canonical_to_document_map_http`; (3) walk the ranked list in order, keeping the first `document_id` occurrence per canonical ID and skipping documents already seeded, to build `expanded_doc_ids`; (4) slice that list to `settings.MAX_EXPANDED_DOCS` before calling `_fetch_expanded_doc_chunks`. Step (4) — the slice — is where a correctly-ranked candidate can still be dropped purely by list position, independent of its actual relevance.

**Expected graph relationship/path**
seed chunk → canonical_id → (graph expansion, unspecified edge types resolved elsewhere) → ranked canonical_id list → document_id → fetched chunk.

**Known competing evidence**
`rag_orchestrator/src/retrieval/traversal_selector.py#execute_traversals_from_seeds` (produces the ranking `_rank_expanded_canonical_ids` consumes/reflects — see Candidate 11); `DOCS/adr/ADR-045-hybrid-vector-graph-rag.md` (the ADR this function's docstring cites); the "Most important confirmed problem" section of [[../audit/2026-09-07-current-state-retrieval-audit]], which names this exact slice as the decisive evidence-loss point.

**Primary failure stage this tests**
expanded-document selection

**Why this candidate is useful**
This is the single most load-bearing function in the whole pipeline per the current audit's own verdict; a question requiring the model to trace four sequential steps across one function (with two of the four being calls into other modules) tests whether cross-file call-graph traversal actually assembles a coherent multi-hop answer, not just single-symbol lookup.

---

### Candidate 4 — Docs→code linking via `SymbolTable.lookup`

**Question**
When `GraphAssembler._link_docs_to_code` links a Markdown section heading to a code symbol of the same name, and that name is ambiguous (defined in more than one place in the repository), which specific canonical ID does it link to, and where is that tie-breaking rule actually implemented?

**Category**
cross-file graph

**Difficulty**
diagnostic

**Required artifact(s)**
`ingestion_service/src/core/codebase/graph_assembler.py`, method `_link_docs_to_code` (lines 754–824, specifically the `symbol_table.lookup(...)` call at lines 780–781); `ingestion_service/src/core/codebase/symbol_table.py`, method `SymbolTable.lookup` (lines 60–64).

**Canonical ID(s)**
`ingestion_service/src/core/codebase/graph_assembler.py#GraphAssembler._link_docs_to_code`
`ingestion_service/src/core/codebase/symbol_table.py#SymbolTable.lookup`

**Required passage**
`graph_assembler.py` lines 776–785 (name normalization + `symbol_table.lookup` call) together with `symbol_table.py` lines 60–64 (`return min(bucket) if bucket else None`).

**Expected answer**
`_link_docs_to_code` calls `symbol_table.lookup(section_name)` (falling back to the lowercased name), which resolves ambiguity by returning `min(bucket)` over all canonical IDs registered under that name — i.e. the lexicographically smallest canonical ID wins, deterministically, per the tie-breaking rule actually implemented in `SymbolTable.lookup`, not in `GraphAssembler` itself.

**Expected graph relationship/path**
`MARKDOWN_SECTION` node → (name match via `SymbolTable`, not a graph edge) → target code node → `DOCUMENTS` relationship created from section to target (lines 802–811).

**Known competing evidence**
`ingestion_service/src/core/codebase/symbol_table.py`'s own docstring, which explicitly names this ADR-048; `DOCS/adr/ADR-048-Cross-Artifact-Linking.md` (describes the DOCUMENTS-edge feature at a design level, but per the current audit does **not** describe this exact tie-break mechanism); `DOCUMENTABLE_TYPES` (imported constant, not re-verified here) gating which target types are eligible.

**Primary failure stage this tests**
graph discovery

**Why this candidate is useful**
This is a genuine two-file, two-module traversal (assembler logic + a separate symbol-table data structure) with a subtle, easy-to-get-wrong answer (the tie-break lives in `SymbolTable`, not in the caller) — a good test of whether the system can correctly attribute which of two related files actually implements a specific decision rule, rather than describing the feature in general terms.

---

### Candidate 5 — `upsertAdvisoryContext` default-record/merge logic

**Question**
In the TradeForge frontend's `src/operationalContext.ts`, when `upsertAdvisoryContext("aapl", { price_regime: "trend" })` is called for a symbol that has no existing advisory record, what does the resulting stored record look like, and what happens to the `symbol` and `updated_at` fields specifically?

**Category**
narrow implementation

**Difficulty**
diagnostic

**Required artifact(s)**
`src/operationalContext.ts` (TradeForge frontend repo), function `upsertAdvisoryContext` (lines 100–131), and its default-record literal (lines 107–117).

**Canonical ID(s)**
`src/operationalContext.ts#upsertAdvisoryContext` — expected under ADR-031's format if this repo is ingested with `src/` at its canonical root; not independently confirmed against a real ingestion of this repo, since it has not been ingested during this task.

**Required passage**
Lines 100–131 in full — the symbol is upper-cased before lookup/storage, a fresh default record is built if none exists, the patch is spread over it, and `symbol`/`updated_at` are unconditionally overwritten after the patch spread (so a caller cannot accidentally set a stale `updated_at` or a different-cased `symbol` via the patch).

**Expected answer**
Symbol is normalized to `"AAPL"` (upper-cased). Since no record exists, the default record is used as the base (`price_regime: null`, etc.), the patch (`price_regime: "trend"`) is merged over it, and then — regardless of what the caller's patch contained — `symbol` is force-set to `"AAPL"` and `updated_at` is force-set to a fresh `new Date().toISOString()`, overriding anything the patch spread might otherwise have set for those two fields.

**Expected graph relationship/path**
none required — single function, no cross-file call needed to answer (though `getOperationalContext`/`saveContext` are called internally within the same file).

**Known competing evidence**
`getAdvisoryContext` (same file, lines 133–136) reads the record back; `src/workspaces/ContextWorkbenchWorkspace.tsx` calls this function twice with different patch shapes (Candidate 6) — a retrieval that only surfaces the caller, not this definition, would be insufficient to answer correctly.

**Primary failure stage this tests**
seed retrieval

**Why this candidate is useful**
This is the repo's own historical control target (named directly in [[../audit/2026-09-07-current-state-retrieval-audit]]'s TS paragraph as a case that was previously omitted from a top-k-5 answer) — re-verified here against the actual current function body (which had *not* previously been re-read line-by-line for this purpose), so it is both historically comparable and freshly grounded rather than assumed unchanged.

---

### Candidate 6 — Advisory-context patch fields per acquisition handler

**Question**
In `src/workspaces/ContextWorkbenchWorkspace.tsx`, `handleRequestPriceContext` and `handleRequestFundamentals` each call `upsertAdvisoryContext` after a successful fetch. What fields does each handler patch, and which fields does neither of them ever touch directly?

**Category**
cross-file graph

**Difficulty**
diagnostic

**Required artifact(s)**
`src/workspaces/ContextWorkbenchWorkspace.tsx`, function `ContextWorkbenchWorkspace` (exported at line 94), specifically `handleRequestPriceContext` (lines 123–146) and `handleRequestFundamentals` (lines 148–174); `src/operationalContext.ts`'s `AdvisoryContextRecord` type (lines 17–27) as the reference for "which fields exist."

**Canonical ID(s)**
`src/workspaces/ContextWorkbenchWorkspace.tsx#ContextWorkbenchWorkspace` — the two handlers are nested closures inside this exported component function; whether the current TS/JS extractor captures nested function declarations as separate artifacts or folds them into the enclosing function's text is **not confirmed** (the golden-fixture tests in this repo only cover top-level/class-method declarations). This should be verified against a real ingestion before the experiment relies on a specific canonical ID for either handler individually.

**Required passage**
Lines 134–138 (`handleRequestPriceContext`'s patch: `price_regime`, `price_provider_id`, `price_data_as_of`) and lines 160–165 (`handleRequestFundamentals`'s patch: `fundamentals_coverage_status`, `fundamentals_provider_id`, `fundamentals_company_name`, `fundamentals_sector`).

**Expected answer**
`handleRequestPriceContext` patches `price_regime`, `price_provider_id`, `price_data_as_of`. `handleRequestFundamentals` patches `fundamentals_coverage_status`, `fundamentals_provider_id`, `fundamentals_company_name`, `fundamentals_sector`. Neither handler ever patches `symbol` or `updated_at` directly (both are force-overwritten inside `upsertAdvisoryContext` itself, per Candidate 5) — and of the seven non-identity fields on `AdvisoryContextRecord`, both handlers together cover all of them; no field is left untouched by both.

**Expected graph relationship/path**
`ContextWorkbenchWorkspace.tsx` --IMPORTS--> `operationalContext.ts` (per the `import { ... upsertAdvisoryContext } from "../operationalContext"` at line 14); a `CALL` edge from the component (or its nested handler, per the caveat above) to `upsertAdvisoryContext` twice, with different literal patch objects at each call site.

**Known competing evidence**
`src/workspaces/MarketContextPanel.tsx` also calls `addWatchedSymbols` (a sibling export of `upsertAdvisoryContext`) but not `upsertAdvisoryContext` itself — a plausible distractor if retrieval conflates the two exports from the same module.

**Primary failure stage this tests**
context construction

**Why this candidate is useful**
The correct answer requires holding two call sites in the same file in view simultaneously and distinguishing them from a same-module sibling function used nearby (`addWatchedSymbols`) — a realistic "what does this UI actually persist, and when" question a developer would actually ask, not a synthetic stress probe.

---

### Candidate 7 — IS8 doc-link match strategy buried in an 834-line assembler

**Question**
In `ingestion_service/src/core/codebase/graph_assembler.py`, what exact matching strategy does `_link_docs_to_code` use to connect a Markdown section to a code symbol, and what confidence value does it record on the resulting relationship?

**Category**
long-artifact passage

**Difficulty**
diagnostic

**Required artifact(s)**
`ingestion_service/src/core/codebase/graph_assembler.py` (834 lines total; the single `GraphAssembler` class starts at line 67 and `_link_docs_to_code` is its next-to-last method, at lines 754–824 — roughly 90% of the way through the file/class).

**Canonical ID(s)**
`ingestion_service/src/core/codebase/graph_assembler.py#GraphAssembler._link_docs_to_code`

**Required passage**
Lines 802–811 (the `relationship_metadata` dict passed to `graph.add_relationship`).

**Expected answer**
`match_strategy: "exact_name"`, `confidence: 1.0` — an exact (case-sensitive first, then lowercased-fallback) name match between the section heading and a symbol-table entry, not any fuzzy or embedding-based match.

**Expected graph relationship/path**
none required to answer the question itself (it's a single method), but the method's own effect is to create the `DOCUMENTS` relationship type this candidate is asking about.

**Known competing evidence**
Per ADR-039/ADR-040, per-artifact embedding means the whole `GraphAssembler` class body (constructor through this method, potentially several hundred lines of unrelated relationship-building logic for CALL/IMPORTS/INHERITS/EXTERNAL_SYMBOL) is plausibly embedded as one large CLASS-level unit — meaning the answer-bearing 10 lines sit far past a large amount of unrelated class text a fixed token/word budget could truncate before reaching them (see [[../audit/2026-09-07-current-state-retrieval-audit]]'s finding on `build_labeled_context`'s first-chunk-over-budget truncation). This should be confirmed against actual embedding-unit boundaries at ingestion time — this task did not verify whether `GraphAssembler` is embedded as one CLASS artifact or per-method.

**Primary failure stage this tests**
chunk selection

**Why this candidate is useful**
It targets the exact mechanism the `_link_docs_to_code` docstring itself explicitly calls "Strategy: exact name match via symbol table. Deterministic, no LLM, rebuild-safe (ADR-048)" — a specific factual claim placed deep inside a large file/class, purpose-built to test whether length-driven truncation (not graph or seed failure) is what actually loses this kind of evidence.

---

### Candidate 8 — Annotation-creation error unwrapping buried in a 2,116-line API module

**Question**
In the TradeForge frontend's `src/api/runtime.ts`, what HTTP method and path does `postCreateAnnotation` call, and — if the server responds with a non-OK status whose JSON body has a nested `detail.message` field — what error message does the function actually throw?

**Category**
long-artifact passage

**Difficulty**
diagnostic

**Required artifact(s)**
`src/api/runtime.ts` (2,116 lines total), function `postCreateAnnotation` (lines 1997–2029 — roughly 94% of the way through the file).

**Canonical ID(s)**
`src/api/runtime.ts#postCreateAnnotation` — expected format per ADR-031 conventions; not confirmed against a real ingestion of this repository.

**Required passage**
Lines 2009–2025 (the `fetch` call and the nested `detail`/`message` unwrapping ternary chain).

**Expected answer**
`POST /lifecycle/decisions/create-annotation`. If the response is not OK, the function parses the body as JSON (swallowing a parse failure to `null`), and if that body is an object containing a `detail` key whose value is itself an object with a `message` field, it throws exactly that nested `detail.message` string; otherwise it throws a generic `` `Annotation creation failed: ${response.status}` `` message (used whenever the body isn't JSON, has no `detail`, or `detail` isn't an object with a usable `message`).

**Expected graph relationship/path**
none required — single function, no cross-file resolution needed to answer.

**Known competing evidence**
Fifty-plus sibling `export async function fetch*/post*` functions in the same file share the same general `fetch` + `!response.ok` shape (e.g. `validateCredential` at line 648, `revokeCredential` at line 633) but with a materially simpler, non-nested error-unwrapping pattern (plain `response.text()`) — a strong distractor set for a model that pattern-matches "the error handling in `runtime.ts`" without locating this specific function's more elaborate nested-detail branch.

**Primary failure stage this tests**
chunk selection

**Why this candidate is useful**
`runtime.ts` is by far the largest single artifact identified in either source snapshot, and this specific function sits in its last 6% — the most extreme "answer near the end of a long artifact" case available, with a genuinely distinguishing detail (the nested-detail unwrapping) that a shallow or truncated read would get wrong in a specific, checkable way (falling back to the generic status-code message instead of the nested one).

---

### Candidate 9 — ADR-048 vs. the actual selector: does query time really traverse `DOCUMENTS`?

**Question**
Does the production query-time retrieval path (the traversal strategies actually selected and executed for a user's natural-language query) traverse `DOCUMENTS` relationships automatically, the way `DOCS/adr/ADR-048-Cross-Artifact-Linking.md`'s query-time section describes?

**Category**
implementation-vs-docs

**Difficulty**
diagnostic

**Required artifact(s)**
`rag_orchestrator/src/retrieval/traversal_selector.py`, functions `select_traversal_strategies` and `execute_traversals` (around line 121, per [[../audit/2026-09-07-current-state-retrieval-audit]]); `ingestion_service/src/core/codebase/graph_assembler.py#GraphAssembler._link_docs_to_code` (creates the edges, ingestion-time only — see Candidate 7); `DOCS/adr/ADR-048-Cross-Artifact-Linking.md` (the doc making the query-time claim).

**Canonical ID(s)**
`rag_orchestrator/src/retrieval/traversal_selector.py#select_traversal_strategies`
`rag_orchestrator/src/retrieval/traversal_selector.py#execute_traversals`
(exact canonical IDs for these two functions were not re-derived from source line-by-line during this task; the audit doc's own file:line citations were used as the pointer and should be re-confirmed before the experiment runs.)

**Required passage**
The regex-driven strategy-selection table in `traversal_selector.py` (which relation types each query-wording pattern maps to) compared against ADR-048's query-time traversal description.

**Expected answer**
No. `GraphAssembler` creates `DOCUMENTS` edges at ingestion time (Candidate 7), but per the current-state audit, the production traversal selector never includes `DOCUMENTS` among the relation types any of its regex-matched strategies traverse — so a query never automatically walks from a code symbol to the Markdown sections that document it (or vice versa) via graph expansion, contrary to what ADR-048's query-time section describes. This is a **documentation/implementation mismatch**, not a data-model defect — the edges exist and are queryable directly, just not auto-traversed by the current selector.

**Expected graph relationship/path**
`DOCUMENTS` edges exist in the graph (created by `_link_docs_to_code`) but are **not** part of any traversal `execute_traversals_from_seeds` currently runs — the correct answer is that the expected path is absent from production behavior, which is the point of the question.

**Known competing evidence**
ADR-048 itself is the primary competing (and, on this specific point, outdated-relative-to-code) source; `ingestion_service/tests/codebase/test_ts_repo_graph_golden.py` and other DEFINES/CALL/IMPORTS/INHERITS-focused tests don't exercise `DOCUMENTS` traversal either, so no test currently contradicts the audit's finding. `DOCS/architecture/Repo-query-ascii-flow-diagram.md` is also named in the audit as stale on a different, adjacent point (expanded-fetch `k` and a nonexistent ranking stage) and could be pulled in as further (also-stale) competing evidence by a broad retrieval.

**Primary failure stage this tests**
graph discovery

**Why this candidate is useful**
This is the cleanest "does the code match the design doc" question in the corpus, already independently confirmed by a same-day audit rather than assumed — a good test of whether the system, when asked a question with a plausible authoritative-sounding wrong answer sitting right in an ADR, correctly prefers the current code's actual traversal table over the ADR's stated intent.

---

### Candidate 10 — Retrieval expansion/cap constants in `rag_orchestrator` settings

**Question**
In `rag_orchestrator/src/core/config.py`, what are the exact current values of `MAX_EXPANDED_DOCS`, `EXPANDED_DOC_CHUNKS`, `MAX_TOTAL_CHUNKS`, and `MAX_CONCURRENT_DOC_FETCHES`?

**Category**
exact config

**Difficulty**
easy control

**Required artifact(s)**
`rag_orchestrator/src/core/config.py`, class `Settings` (lines 8–43).

**Canonical ID(s)**
`rag_orchestrator/src/core/config.py#Settings`

**Required passage**
Lines 20–31 (the "Retrieval expansion limits (issue #30 Part 3)" block).

**Expected answer**
`MAX_EXPANDED_DOCS = 20`, `EXPANDED_DOC_CHUNKS = 3`, `MAX_TOTAL_CHUNKS = 50`, `MAX_CONCURRENT_DOC_FETCHES = 8`.

**Expected graph relationship/path**
none required — one class, four adjacent class attributes.

**Known competing evidence**
`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md` §2 states an overlapping but not-necessarily-current-shaped description ("`EXPANDED_DOC_CHUNKS=3` chunks... capped at `MAX_EXPANDED_DOCS=20` and `MAX_TOTAL_CHUNKS=50`") that happens to agree with current source as of this task, but is a plausible stale-value trap in general since it's a separate, older document restating config values rather than the config file itself; `.env`/`.env.test` could theoretically override any `Settings` field via `pydantic_settings`, though no override for these four fields was observed during this task.

**Primary failure stage this tests**
seed retrieval

**Why this candidate is useful**
A pure fact-lookup easy control with a single, unambiguous, machine-checkable answer (four integers) and a plausible near-duplicate distractor already present in the corpus (the audit-methodology doc's own restatement) — useful as a sanity floor for the whole experiment: if this fails, no other result in the batch should be trusted.

---

### Candidate 11 — Same-priority tie-break order in multi-seed graph expansion

**Question**
In `execute_traversals_from_seeds` (`rag_orchestrator/src/retrieval/traversal_selector.py`), when two graph-expanded artifacts end up with the same `best_strategy_index` and the same `seed_hits` count, what determines which one is ranked first — and what does that specific tie-break criterion imply for an artifact whose canonical ID happens to sort late alphabetically?

**Category**
graph-expansion stress

**Difficulty**
stress

**Required artifact(s)**
`rag_orchestrator/src/retrieval/traversal_selector.py`, function `execute_traversals_from_seeds` (lines 209–259), specifically the `sorted(..., key=...)` call at lines 247–254.

**Canonical ID(s)**
`rag_orchestrator/src/retrieval/traversal_selector.py#execute_traversals_from_seeds`

**Required passage**
Lines 247–254 (`key=lambda n: (best_strategy_index[...], -seed_hits[...], n.canonical_id)`) plus the surrounding comment block (lines 222–234) explaining the historical failure this ordering was chosen to fix.

**Expected answer**
The sort key is `(best_strategy_index, -seed_hits, canonical_id)` — strategy priority first, then descending seed-hit count, and **canonical ID ascending (plain lexicographic order) as the final tie-break**. An artifact whose canonical ID sorts alphabetically late (e.g. deep in a `z`-prefixed path, or simply a longer/later symbol name at the same priority and seed-hit level) is pushed later in the ranked list purely by string comparison, making it more likely to fall outside `MAX_EXPANDED_DOCS` (Candidate 3/10) than an otherwise-equally-relevant artifact whose canonical ID happens to sort earlier — a form of arbitrary, relevance-blind competition among same-priority candidates.

**Expected graph relationship/path**
Multiple seeds, each expanded via `execute_traversals`, all funneled into one shared `node_by_cid`/`seed_hits`/`best_strategy_index` accumulation before the final `sorted(...)` call — the "many competing related artifacts" shape is structural to this function, not query-specific.

**Known competing evidence**
The function's own inline comment names the exact historical failure mode this ordering was built to partially fix (an external-library symbol crowding out a seed module's own helper via alphabetical ordering alone) and cites `DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md` §13 directly; [[../audit/2026-09-07-current-state-retrieval-audit]]'s "Most important confirmed problem" section restates this as the decisive, still-only-partially-fixed evidence-loss mechanism.

**Primary failure stage this tests**
expanded-document selection

**Why this candidate is useful**
This is the mechanism the current audit calls the single most important confirmed problem in the whole pipeline — a stress case by construction (many same-priority candidates, one arbitrary tiebreaker) rather than an artificially padded one, and it is exactly the kind of question where "the code discovers the right thing but discards it before selection" would be directly demonstrable if the experiment can construct or find a query with several same-priority expanded candidates.

---

### Candidate 12 — Ollama embedding input truncation (800 chars, then 400 words)

**Question**
Before a code or document chunk is embedded via Ollama, what two-stage truncation does `_truncate` in `shared/embedders/ollama.py` apply, and in what order?

**Category**
other

**Difficulty**
easy control

**Required artifact(s)**
`shared/embedders/ollama.py`, function `_truncate` (lines 13–29) and constants `MAX_EMBEDDING_WORDS` / `MAX_EMBEDDING_CHARS` (lines 9–10).

**Canonical ID(s)**
`shared/embedders/ollama.py#_truncate`

**Required passage**
Lines 9–29 in full.

**Expected answer**
First, if the text exceeds `MAX_EMBEDDING_CHARS` (800), it is hard-truncated to the first 800 characters. Then, independently, if the (possibly already character-truncated) text splits into more than `MAX_EMBEDDING_WORDS` (400) whitespace-separated words, it is further cut down to the first 400 words. Character truncation always runs first and can itself remove content a word-count truncation alone would have kept.

**Expected graph relationship/path**
none required — one function, no traversal; relevant only in that it runs on `chunk.content` for every embedded chunk (`OllamaEmbedder.embed`, line ~53, same file), i.e. upstream of seed retrieval for every artifact in the corpus, not specific to any one query.

**Known competing evidence**
[[../audit/2026-09-07-current-state-retrieval-audit]] names this exact 800-character limit as a candidate cause of "potentially omitting searchable content," but explicitly as an unverified hypothesis, not a demonstrated failure — this candidate is the natural follow-up to actually check whether a long, answer-bearing artifact's embedding input gets cut before the relevant text.

**Primary failure stage this tests**
seed retrieval

**Why this candidate is useful**
It targets a pipeline-wide precondition (every embedded chunk passes through this exact truncation) rather than one artifact's behavior, and it is the one candidate in this set that can explain a **seed-retrieval** failure (the correct artifact never ranks high enough because its embedding was built from truncated text) as distinct from every other candidate here, which test graph-, cap-, or context-stage loss.

---

## Recommended Frozen Set

Recommended 8 for the actual experiment: **1, 2, 3, 5, 7, 9, 10, 11**

- **Candidate 1** (easy control) — the repo's own named historical control case; must be in any run that claims continuity with prior findings.
- **Candidate 10** (easy control) — a four-integer fact-lookup sanity floor; if this fails, nothing else in the batch is trustworthy.
- **Candidate 2** (diagnostic) — precise single-function branch logic, cheap to grade exactly right/wrong, good baseline for Python narrow-symbol recall.
- **Candidate 3** (diagnostic) — exercises the single most load-bearing multi-hop call chain in the current pipeline (`hybrid_retrieve`); directly informative for every downstream pipeline-stage question.
- **Candidate 5** (diagnostic) — the TS analogue of Candidate 2, and the one candidate directly comparable to the historical `upsertAdvisoryContext` finding, giving before/after comparability across evaluations.
- **Candidate 7** (diagnostic) — the clearest test of length/truncation-driven chunk-selection loss on the Python side, distinct in failure-stage attribution from Candidates 3/11.
- **Candidate 9** (stress) — a same-day, independently-confirmed implementation-vs-docs mismatch; high-value because a wrong answer here is specifically attributable to preferring stale documentation over current code.
- **Candidate 11** (stress) — the audit's own "most important confirmed problem"; the single highest-value stress case in the set for demonstrating expanded-document-selection loss under competing same-priority artifacts.

## Deferred Candidates

- **Candidate 4** — valuable and well-grounded, but overlaps substantially with Candidate 9 (both probe `DOCUMENTS`-edge / ADR-048 behavior) and with Candidate 2 (single-function deterministic-logic style); better reserved for a follow-up round focused specifically on symbol-table ambiguity resolution rather than this round's pipeline-stage focus.
- **Candidate 6** — realistic and useful, but its exact canonical-ID shape (nested closures inside a component function) is the least confidently grounded in this set; worth running only after a real ingestion of the TradeForge fixture confirms how the extractor actually names these artifacts, rather than spending one of the 8 frozen slots on an assumption.
- **Candidate 8** — the most extreme long-artifact case by raw distance (94% into a 2,116-line file), which makes it excellent evidence *once* Candidate 7 has already established whether length/truncation loss is real; redundant to run both in the first frozen pass.
- **Candidate 12** — high-value but tests a different pipeline entry point (embedding-time truncation) than the seed→graph→cap→fetch→context chain the other 7 frozen candidates jointly cover; better run as a targeted follow-up once/if seed-retrieval misses are actually observed among the frozen 8, rather than spent speculatively now.

## Experiment Matrix

Planned, **not executed**:

- 8 frozen questions (candidates 1, 2, 3, 5, 7, 9, 10, 11)
- 3 conditions per question:
  1. current production retrieval/context path (as deployed today, no changes)
  2. diagnostic control with the relevant cap/selection restriction relaxed, or the target evidence deliberately preserved through to context construction
  3. clean-context replay using exactly the required passage identified above, with no competing distractors
- 3 generation repetitions per condition (for generation-variability sampling only)
- 8 × 3 = **24 deterministic retrieval/context executions** — conditions 1 and 2 are deterministic given fixed seeds/settings, and condition 3's context is hand-assembled, so each condition needs one execution per question, not three; the three repetitions apply to the generation call, not to retrieval/context construction
- 8 × 3 × 3 = **72 generation calls total**

## Decision principle

> A code or architecture change is justified only when the same failure stage is demonstrated on at least two independent questions and preserving the missing evidence materially improves the answer.

No reranker, hybrid lexical search, new embedding model, graph database, larger context window, LLM router, or general agent is recommended by this document. Any such change should wait for the evidence this experiment produces.
