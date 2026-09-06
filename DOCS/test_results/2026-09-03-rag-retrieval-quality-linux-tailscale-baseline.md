---
title: "RAG Retrieval Quality Diagnostic - Linux/Tailscale Baseline"
date: 2026-09-03
type: test-result
status: complete
scope:
  - linux deployment
  - remote tailscale access
  - self-ingestion
  - retrieval quality
  - mixed-artifact retrieval
  - context construction
tags:
  - rag
  - evaluation
  - retrieval
  - graph
  - context-quality
  - typescript
  - tailscale
---

# RAG Retrieval Quality Diagnostic - Linux/Tailscale Baseline

## 1. Purpose

Validate RAG-FOUNDRY-UNIVERSAL running on the Linux host, operated remotely from
Windows over Tailscale, and then investigate observed retrieval-quality failures
systematically rather than changing implementation based on isolated answers.

The test progressed through four levels:

1. Deployment / connectivity
2. Repository ingestion
3. Codex-driven quality evaluation
4. Deep diagnosis of one failed retrieval case

No implementation changes were made during this investigation.

---

## 2. Deployment Validation

### Linux Environment

The stack was started on the Linux machine.

Alembic migrations were run successfully through:

```text
20260831_language_col
```

Docker showed the following services running:

```text
gradio-ui
rag-orchestrator
llm-service
vector-store-service
ingestion-service
ingestion-db
```

Relevant exposed ports:

```text
Gradio               7860
ingestion-service     8001
vector-store-service  8002
llm-service           8003
rag-orchestrator      8004
Postgres              5434
```

Linux Tailscale address:

```text
100.105.24.12
```

Local Linux validation:

```text
curl http://localhost:7860
```

returned the Gradio application successfully.

---

## 3. Remote Windows Validation

From Windows, the Gradio application was opened through Tailscale:

```text
http://100.105.24.12:7860
```

This proved:

```text
Windows browser
    -> Tailscale
    -> Linux Gradio
    -> Docker-hosted RAG stack
```

A full repository ingestion was then started remotely through the Gradio UI.

Repository ingestion completed successfully.

Repository ID:

```text
f7641840-ba13-5f9d-9ae6-87e1f924709d
```

The Linux ingestion was noticeably faster than previous laptop runs.

---

## 4. Initial Manual RAG Tests

Several manual questions were asked against the self-ingested
RAG-FOUNDRY-UNIVERSAL repository.

### Test: Orchestrator Responsibilities

Question:

```text
What service handles RAG queries, and what downstream services does it call?
```

The answer correctly identified the RAG Orchestrator and the Vector Store / LLM
services, but leaned heavily on documentation.

This raised the first concern:

```text
Does the system understand current implementation,
or is it primarily retrieving explanatory documentation?
```

### Test: `hybrid_retrieve` Caller/Callee Behavior

Question:

```text
What functions call hybrid_retrieve, and what functions does hybrid_retrieve itself call?
```

The system correctly identified:

```text
run_rag -> hybrid_retrieve
```

but failed to enumerate the full implementation-level callees.

A follow-up explicitly required implementation-only evidence:

```text
According to the actual implementation of hybrid_retrieve
in rag_orchestrator/src/core/service.py,
list every function it directly calls.
Use only the implementation, not documentation or tests.
```

RAG responded that the implementation body was not present in the supplied
context.

This became the first reproducible evidence that the required implementation
artifact could be absent from final RAG context even when the system knew about
the symbol.

---

## 5. Codex Evaluation - Baseline 1

Codex was launched directly inside the repository and instructed to:

1. inspect the source directly;
2. generate 10 technically meaningful questions;
3. determine ground truth from current implementation;
4. ask the same questions through the remote RAG endpoint;
5. compare RAG answers against source;
6. classify retrieval vs generation failures.

Remote endpoint used:

```text
POST http://100.105.24.12:8004/v1/rag
```

### Baseline 1 Scope

This first run focused heavily on Python/backend behavior:

```text
rag_orchestrator/src/core/service.py
routes.py
simple_service.py
traversal utilities
graph utilities
source adapter behavior
```

Docs/tests were mostly observed as competing evidence rather than as the primary
subject.

### Baseline 1 Result

```text
PASS       3
WEAK PASS  2
FAIL       5
```

Correctness:

```text
correct            4
partially correct  3
incorrect          3
```

Evidence completeness:

```text
complete    6
incomplete  3
missing     1
```

### Main Failure Classes

Retrieval/context failures:

```text
Q1
Q2
Q3
Q7
```

Generation/reasoning failures despite adequate evidence:

```text
Q4
Q6
Q10
```

### Important Finding

The `hybrid_retrieve` failure was confirmed independently:

```text
query targets current implementation
        -> retrieval returns tests/specs/docs
        -> implementation body does not reach final context
        -> model cannot answer from source
```

---

## 6. Codex Evaluation - Baseline 2

A second 10-question evaluation was run against the same repository with
intentionally broader coverage.

Approximate coverage:

```text
Python backend
TypeScript/JavaScript implementation
Markdown/current docs
YAML/config
UI/API contracts
graph-dependent relationships
current implementation vs stale/spec documentation
```

The repository did not contain a TypeScript frontend application; TypeScript
coverage therefore focused on the tree-sitter extractor implementation and
fixtures.

### Baseline 2 Result

```text
PASS       0
WEAK PASS  3
FAIL       7
```

Correctness:

```text
correct            2
partially correct  3
incorrect          5
```

Evidence completeness:

```text
complete    2
incomplete  6
missing     2
```

### Results by Area

```text
Python:
0 PASS
1 WEAK PASS
1 FAIL

TypeScript/JavaScript:
0 PASS
0 WEAK PASS
2 FAIL

Docs:
0 PASS
0 WEAK PASS
1 FAIL

YAML/config:
0 PASS
0 WEAK PASS
1 FAIL

Cross-language/API contract:
0 PASS
1 WEAK PASS
2 FAIL
```

### Main Recurring Failures

1. Specs/design docs frequently outcompeted current implementation.
2. TypeScript implementation chunks were retrieved less cleanly than Python.
3. Direct YAML/config questions often failed to retrieve the actual
   configuration file.
4. UI/API contract questions often retrieved only one side of the boundary.
5. When implementation evidence was present, Qwen3:4b sometimes still missed
   visible fields.

---

## 7. Deep-Dive Failure Case

One failed TypeScript/tree-sitter question was selected for direct inspection.

Question:

```text
In ingestion_service/src/core/extractors/treesitter/base.py,
how are .tsx, .ts, .js, .jsx, .mjs, and .cjs files mapped
to tree-sitter languages, and how are
_language_for, _parser_for, and _compiled_query cached?
```

This case was selected because Baseline 2 showed that the RAG answer came
primarily from specs/design material instead of current implementation.

---

## 8. Database Inspection

Postgres was accessed remotely from Windows over Tailscale using Python/psycopg:

```text
100.105.24.12:5434
```

### `document_nodes`

The implementation file was confirmed present:

```text
ingestion_service/src/core/extractors/treesitter/typescript.py
```

Example stored nodes:

```text
typescript.py                                 text_len 22726
typescript.py#_classify                       text_len 1889
typescript.py#_is_default_export              text_len 714
typescript.py#TypeScriptExtractor             text_len 16910
typescript.py#TypeScriptExtractor.extract     text_len 1154
...
```

Conclusion:

```text
Source extraction        PASS
Node persistence         PASS
Implementation text      PASS
```

### `vector_chunks`

The same implementation nodes also had embedded vector chunks.

Examples:

```text
typescript.py                                 26 chunks
typescript.py#_classify                        4 chunks
typescript.py#TypeScriptExtractor             19 chunks
typescript.py#TypeScriptExtractor.extract      2 chunks
...
```

Conclusion:

```text
Vector chunk creation     PASS
Embedding persistence     PASS
```

This ruled out:

```text
missing extraction
missing document storage
missing text
missing vector persistence
```

---

## 9. Raw Vector Retrieval Test

The exact failed query was embedded using:

```text
mxbai-embed-large
```

Embedding size:

```text
1024
```

The resulting vector was sent directly to:

```text
POST http://100.105.24.12:8002/v1/vectors/search
```

with:

```text
k = 20
repo_id = f7641840-ba13-5f9d-9ae6-87e1f924709d
source_type = code
```

### Raw Ranking

The top results showed strong competition from Markdown/spec material.

Representative ranking:

```text
Rank 1   score 0.8914   markdown/spec
Rank 2   score 0.8407   markdown
Rank 3   score 0.8407   markdown
Rank 4   score 0.8374   markdown
Rank 5   score 0.8374   markdown
Rank 6   score 0.8346   markdown
Rank 7   score 0.8336   markdown
Rank 8   score 0.8336   markdown
Rank 9   score 0.8271   actual treesitter/base.py implementation
```

This proves:

```text
implementation is retrievable
but is outranked by semantically descriptive prose
```

At `top_k=5`, the implementation would not enter the seed set.

At `top_k=10`, it does.

---

## 10. `top_k` A/B Test

The same question was sent through `/v1/rag` with:

```text
top_k = 5
top_k = 10
top_k = 20
```

### `top_k = 5`

`base.py` was absent from final sources.

The model invented a plausible implementation involving dictionaries and parser
caches.

Classification:

```text
retrieval failure
+
hallucinated implementation
```

### `top_k = 10`

`base.py` appeared in sources.

However, the answer still relied heavily on plans/specs and inferred
implementation details rather than accurately describing current code.

Classification:

```text
implementation available
but source competition remains
```

### `top_k = 20`

`base.py` remained available.

Answer quality became worse.

The model invented unsupported details such as:

```text
lru_cache(maxsize=1000)
10 minute TTL
LRUCache(maxsize=50)
1 hour TTL
```

Classification:

```text
more context did not improve quality
context competition increased
```

Important conclusion:

```text
Increasing top_k alone is not a solution.
```

---

## 11. Retrieval Plan Inspection

For `top_k=10`, the RAG retrieval plan showed:

### Seed Canonical IDs

Included:

```text
ingestion_service/src/core/extractors/treesitter/base.py
```

alongside several specs and audit documents.

### Graph Expansion

Graph expansion successfully found the exact implementation functions:

```text
base.py#_compiled_query
base.py#_language_for
base.py#_parser_for
base.py#language_for_path
base.py#parser_for_path
base.py#run_query
```

It also found many external tree-sitter symbols and many documentation/spec
nodes.

Statistics:

```text
seed_docs                 7
expanded_docs_considered 59
expanded_docs_used       20
total_docs               20
```

This is important:

```text
vector retrieval found module       PASS
graph expansion found exact funcs   PASS
```

---

## 12. Final Context / Source Selection

The final 20 sources were then inspected.

They were:

```text
1-5     specs/tasks/plans
6       treesitter/base.py module
7-20    audit document sections
```

The exact implementation function chunks:

```text
base.py#_language_for
base.py#_parser_for
base.py#_compiled_query
```

were present in:

```text
expanded_canonical_ids
```

but were absent from:

```text
final sources
```

Therefore the system performed:

```text
vector retrieval
    -> base.py found
    PASS

graph expansion
    -> exact helper functions found
    PASS

expanded candidate selection
    -> 59 candidates -> 20 used
    FAIL

final context
    -> spec/audit material dominates
    -> exact implementation function chunks removed
    -> LLM answers from design prose
```

---

## Takeaway

The deepest diagnostic result from this investigation is:

> The observed TypeScript/tree-sitter failure is not fundamentally an ingestion
> failure, vector-persistence failure, or graph-resolution failure.

For the investigated case:

```text
Extraction                        PASS
Document-node persistence         PASS
Implementation text               PASS
Embedding/vector persistence      PASS
Raw vector retrieval              PASS
Graph expansion                   PASS
Exact function discovery          PASS
Final evidence selection          FAIL
Generation from authoritative evidence FAIL
```

The graph is successfully discovering the exact implementation artifacts.

The key failure occurs after graph expansion:

```text
59 expanded candidates
        -> 20 selected
        -> implementation helpers discarded
        -> spec/audit prose dominates context
```

This creates a source-authority problem:

> Semantically descriptive planning/specification text can outrank and displace
> the current executable implementation even when the query explicitly names the
> implementation file and functions.

The `top_k` experiment also shows that simply retrieving more material does not
solve the issue.

```text
top_k=5  -> implementation excluded
top_k=10 -> implementation present but poorly used
top_k=20 -> more distractors, worse hallucination
```

Therefore the emerging problem is best described as:

> Post-retrieval evidence selection and context competition, especially between
> authoritative implementation code and semantically similar specs/docs.

A secondary independent problem remains:

> Even when adequate implementation evidence reaches the model, Qwen3:4b
> sometimes fails to use it accurately.

The two issues must remain separate during evaluation.

---

## Next Steps

No implementation change should be made yet.

### 1. Inspect Expanded-Candidate Selection

Determine exactly how:

```text
expanded_docs_considered = 59
```

becomes:

```text
expanded_docs_used = 20
```

Questions to answer:

```text
How are candidates ranked?
Are seed chunks automatically preferred?
Are graph-expanded implementation nodes scored?
Are source types treated equally?
Is canonical proximity considered?
Does document ordering affect selection?
Are parent/module chunks competing with child/function chunks?
```

This is now the highest-value code path to inspect.

### 2. Measure Authoritative-Source Survival

Create a small diagnostic metric:

```text
Target implementation found by retrieval?
Target implementation found by graph?
Target implementation survives final context selection?
```

For example:

```text
vector found       yes
graph found        yes
final context      no
```

This is more informative than answer correctness alone.

### 3. Repeat on Several Failed Questions

Do not generalize from one case.

Repeat the same diagnostic on:

```text
one Python implementation failure
one TypeScript implementation failure
one YAML/config failure
one UI/API-contract failure
```

Determine whether the same pruning/source-competition pattern recurs.

### 4. Run Second-Repository Control

Ingest a second repository with:

```text
primarily Python
little or no TypeScript
less architectural/spec documentation
```

Launch Codex from that repository and repeat the 10-question source-grounded
evaluation.

Purpose:

```text
Does retrieval quality improve
when the corpus contains less competing design prose?
```

This will distinguish:

```text
general retrieval/context defect
vs
self-repo documentation-density effect
```

### 5. Separate Model-Quality Evaluation

After retrieval/context behavior is understood, repeat selected questions using
a stronger generation model while keeping retrieval identical.

This will measure:

```text
retrieval/context contribution
vs
Qwen3:4b generation contribution
```

Do not change both retrieval and model simultaneously.

---

## Current Working Hypotheses

The evidence currently supports testing the following hypotheses:

1. Exact implementation artifacts are sometimes outranked by semantically richer
   prose.
2. Graph expansion often successfully recovers implementation evidence.
3. Expanded-candidate selection can discard that authoritative evidence before
   generation.
4. Larger `top_k` values can increase distractor competition rather than improve
   answers.
5. Source type / authority may need to become an explicit evaluation dimension.
6. Qwen3:4b has a separate tendency to infer plausible implementation details
   when context contains competing design prose.
7. TypeScript/YAML retrieval may be more vulnerable than Python implementation
   retrieval, but more evidence is required.

No implementation recommendation is made yet.

## Summary

The most important thing learned is that this is not simply "vector RAG cannot
find the code." In the case dissected, the system found the module, and the
graph then found the exact functions. The failure happened when 59 expanded
candidates were reduced to 20: the implementation functions disappeared while
planning/audit material survived.

That is a much narrower and more valuable diagnosis than where the investigation
started.

The next investigation should inspect, without modifying, the code path
responsible for `expanded_docs_considered -> expanded_docs_used` and explain the
current selection algorithm before designing any fix.

---

# 13. Runtime Root-Cause Confirmation

This follow-up closed the diagnostic loop for the known failed query:

```text
In ingestion_service/src/core/extractors/treesitter/base.py, how are .tsx, .ts, .js, .jsx, .mjs, and .cjs files mapped to tree-sitter languages, and how are _language_for, _parser_for, and _compiled_query cached?
```

Runtime inspection confirmed that the failure is not caused by missing
extraction, missing graph discovery, missing vector chunks, `/search-by-doc`
inability to retrieve the helper documents, per-document chunk limits,
`MAX_TOTAL_CHUNKS`, or token-budget truncation.

## Confirmed finding

The confirmed failure mode is:

```text
graph expansion successfully discovers authoritative implementation evidence,
but authority-blind expanded ranking places the helper documents below the fixed
MAX_EXPANDED_DOCS cutoff, preventing that evidence from entering final context.
```

## Proven runtime chain

```text
base.py is vector seed
        ->
graph expansion finds exact helpers
        ->
_compiled_query rank 25
_language_for  rank 26
_parser_for    rank 27
        ->
MAX_EXPANDED_DOCS = 20
        ->
all three helper documents are discarded
        ->
/search-by-doc never fetches them in the production retrieval path
        ->
module seed contributes only chunk 0
        ->
module chunks 3-5 containing the implementations are absent
        ->
correct implementation text never reaches the LLM prompt
```

## Target identity and survival

| Target | document_id | Vector chunks | Seed? | Expanded rank | Pre-cap doc position | Survives top 20? | Implementation reaches final prompt? |
| --- | --- | ---: | --- | ---: | ---: | --- | --- |
| `base.py` | `f83d2b50-0924-4965-8df1-57a6d7ef061a` | 7 | yes | n/a | seed | yes | no helper implementation text from returned chunk |
| `base.py#_compiled_query` | `9f9fc219-92b6-43a9-8e6d-20076b1851eb` | 1 | no | 25 | 25 | no | no |
| `base.py#_language_for` | `9130e86f-135b-4120-8c1a-a403847844ae` | 1 | no | 26 | 26 | no | no |
| `base.py#_parser_for` | `51b4f01a-c388-4442-bb14-f506553e077a` | 1 | no | 27 | 27 | no | no |

The helper canonical IDs map to distinct document IDs. Document identity
collapse was therefore ruled out for this case.

Direct read-only `/search-by-doc` checks against the three helper document IDs
returned the expected implementation chunks. This proves that the helper
evidence is persisted, vectorized, and retrievable when the correct document is
selected.

## Final context survival

The final prompt reconstruction showed:

```text
retrieved_docs   = 20
agent_chunks     = 44
context_chunks   = 44
token estimate   = 3278
```

Only the module-level `base.py` source appeared in final context. That source
represented the seed chunk containing the file header/docstring area and did
not contain the implementations of:

```text
_language_for
_parser_for
_compiled_query
```

The module-level document stores the full file and has chunks containing those
helpers, but the production retrieval path did not include those module chunks
in the final prompt for this query.

## Ruled in and ruled out

Supported by runtime evidence:

```text
expanded ranking failure
MAX_EXPANDED_DOCS loss
context-authority problem
```

Not supported as the primary cause for this query:

```text
graph discovery failure
document identity collapse
search-by-doc chunk-selection loss
per-document chunk-limit loss
MAX_TOTAL_CHUNKS loss
token-budget loss
generation failure
```

The earlier working hypothesis is now promoted to a confirmed finding for this
specific query: authoritative implementation evidence was discovered by graph
expansion but lost at the expanded-document cap because ranking did not account
for implementation authority, source type, language, function specificity, or
the query's explicit file/function targets.

No implementation recommendation is made in this test result.

---

# 14. Follow-Up: Evidence-Survival Instrumentation and Regression Fixture (issue #89)

This section records the first concrete step taken on issue #89
(https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/89),
opened against the confirmed finding in section 13. Per the issue's ordering,
this step adds only the minimum diagnostic instrumentation and a regression
fixture reproducing the confirmed failure — no ranking/cap behavior was
changed.

## What was added

- `rag_orchestrator/src/retrieval/evidence_trace.py` — a small, dict-based
  instrumentation module. Given a set of target `canonical_id`s, it reports,
  per target: `found_by_vector`, `found_by_graph` (+ `expanded_rank`),
  `survives_cap`, `chunk_fetched`, `reaches_final_context`, and a
  `drop_reason` naming the first stage that discarded it
  (`not_found_by_vector_or_graph`, `truncated_by_max_expanded_docs`,
  `fetch_returned_no_chunks`, `dropped_before_final_context`).
- `hybrid_retrieve` gained an optional `trace_canonical_ids` parameter
  (`rag_orchestrator/src/core/service.py`). Omitted (the default, used by
  every production call), it costs nothing and changes no behavior. When
  supplied, the returned `retrieval_plan_dict` carries the partial trace
  through the `MAX_EXPANDED_DOCS` cap and fetch stages; `run_rag` finalizes
  it against the actual post-truncation final context and exposes it as
  `retrieval_plan["evidence_trace"]`.
- `rag_orchestrator/tests/test_evidence_survival.py` — a regression fixture
  modeled directly on the confirmed `treesitter/base.py` case: one seed
  module graph-DEFINES 30 children, three of them targeted as "helper
  functions" landing at ranks 25-27 (past the `MAX_EXPANDED_DOCS=20`
  default), matching the diagnostic's own rank numbers. The fixture asserts
  the instrumentation shows exactly the confirmed failure chain: found by
  graph, not surviving the cap, never fetched, never reaching final context,
  with `drop_reason == "truncated_by_max_expanded_docs"`.

## Result

All 3 new tests pass, confirming the failure is reproducible outside the
live diagnostic session, and the full `rag_orchestrator` suite (101 tests)
passes with the instrumentation in place — no regressions from adding it.

## Explicitly not done in this step

- No ranking or cap behavior was changed. The regression fixture currently
  documents the *existing* failure, not a fix.
- No reranker or other intervention (issue #89's candidates A-E) was
  implemented or chosen.
- The instrumentation is not wired into the `/v1/rag` HTTP endpoint/response
  model — it's a Python-level hook for eval scripts and tests, kept
  deliberately out of the public API contract for this step.
- Generation-only failures (Q4/Q6/Q10 in the source eval) remain untouched
  and out of scope.

## Next steps (per issue #89)

Repeat the same diagnostic shape on a few more failed questions from the two
eval docs (one Python, one YAML/config, one UI/API-contract case) to check
whether the rank/cap pattern generalizes, before comparing candidate
interventions.

---

# 15. Frozen Evaluation Set, Regression Bar, and Implemented Intervention (issue #89)

This section records the second step on issue #89: freezing the evaluation
set and numeric acceptance/regression bar before changing retrieval
behavior, implementing the smallest evidence-supported intervention, and
reporting before/after results against that bar.

## Frozen evaluation set and bar

Live LLM-graded re-evaluation of the 10 questions in
`DOCS/test_results/2026-09-03-rag-quality-source-eval.md` was not performed
for this step: doing so would require deploying this branch's code to the
Linux/Tailscale Docker stack that produced that baseline, which means a
container rebuild on that host — the kind of operation flagged as a known
cost/risk by issue #41 (containers resolve their uv environment at runtime;
multi-GB re-download on recreation) and not something to trigger
unilaterally mid-issue. That live re-run remains open follow-up work (see
Deferred below), not something this step claims to have done.

Instead, the frozen evaluation set and bar for *this* step are unit-level
and structural, built directly on the evidence-survival instrumentation
added in PR #90:

- **Primary regression fixture** (`rag_orchestrator/tests/test_evidence_survival.py`,
  first two tests): the confirmed `treesitter/base.py` case — single
  relation type, helpers ranked past the cap purely by canonical_id.
  Frozen expectation: this fixture is *not* required to start passing as
  "fixed" — when every competing candidate is the same relation type, no
  ranking change can rescue all of them, and that's an explicitly
  out-of-scope limitation for this step (raising `MAX_EXPANDED_DOCS` or a
  finer specificity signal would be the lever, not attempted here).
- **New fix-target fixture** (same file, `test_defines_children_outrank_call_derived_noise_for_the_cap`
  and `test_defines_children_reach_final_context_ahead_of_call_noise`):
  mirrors the live diagnostic's actual finding (section 11: graph expansion
  returned both the true DEFINES helpers *and* "many external tree-sitter
  symbols" reached via CALL, at the same seed-hit count). Numeric bar: all
  3 target helper canonical IDs must show `survives_cap: true`,
  `chunk_fetched: true`, `reaches_final_context: true`, `drop_reason: null`
  after the change — i.e. the confirmed competition pattern from the real
  case must no longer discard authoritative evidence.
- **No-regression bar**: the full pre-existing `rag_orchestrator` suite
  (101 tests as of PR #90, including the two ranking-determinism tests
  `test_expansion_ranks_by_seed_adjacency` and
  `test_ranking_ties_break_deterministically`) must continue to pass
  **unmodified** — i.e. the change must not alter ranking behavior for the
  single-relation-type / already-tested cases, only add a new ordering
  dimension ahead of the existing seed-hit/alphabetical tiebreak.

## Candidate interventions considered

Per issue #89's list (A. raise cap, B. rerank, C. prefer implementation over
docs, D. prefer graph-proximal children of strong seeds, E. guarantee
child-symbol survival when the parent is a strong seed):

- **D was implemented** (see below) — it directly targets the confirmed
  mechanism (flat positional truncation losing a structural signal the
  code already computes) with no new dependency, no LLM call, and no
  semantic-similarity re-scoring; the graph already univocally distinguishes
  DEFINES (structural: literally defined inside a seed) from
  CALL/IMPORT/other (referential), so "prefer graph-proximal children of
  strong seeds" reduces to "don't discard the relation-type signal that
  `execute_traversals` already computes per node."
- **A (raise `MAX_EXPANDED_DOCS`)** was explicitly not chosen as the fix:
  the source eval doc's own `top_k` A/B test already showed raising a
  similar cap increases distractor competition and degraded answers at
  `top_k=20` — the same risk applies here, and it doesn't fix the
  underlying authority-blindness, only delays when it bites.
- **B (rerank)** was not implemented in this step, per
  [[rag-quality-evaluation-gate]] / the roadmap's flag-gated,
  eval-justified requirement for a reranker — it remains a candidate for a
  later step if D proves insufficient once live-evaluated.
- **C and E** were not separately implemented: E is effectively subsumed by
  D's mechanism (a DEFINES child of a strong seed now structurally
  outranks non-DEFINES competition), and C (implementation-over-docs
  preference) operates on the *seed* vector-search stage, not the
  *expanded*-candidate stage this issue is scoped to — left for a
  follow-up issue if generalization testing (next steps) shows seed-stage
  competition is still the dominant failure mode.

Comparison stopped once D cleared the frozen bar — per the tightened goal,
this step does not exhaustively implement every candidate.

## Implemented intervention: relation-type-aware expansion ranking

`rag_orchestrator/src/retrieval/traversal_selector.py`:
`execute_traversals` now returns `(Node, strategy_index)` pairs instead of
bare nodes, `strategy_index` being the position of the traversal strategy
(e.g. `traverse_defines` before `traverse_calls` in `_DEFAULT_STRATEGIES`)
that discovered each node. `execute_traversals_from_seeds` now sorts
expanded candidates by `(best_strategy_index, -seed_hits, canonical_id)`
instead of `(-seed_hits, canonical_id)` — the relation-type signal was
already being computed per traversal call and then discarded before the
final sort; it is now retained as the primary ranking key. Nothing else in
the expansion/cap/fetch pipeline changed.

## Result against the frozen bar

- Fix-target fixture: **3/3 target helper IDs** now show `survives_cap:
  true`, `chunk_fetched: true`, `reaches_final_context: true`,
  `drop_reason: null` (previously would have shown `truncated_by_max_expanded_docs`
  under the old ranking, verified by inspection of the pre-fix sort order —
  CALL-derived `call_extern_*` IDs sort alphabetically before `helper_*`,
  so the old canonical_id tiebreak would have filled the 20-slot cap with
  external noise first).
- No-regression bar: full `rag_orchestrator` suite — **103/103 pass**
  (101 pre-existing + 2 new fix-verification tests), including both
  ranking-determinism tests unmodified and passing.
- Primary regression fixture (single relation type): still fails the cap
  as expected/frozen — confirms the fix is scoped to the mixed-relation-type
  competition it targets, not silently masking the single-type limitation.
- `ruff check` and `pyright` on changed files: clean, no new errors (same
  pre-existing import-resolution errors in this sandboxed root venv
  present on `main` too, unrelated to this change).

## Deferred (not done in this step)

- Live re-run of the 10-question source eval against a deployed build of
  this branch, to get an LLM-graded before/after PASS/FAIL/WEAK-PASS count
  — requires a Linux-side container rebuild, out of scope for this step
  per the reasoning above.
- Generalizing the diagnostic to a Python/YAML/API-contract failure case
  and a second-repository control, per the diagnostic doc's original Next
  Steps §§3-4.
- Any change to seed-stage vector search (candidate C) or a reranker
  (candidate B).

## Whether the evidence supports closing issue #89

**Not yet.** This step delivers and unit-verifies a scoped, minimal fix for
the confirmed truncation mechanism, with a clean no-regression result on
the existing suite. It does not yet carry live-stack, LLM-graded evidence
that the fix measurably improves the original 10-question baseline's
PASS/FAIL counts, which the issue's completion criteria call for
("evaluated against the existing quality baseline"). Issue #89 should stay
open until that live comparison — or an explicit, deliberate decision to
accept the unit-level evidence as sufficient — is recorded.
