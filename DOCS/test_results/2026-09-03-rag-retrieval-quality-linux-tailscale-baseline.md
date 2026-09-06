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
