---
title: "Repository Intelligence Research Lessons"
date: 2026-10-04
type: research-note
status: draft
scope:
  - repository-rag
  - code-intelligence
  - graph-retrieval
  - evidence-selection
  - authority
  - provenance
  - repository-orientation
tags:
  - rag
  - repository-intelligence
  - graph
  - retrieval
  - evidence
  - provenance
  - authority
  - research
related:
  - "[[2026-09-07-repository-intelligence-architecture-audit]]"
  - "[[08-RAG-Quality-Evaluation-Methodology]]"
  - "[[2026-10-03-issue-240-frozen-quality-comparison]]"
  - "[[20261003-issue-240-restart-handoff]]"
---

# Repository Intelligence Research Lessons

## Purpose

This note records repository/code-side investigations carried out outside the main Codex/Claude implementation loop, primarily through independent ChatGPT analysis of:

- live RAG behavior,
- repository-query failures,
- controlled evaluation results,
- external repository-intelligence/RAG ideas,
- architectural alternatives,
- and repeated comparison between proposed techniques and measured failures in RAG-FOUNDRY-UNIVERSAL.

This is **not an accepted architecture document** and does not automatically create roadmap work.

The goal is to preserve the reasoning behind ideas that may otherwise disappear from chat history, while clearly separating:

1. **evidence-backed findings**,
2. **promising experiments/hypotheses**,
3. **explicitly deferred ideas**.

The scope of this document is the **repository intelligence path** only. Uploaded-document ingestion and document RAG are intentionally excluded and should be documented separately.

---

# 1. Core conclusion: repository intelligence is more than semantic RAG

The repository path has evolved beyond the original mental model:

```text
query
  ↓
vector search
  ↓
graph expansion
  ↓
LLM answer
```

The evidence now points toward a richer model:

```text
semantic retrieval
        +
deterministic repository inventory
        +
typed graph relations
        +
source role / provenance / snapshot identity
        +
claim-specific evidence selection
        +
typed derived facts
        +
bounded LLM synthesis
```

The most important change in perspective is:

> The LLM should increasingly explain a repository evidence model rather than reconstruct that model from arbitrary retrieved prose.

This affects ORIENT, TRACE, IMPACT, authority handling, evaluation, and the future roadmap.

---

# 2. Graph expansion has demonstrated real retrieval value

One of the earliest strategic questions was whether the graph justified its complexity.

A measured evaluation showed approximately:

- raw vector Recall@5: **70%**
- vector + graph Recall@5: **90%**

Graph traversal recovered evidence missed by vector search in multiple evaluation cases.

That matters because it changes the status of the graph from an architectural thesis to an evidence-supported retrieval mechanism.

## Lesson

Do not remove the graph in favor of pure vector RAG.

Instead, improve the graph and traversal only where measured failures justify it.

## Architectural consequence

The preferred pattern remains:

```text
semantic/vector seeds
       ↓
typed deterministic graph expansion
       ↓
bounded evidence selection
```

not:

```text
LLM agent freely explores graph
```

The graph earns its place when it recovers relationships vector similarity cannot.

---

# 3. "Retrieval failure" is not one failure class

A major independent investigation was the decomposition of the repository query path into evidence-survival stages.

A bad answer can originate at multiple independent stages:

```text
query
  ↓
seed retrieval
  ↓
graph discovery
  ↓
expanded-document ranking / cap
  ↓
per-document chunk fetch
  ↓
context assembly / context budget
  ↓
LLM generation
```

This became one of the most important diagnostic principles in the project.

## 3.1 Seed retrieval failure

An expected artifact can be stored, embedded, and retrievable, but not enter the initial vector seed set.

This has been observed especially when semantically rich prose competes with implementation code.

## 3.2 Graph discovery succeeds, document selection fails

A confirmed failure mode showed graph expansion discovering exact implementation helpers while a fixed expanded-document cap discarded them before their content was fetched.

Example shape:

```text
vector seed found
      ↓
graph finds exact helpers
      ↓
helpers rank below expanded-doc cutoff
      ↓
/search-by-doc never called for them
      ↓
answer-bearing implementation never reaches LLM
```

This is not a graph failure.

It is a **post-graph evidence-selection failure**.

## 3.3 Correct document survives, correct passage does not

A second confirmed failure mode showed that selecting the correct document still does not guarantee retrieving the answer-bearing passage.

`/search-by-doc` can return only a small subset of chunks, and previously observed behavior showed relevant implementation existing elsewhere in the same stored document.

Therefore:

> correct document != correct evidence

## 3.4 Final context can still remove useful evidence

Even after retrieval and document selection, context packing and budget limits can remove the required text.

This means document-level provenance is insufficient unless exact passage survival is measured.

## 3.5 Generation can still fail with sufficient evidence

Some answers remain wrong even when sufficient implementation evidence reaches the model.

This must remain a separate class from retrieval.

## Diagnostic rule

Do not classify a bad answer as "retrieval failure" until the exact answer-bearing passage has been traced through the complete pipeline.

---

# 4. Evidence survival is more useful than a simple source list

Traditional RAG observability often reports only:

```text
sources = [...]
```

That is insufficient.

A source appearing in the response does not prove the answer-bearing text reached the model.

The more useful model is:

```text
expected evidence
      ↓
seed?
      ↓
graph-discovered?
      ↓
selected document?
      ↓
required chunk fetched?
      ↓
required passage in final context?
      ↓
used correctly by model?
```

## Consequence

Evidence-survival instrumentation should remain foundational.

Useful fields include:

- seed canonical IDs,
- graph-expanded canonical IDs,
- mapped document IDs,
- expanded-document rank,
- fetched chunk IDs / indices,
- final-context manifest,
- exact text hashes,
- generation payload membership.

This is a stronger evaluation framework than answer correctness alone.

---

# 5. More top-k is not automatically better

A repeated external recommendation is to retrieve more candidates.

Our own experiments showed non-monotonic behavior:

```text
top_k = 5
→ implementation sometimes absent

top_k = 10
→ implementation appears, but competes with prose

top_k = 20
→ more distractors, sometimes worse answers
```

## Lesson

The optimization target is not context volume.

It is:

> useful evidence survival with minimal distracting evidence.

Increasing `top_k`, expanded-document caps, or context windows should initially be treated as **diagnostic controls**, not default fixes.

---

# 6. Context competition is a real failure mode

One evaluation failure contained the correct evidence near the top, yet the model selected a competing numerical value from another plausible passage.

This exposed a distinct problem:

```text
correct evidence
+
plausible competing evidence
+
small model
=
wrong answer
```

Potential mitigations we discussed include:

- near-duplicate suppression,
- source grouping,
- stronger canonical labels,
- better context ordering,
- conflict-aware instructions,
- evidence pruning,
- claim-specific source selection.

But these should be evaluated rather than enabled wholesale.

---

# 7. Near-duplicate chunks waste candidate capacity

Repository indexing naturally creates overlapping representations:

- module text,
- class text,
- function text,
- parent section text,
- documentation that repeats source behavior.

Without deduplication, top-k slots can be consumed by nearly identical content.

Example:

```text
rank 1  same implementation
rank 2  same implementation
rank 3  same implementation
rank 4  useful independent evidence
rank 5  useful independent evidence
```

## Lesson

Near-duplicate suppression is valuable, but it must not collapse genuinely distinct evidence.

A good deduplication strategy should preserve:

- distinct canonical artifacts,
- independent sources,
- materially different passages.

---

# 8. Authority is claim-dependent, not a single global score

A central lesson from repository self-querying is that similarity is not authority.

For the same repository, semantically similar sources can include:

- executable implementation,
- configuration,
- README descriptions,
- ADRs,
- plans,
- test results,
- historical investigations,
- fixtures,
- examples,
- stale architecture diagrams.

The correct source depends on the claim.

## Example authority patterns

### Current implementation question

Prefer:

```text
current implementation
> current configuration
> current documentation
> historical design/evaluation material
```

### Design-intent question

Prefer:

```text
accepted ADR / canonical design record
> implementation clues
> historical discussion
```

### Historical investigation question

The historical note itself may be authoritative.

## Lesson

Do **not** create one universal numeric authority score.

Instead, use **claim-specific evidence obligations**.

---

# 9. Self-contamination is a real and useful stress test

RAG-FOUNDRY-UNIVERSAL is unusual because it contains extensive commentary about itself:

- audits,
- old plans,
- test-result documents,
- architecture discussions,
- issue investigations,
- fixture references,
- previous descriptions of the repository.

This creates a self-contamination risk:

```text
correct repo selected
      ↓
historical note about repo retrieved
      ↓
note contains stale / experimental / wrong-project claim
      ↓
model presents it as current truth
```

This is not cross-repository contamination.

It is **same-repository authority contamination**.

## Strategic interpretation

Self-ingestion should not be dismissed as an unrealistic benchmark.

It is a valuable stress test because mature real repositories also contain:

- deprecated docs,
- migration notes,
- design history,
- examples,
- test fixtures,
- multiple generations of architecture.

If authority handling survives this repository, that is meaningful evidence.

---

# 10. Snapshot identity is foundational

DeepWiki and other external summaries reminded us that repository descriptions can become stale even when technically accurate at an earlier revision.

A repository intelligence answer must distinguish at least:

```text
runtime revision
indexed repository revision
local checkout revision
ingestion generation
```

A convincing answer from the wrong snapshot is still wrong.

## Lesson

Every serious evaluation should pin:

- deployed runtime SHA,
- ingested source SHA,
- repository ID,
- generation / ingestion ID,
- model and relevant query settings.

Snapshot identity should be treated as part of evidence provenance.

---

# 11. ORIENT is not ordinary semantic RAG

Repository-global questions include:

- What is this repository?
- What services are present?
- How is it structured?
- What languages/frameworks are used?
- What is its purpose?
- What are its major components?

Generic top-k similarity cannot guarantee repository-wide coverage.

## Lesson

Use deterministic inventory for global structure.

Use semantic retrieval for explanatory or local evidence.

The preferred conceptual split is:

```text
repository-global facts
→ deterministic inventory / typed derived facts

local implementation explanations
→ semantic retrieval + graph

historical/design intent
→ explicitly selected descriptive sources
```

This is the core rationale behind ORIENT.

---

# 12. A repository overview should not become a second source of truth

We considered generating a giant `REPO_STRUCTURE` or architecture document and embedding it.

That is dangerous because it would:

- duplicate facts already available in structured form,
- become stale,
- compete with implementation during retrieval,
- create another authority source.

## Lesson

Prefer:

```text
one factual representation
      ↓
multiple derived views
```

Examples:

- inventory table,
- textual overview,
- Mermaid rendering,
- architecture summary.

The canonical source should remain structured evidence, not generated prose.

---

# 13. Mermaid should be a derived view, not canonical truth

Architecture diagrams are useful for human understanding.

But persisted generated diagrams can become stale and later re-enter retrieval as misleading evidence.

Therefore:

> Mermaid should be rendered from current structured facts, not treated as an independent architectural authority.

If persisted, it should carry:

- snapshot identity,
- derivation version,
- underlying evidence references,
- clear `derived` role.

---

# 14. TRACE requires richer evidence, not merely deeper BFS

A tempting idea was:

```text
TRACE = graph traversal with greater depth
```

Independent investigation showed that this is insufficient.

Useful trace reasoning can require evidence not represented in the ordinary symbol graph:

- route registration,
- endpoint path/method,
- service membership,
- configured service URLs,
- HTTP client call arguments,
- source-root/PYTHONPATH semantics,
- edge provenance,
- ordered path evidence,
- confidence.

A concrete example was service-local Python `src` roots causing otherwise obvious calls to resolve as external symbols.

## Lesson

TRACE should be a bounded evidence workflow, not generic deep BFS.

It may combine:

```text
semantic entry-point discovery
+
exact symbol lookup
+
typed graph paths
+
route/config/service facts
+
LLM explanation
```

---

# 15. IMPACT should mean candidate affected-set, not breakage prediction

Reverse graph relationships can answer:

- possible callers,
- importers,
- subclasses,
- dependent modules.

But adjacency does not prove a change will break them.

Reliable breakage prediction may require:

- API/signature diff,
- types,
- runtime dispatch,
- test relationships,
- contract comparison,
- old/new snapshot comparison.

## Lesson

Use conservative language:

```text
candidate affected callers
possible downstream dependencies
potentially relevant tests
```

not:

```text
these components will break
```

This should remain a semantic contract of IMPACT.

---

# 16. Exact identifiers make lexical retrieval interesting — but only conditionally

Code and configuration contain strings that are naturally lexical:

- exact symbol names,
- environment variables,
- route names,
- class/function names,
- configuration keys.

Hybrid lexical + vector search is therefore plausible.

However, early evaluation did not establish a repeated lexical-miss pattern.

In some cases, graph traversal recovered vector misses.

## Trigger condition

Hybrid retrieval becomes justified when we repeatedly observe:

```text
exact identifier exists in indexed corpus
        ↓
vector seed retrieval misses it
        ↓
literal lexical lookup would recover it
```

Until then, hybrid search remains an experiment, not a roadmap requirement.

---

# 17. Reranking was explicitly deferred

Many external systems use:

```text
vector + lexical
       ↓
candidate set
       ↓
reranker
       ↓
context
```

We considered this seriously.

But the measured failure distribution did not initially support it.

There were essentially no cases where the correct evidence consistently sat at mid ranks waiting for a reranker.

In one major failure, the correct evidence was already near the top.

## Lesson

Do not add a reranker because modern RAG architectures often include one.

Add it only when candidate ranking is demonstrated to be the failure.

---

# 18. Embedding replacement should require a high evidence bar

Newer code-capable embedding models are attractive.

But an embedding change is operationally expensive:

- full corpus re-embedding,
- possible dimension changes,
- index invalidation,
- new latency/memory characteristics.

## Proposed evaluation

Compare candidates on the same pinned corpus and question set:

```text
Recall@5
Recall@20
MRR
latency
memory
code/symbol performance
multilingual performance
```

Until such a comparison shows a material gain, keep the current embedder.

---

# 19. Contextual retrieval is worth testing, but deterministic structural context should be the baseline

Anthropic-style Contextual Retrieval suggested prefixing chunks with a short description of where they belong.

That is attractive for repository code.

However, repository intelligence already has deterministic structural context:

- relative path,
- canonical symbol,
- parent,
- language,
- artifact type,
- graph relationships,
- provenance.

## Proposed experiment

Compare:

```text
A. raw function body

B. deterministic structural prefix
   path + symbol + parent + language + body

C. LLM-generated contextual prefix
   generated context + body
```

Measure retrieval recall and downstream answer quality.

## Important constraint

Generated contextual text is **retrieval metadata**, not source truth.

It must never silently become answer evidence.

---

# 20. Repository search and answer generation need not use the same model

External work on specialized search/decision models suggested another useful principle:

> The model that finds repository evidence does not have to be the model that writes the final answer.

A cheaper or specialized model could potentially help with:

- directory pruning,
- candidate file selection,
- snippet ranking,
- follow-up retrieval.

The final reasoning model would still receive exact source evidence.

## Guardrail

This should initially run in shadow mode against deterministic methods.

Measure:

- recall,
- latency,
- model calls,
- token cost,
- calibration,
- final task success.

Exact lookup, graph traversal, and deterministic inventory should not be replaced by a learned search model without evidence.

---

# 21. Deterministic mechanisms should precede agentic routing

Across several external architectures we repeatedly saw:

- LangGraph supervisors,
- LLM routers,
- autonomous search agents.

Our conclusion was consistent:

> First prove that deterministic routing cannot solve the observed failure.

Preferred order:

```text
exact lookup
  ↓
inventory
  ↓
typed graph traversal
  ↓
semantic retrieval
  ↓
bounded evidence follow-up
  ↓
LLM planner only if necessary
```

This keeps behavior testable and explainable.

---

# 22. Bounded evidence-sufficiency loops are promising

A useful middle ground exists between one-shot RAG and a general autonomous investigator.

Example:

```text
retrieve
  ↓
check evidence obligations
  ↓
missing one facet?
  ↓
perform one targeted follow-up
  ↓
answer
```

For ORIENT, required facets might include:

- purpose,
- services,
- languages,
- entry points,
- storage,
- deployment.

If one is missing, fetch that facet rather than letting an unconstrained agent explore the repository.

This remains a promising future direction.

---

# 23. Claim-specific evidence selection is now evidence-backed

Issue #240 materially strengthened a prior research hypothesis.

The correct evidence source depends on what the user is asking.

Examples:

```text
purpose
→ canonical descriptive source

current structure
→ current inventory

current architecture
→ current config + current implementation + typed architecture facts

historical investigation
→ historical notes explicitly allowed

exact symbol behavior
→ implementation artifact
```

A single broad `repository_overview` category may eventually be too coarse.

This is now more than a speculative idea.

---

# 24. Current ORIENT failures reveal a second layer: derivation discipline

The October #240 experiments uncovered a new class of failure.

Even with current evidence available, the model can make unsupported transformations.

Examples:

```text
9 Compose declarations
!=
9 distinct logical services
```

```text
pyproject.toml present
!=
Python import package exists
```

```text
missing inventory fact
!=
fact does not exist
```

```text
service + datastore in architecture
!=
all components communicate over HTTP
```

This is not ordinary retrieval failure.

It is **fact derivation / aggregation failure**.

---

# 25. Repository intelligence needs typed facts

The emerging architecture should not ask the LLM to infer every repository fact from loosely related prose.

A better direction is:

```text
raw inventory/config/implementation
            ↓
deterministic normalization
            ↓
typed repository facts
            ↓
claim-specific evidence selection
            ↓
LLM explanation
```

Possible fact types include:

```text
ServiceFact
- stable service name
- compose declarations[]
- source directory
- Dockerfile
- project manifest
- package markers[]
- test directories[]
```

```text
ArchitectureEdge
- source
- target
- edge type
- evidence
```

Possible edge types:

- HTTP_CALL
- DATASTORE_ACCESS
- DEPLOYMENT_DEPENDENCY
- IMPORT
- ROUTE_EXPOSES
- SERVICE_CONTAINS

The LLM should explain these facts rather than invent their semantics.

---

# 26. "Unknown" must be first-class

A recurring derivation error is turning missing evidence into a negative fact.

Repository intelligence needs to distinguish:

```text
present
absent-by-complete-enumeration
not observed
not established
unsupported
```

For example:

- no source directory was supplied by the inventory
  is not equivalent to
- the service has no source directory.

This should become part of both the fact model and answer policy.

---

# 27. Raw observations and normalized entities must remain distinct

The recent Compose example exposed another important distinction.

A repository may contain:

- nine service declarations across several Compose files,
- but fewer distinct logical services.

Therefore reports should distinguish:

```text
raw declarations
vs
deduplicated entities
```

Example:

```text
Compose evidence:
- 9 declarations
- 5 distinct application service names
- 1 datastore service
```

This normalization should be deterministic where possible.

---

# 28. External systems should be treated as hypothesis generators

Across DeepWiki, code-RAG projects, contextual retrieval systems, specialized search models, and large-scale RAG architectures, we repeatedly saw attractive components.

The mature rule that emerged is:

> What measurable failure in RAG-FOUNDRY-UNIVERSAL would make this component appropriate?

Examples:

### Reranker

Adopt when:

```text
correct evidence repeatedly appears below final ranking cutoff
```

### Hybrid lexical search

Adopt when:

```text
exact identifiers repeatedly exist but vector seeding misses them
```

### Larger context

Adopt when:

```text
needed evidence survives retrieval but repeatedly exceeds a justified context budget
```

### LLM router / agent

Adopt when:

```text
deterministic routing and bounded follow-up cannot satisfy known evidence obligations
```

### Graph database

Adopt when:

```text
measured graph storage/traversal performance becomes the bottleneck
```

External architecture is therefore a **menu of experiments**, not a backlog.

---

# 29. Evidence-backed roadmap implications

The following capabilities have enough evidence to deserve roadmap consideration.

## 29.1 Preserve and extend evidence-survival instrumentation

This is foundational evaluation infrastructure.

## 29.2 Continue claim-specific authority work

Issue #240 demonstrates that current claims, historical claims, and purpose/design claims require different evidence policies.

## 29.3 Add typed repository facts

Especially for:

- services,
- directories,
- package boundaries,
- manifests,
- tests,
- routes,
- application-to-application HTTP relationships,
- datastore relationships.

## 29.4 Add explicit unknown/not-established semantics

Prevent missing evidence from becoming negative facts.

## 29.5 Normalize raw declarations into stable entities

Especially Compose/service-level inventory.

## 29.6 Keep deterministic inventory as the basis of ORIENT

Semantic retrieval should augment, not reconstruct, repository-global facts.

## 29.7 Continue snapshot-aware evaluation

Runtime, corpus, and source revisions must remain independently pinned.

---

# 30. Investigation-worthy ideas that should not yet become committed roadmap work

These remain promising but conditional:

- lexical/BM25 + vector hybrid retrieval,
- reranking,
- alternative embedding models,
- LLM-generated contextual retrieval,
- specialized repository-search decision models,
- bounded evidence-sufficiency follow-up,
- broader architecture projections,
- richer TRACE evidence,
- stronger IMPACT analysis.

Each should get an explicit experiment and decision gate before implementation.

---

# 31. Explicit deferrals

The current evidence does **not** justify immediately adding:

- a dedicated graph database,
- generic LangGraph/agentic retrieval supervisor,
- blanket larger `top_k`,
- blanket larger context windows,
- universal source-authority scores,
- always-on reranking,
- automatic embedding replacement,
- unconstrained autonomous repository exploration.

These remain available future options, not current requirements.

---

# 32. Recommended design principles

The accumulated investigations suggest the following working principles.

1. **Measure the stage where evidence disappears before changing architecture.**
2. **Prefer deterministic facts over LLM reconstruction when the fact is mechanically derivable.**
3. **Treat authority as claim-specific.**
4. **Preserve historical material, but do not let it silently answer current-state questions.**
5. **Keep raw evidence distinct from normalized/derived facts.**
6. **Represent unknown explicitly.**
7. **Use graph traversal when relationships add evidence beyond vector similarity.**
8. **Do not optimize for context volume; optimize for evidence survival and low distraction.**
9. **Require new architectural components to correspond to measured failure modes.**
10. **Keep generation downstream of evidence construction; do not make the model responsible for repository inventory.**
11. **Pin runtime, corpus, and source snapshots in every serious evaluation.**
12. **Prefer bounded deterministic workflows before introducing autonomous agents.**

---

# 33. Working target architecture

The accumulated lessons point toward this repository-intelligence flow:

```text
Repository snapshot
       │
       ├── deterministic inventory
       │
       ├── code/config extraction
       │
       ├── graph relationships
       │
       └── source role/provenance
       │
       ▼
Typed repository facts
       │
       ├── services
       ├── packages
       ├── routes
       ├── datastores
       ├── architecture edges
       └── explicit unknowns
       │
       ▼
Claim classification
       │
       ├── purpose
       ├── structure
       ├── implementation
       ├── architecture
       ├── trace
       ├── impact
       └── historical/design
       │
       ▼
Claim-specific evidence plan
       │
       ├── inventory facts
       ├── exact lookup
       ├── vector seeds
       ├── graph expansion
       └── bounded follow-up if needed
       │
       ▼
Evidence-survival checks
       │
       ▼
Bounded, labeled context
       │
       ▼
LLM synthesis
```

The LLM remains important, but its role becomes narrower and safer:

> explain, connect, and summarize supplied evidence without inventing the repository model itself.

---

# 34. Roadmap reorientation implications

This research suggests that the next roadmap should no longer be organized mainly around generic RAG improvements.

A more accurate repository-intelligence track would be:

```text
1. Evidence correctness and survival
2. Repository inventory and snapshot identity
3. Claim-specific authority
4. Typed repository facts / normalization
5. ORIENT quality
6. TRACE evidence model
7. IMPACT evidence model
8. Targeted retrieval experiments
9. Scale and productization
10. Agentic behavior only where bounded methods prove insufficient
```

This should be reconciled with the current implementation state and October #240 results before replacing or editing the formal roadmap.

---

# 35. Status of this note

This document intentionally contains a mixture of:

- measured findings,
- architectural lessons,
- hypotheses,
- and explicit deferrals.

It is **research input**, not a specification.

Before any item becomes implementation work, it should be promoted through the project’s normal process:

```text
observed failure
    ↓
focused experiment
    ↓
measured result
    ↓
decision
    ↓
issue / ADR / roadmap item
```

That evidence-first discipline is itself one of the most important lessons from the investigations recorded here.
