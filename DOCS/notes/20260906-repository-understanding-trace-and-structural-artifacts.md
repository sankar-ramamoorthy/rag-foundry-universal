# Repository Understanding, Trace, and Structural Artifact Findings
## 2026-09-06 exploratory evaluation

Status: design/evaluation note. Not an implementation task, not a roadmap change,
not a decided architecture. Captures observations and architectural implications
from hands-on use of RAG-FOUNDRY-UNIVERSAL today so they can inform future
roadmap/design work, without pre-committing to any of it.

## 1. Why this note exists

During live use of RAG-FOUNDRY-UNIVERSAL against several real ingested repositories
today (rag-foundry-universal itself, TradeForge, TradeForge-KnowledgeBase,
TradeForge-ResearchCockpit, and py-coding-agent), we explored a possible future
consumer workflow:

1. **ORIENT ME**
   - What is this repository?
   - What directories/packages/services does it contain?
   - What does the architecture look like?
2. **TRACE THIS**
   - Follow a symbol, behavior, feature, request path, or bug through the repository.
3. **ASSESS IMPACT**
   - What callers, imports, services, tests, or other areas may be affected?
4. Later possibility: **INVESTIGATE**
   - Determine whether available evidence is sufficient.
   - If not, retrieve/inspect further evidence and repeat.

Today's experiments were exploratory. They should inform future architecture but
do not imply these capabilities should be implemented immediately.

## 2. Existing retrieval work immediately preceding these experiments

Context from issues #89 and #91, both from earlier today.

### #89 (closed, PR #90)

The diagnosed failure was:

```
vector seed
  -> graph expansion successfully discovers authoritative implementation evidence
  -> expanded candidates are ranked/capped
  -> relevant implementation document falls below MAX_EXPANDED_DOCS
  -> its chunks are never fetched
  -> implementation does not reach final LLM context
```

The fix introduced relation-aware expanded-candidate ranking
(`rag_orchestrator/src/retrieval/traversal_selector.py`).

Live A/B against real, freshly re-ingested data
(`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`
section 16) confirmed:

- Q7 `traverse_defines`: rank 24 -> 12
- final-context survival: False -> True
- 103 tests passed, no regressions observed across the unaffected questions

### #91 (open)

A distinct limitation remains:

- Q10 `run_simple_rag`: rank 137 -> 88
- improvement is real, but still below the cap
- this is a same-relation-type candidate-overload problem, not the original #89
  failure mechanism

#91 tracks that separately. The findings in this note are **not** folded into #91
automatically — several failure classes observed today look conceptually
different from either #89 or #91 and are recorded here without assignment to an
issue.

## 3. Important methodological finding: evaluation/source contamination

After `DOCS/test_results/*.md` documents were committed and the repository
re-ingested, they became ordinary retrievable corpus content
(`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`
section 16 documents this directly). That creates two forms of contamination.

### 3.1 Benchmark contamination

The repository can retrieve documents that literally contain previous evaluation
questions, expected answers, prior failures, ground-truth explanations, and fix
descriptions.

The existing question set therefore remains useful for retrieval-regression
instrumentation (target rank, graph discovery, candidate survival, final-context
presence) but is no longer a clean answer-quality benchmark against the same
corpus.

### 3.2 Subject/authority contamination

The problem is broader than benchmark leakage. Documents inside one repo can
describe test fixture repositories, historical repositories, examples,
proposed/future structures, archived designs, or previous implementation states.
A RAG answer can mistake statements about those embedded subjects for facts about
the currently selected repository.

Reported live: a question asking for the actual repository directory/service/
package structure returned the structure of a small `my_test_repo` fixture
documented inside historical/test-result material. The UI-selected `repo_id`
remained the correct RAG-FOUNDRY-UNIVERSAL repo, but the model effectively allowed
retrieved content to redefine the subject.

This suggests a future repository-identity invariant:

> The selected `repo_id` is the subject of the query unless the user explicitly
> asks about another embedded/example repository. Fixture/example/archive text
> must not silently redefine repository identity.

Not implemented; preserved as a design requirement candidate.

## 4. ORIENT ME experiments

### 4.1 Generic "repo structure" query

Query: *"I need information about the repo structure."*

RAG retrieved a document about the repository **graph structure** and answered
with an illustrative artifact hierarchy such as MODULE/CLASS/METHOD and
DEFINES/CALL relationships — coherent, but answering the wrong meaning of "repo
structure."

Observed distinction: "repo structure" may mean the actual filesystem/service/
package organization, whereas the retrieved material interpreted it as the
repository graph / `DocumentNode` structural model (ADR-030, ADR-031).

Classification: intent/source-selection ambiguity — a semantically close document
title can dominate even when it represents the wrong conceptual meaning.

### 4.2 Explicit actual-directory query

Query: *"Describe the actual directory, service, and package structure of this
repository."*

RAG then described `my_test_repo`, a fixture documented inside test-result
material. Classification: repository-subject contamination / identity grounding
failure (see section 3.2).

### 4.3 Explicit repo-name query

The query was strengthened by explicitly naming RAG-FOUNDRY-UNIVERSAL. Repository
identity was then preserved, but the answer fabricated a plausible Python
microservice filesystem from ADR concepts plus general Python conventions — the
response itself said it was reasoning from the ADRs and "standard practices for
Python microservices." The claimed paths/components did not match the actual
current repository.

Classification: generation grounding failure caused by insufficient authoritative
structural evidence. Important principle: for a question asking for the *actual*
filesystem or architecture, general software conventions are not evidence. Missing
structural evidence must not be filled with plausible conventional layouts and
presented as current fact.

### 4.4 Direct-repository comparison

Independent direct repository inspection (reading the repo directly rather than
through RAG) produced a materially better structural view, because it could
inspect actual top-level directories, actual service directories, actual
packages, README/agent guidance, DOCS layout, specs layout, per-service
dependency/test structure, and implementation locations directly.

This demonstrates the requested information exists and is mechanically obtainable
from the repository. The problem is not that "repo structure" is unknowable — the
problem is that generic semantic top-k retrieval is a poor primitive for a
repository-global structural question.

### 4.5 Cross-repo confirming case: a dedicated diagram file invisible to retrieval

A related, independently-traced case on a different ingested repo
(py-coding-agent, `repo_id 863e770d-651e-5bc5-83d1-a1409693e707`) reinforces 4.1-4.4
with hard evidence rather than a reported account:

Query: *"Give me an architectural map of this repository."* RAG answered that "the
requested map itself is not present in the provided materials," citing only
`docs/architectural-summary.md` and `docs/architectural-summary-by-codex-20260412.md`
as sources.

Direct inspection confirmed `docs/architectural-diagram.md` exists, is fully
ingested, chunked, and embedded, and its third chunk *is* a hand-maintained ASCII
architecture diagram of the agent loop — exactly what was asked for.

Tracing with the `evidence_trace` instrumentation from #89
(`trace_canonical_ids={"docs/architectural-diagram.md"}` on `hybrid_retrieve`)
showed:

```json
{
  "canonical_id": "docs/architectural-diagram.md",
  "found_by_vector": false,
  "found_by_graph": false,
  "expanded_rank": null,
  "survives_cap": false,
  "chunk_fetched": false,
  "reaches_final_context": false,
  "drop_reason": "not_found_by_vector_or_graph"
}
```

The file was never found by either seed vector search or graph expansion — a
different mechanism from both #89 (cap truncation of an already-discovered
candidate) and #91 (same-relation-type overload). Most likely cause: the file's
first chunk is almost pure structure/metadata (title, refresh date, one header)
and its diagram chunk is dense ASCII box-drawing with very little natural-language
content, both of which likely embed weakly against a natural-language query; and
since `docs/architectural-summary.md` merely *mentions* the diagram file by name
rather than containing a code-style reference to it, there is no DEFINES/CALL-type
graph edge for graph expansion to follow between the two documents (doc-to-doc
edges are out of scope for the current cross-linking model, which links
docs-to-code only — ADR-048).

This is the same `not_found_by_vector_or_graph` pattern already seen in this
session's own live eval of rag-foundry-universal (Q1/Q3 in
`DOCS/test_results/2026-09-03-rag-quality-source-eval.md`), now confirmed to
generalize to a different repo and to non-code (pure documentation) content. It is
concrete supporting evidence for section 15's central insight below, not a claim
that this exact mechanism explains 4.1-4.3 (which look more like intent-ambiguity
and subject-contamination failures than a pure not-found case).

## 5. Architectural implication: preserve repository structure as a first-class artifact

Strong candidate idea: during deterministic repository ingestion, derive and
persist an authoritative repository-structure artifact.

Example conceptual type: `REPO_STRUCTURE`.

Potential contents: root directories, files, package roots, service roots,
languages, manifest files, pyproject/package metadata, Docker/Docker Compose
services, entry points, top-level configuration, perhaps counts/statistics.

Potential metadata: `source_role: generated_structural_fact`,
`authority: current_filesystem`, `repo_id`, `ingestion_id`, `commit_sha` (if/when
tracked), `generated_by: deterministic_ingestion`.

Critical constraint: this should be deterministic and require **no LLM call**
during ingestion.

The artifact could be represented in two complementary forms:

1. a retrievable text/document representation for semantic RAG
2. a graph representation, e.g. `REPOSITORY -CONTAINS-> DIRECTORY / SERVICE / PACKAGE / FILE`

This would give repository-wide questions an authoritative source instead of
forcing the LLM to infer filesystem structure from arbitrary chunks.

This is a design candidate, not yet a work package.

## 6. Architectural implication: preserve an architecture graph/artifact

A second candidate is a first-class architecture representation, preferring
deterministic facts where possible.

Potential mechanically derived relationships: `SERVICE -OWNS_PACKAGE / EXPOSES_ENDPOINT / CALLS_SERVICE / DEPENDS_ON / USES_DATASTORE->`.

Possible evidence sources: Docker Compose, FastAPI route registration, HTTP
client/service URL configuration (`shared/config/service_urls.py`), imports, the
current CALL/IMPORT graph, package/service boundaries, database
ownership/configuration, entry points.

The canonical artifact should represent mechanically supported facts, not an
LLM's guess at architecture.

Potential flow:

```
filesystem inventory
  + language extraction / IR
  + GraphAssembler
  + routes/config/compose/import evidence
    -> repository structural graph
    -> architecture graph
    -> retrievable architecture artifact
```

Relates conceptually to `DOCS/audit/02-Graph-Depth-Analysis.md` and
`DOCS/audit/03-Multi-Language-Graph-Plan.md`, without proposing to change either.

## 7. Mermaid diagrams

The ability to answer "show me the architecture as Mermaid" does **not** itself
require full agentic behavior. Once an authoritative architecture graph exists,
Mermaid can be treated primarily as a rendering/presentation format:
`architecture graph -> Mermaid -> Graphviz / UI visualization / ASCII if desired`.

An LLM could render the graph into Mermaid, but the underlying facts should come
from authoritative structured evidence. If an LLM-generated architectural summary
is later persisted, it should be distinguished from canonical facts with metadata
such as `source_role: derived_summary`, `authority: synthesized`,
`derived_from: [...]`, `model: ...`, `prompt_version: ...`. A synthesized summary
should not have equal authority to current filesystem/code facts.

## 8. TRACE THIS experiment

Prompt tested: *"Trace a RAG query through the current implementation from the
`/v1/rag` API request until the final context is sent to the LLM. Identify
concrete files and functions in execution order. Include vector seed retrieval,
graph expansion, expanded-candidate ranking/capping, per-document chunk
retrieval, context budgeting, and LLM generation. Use current implementation code
as authority."*

Result at `top_k=10`: the answer was organized and sounded like a trace, but
largely replayed the existing 2026-09-03 diagnostic test-result document — it
described the old tree-sitter/`base.py` failure, "59 expanded candidates -> 20
used," `_compiled_query`/`_language_for`/`_parser_for`, and historical
final-context loss. It did **not** successfully derive the current `/v1/rag`
execution chain from the current implementation. Most cited evidence came from
`DOCS/test_results/`, `docs-archive/`, and old design/handover documentation.
Current `rag_orchestrator/src/core/service.py` appeared among the sources but did
not dominate synthesis.

Classification: the current system can **retell** an already-documented trace, but
cannot yet reliably **derive** a fresh behavioral trace from the current codebase.

## 9. Architectural implication: TRACE THIS should likely be graph-driven

Generic semantic top-k is probably not sufficient for execution tracing.

Candidate future behavior:

```
behavior-trace intent
  -> resolve entry point / symbol
  -> retrieve current implementation
  -> follow CALL relationships
  -> follow relevant import/service boundaries
  -> retrieve implementation at each hop
  -> continue until requested sink/end condition
  -> produce ordered trace with evidence for every hop
```

Possible questions this should eventually support: trace `/v1/rag` from request
to LLM; trace symbol X; where is this behavior implemented; what calls X; what
does X call; which service boundary does this cross; where could
evidence/data be dropped; show the likely execution path for this bug.

This is much closer to using the existing graph intentionally than asking vector
retrieval to return a representative set of the entire behavior.

## 10. Proposed product/use-case framing

A useful conceptual sequence for how a future consumer might use
RAG-FOUNDRY-UNIVERSAL, surfaced by today's exploration:

**Mode 1 -- ORIENT ME.** At first contact with a repository: what is this repo;
what languages/frameworks; what directories/packages/services; what are the
entry points; what are major runtime flows; what depends on what; what is
current implementation vs. plans/history; show architecture as Mermaid. Likely
requires first-class repository/architecture structural artifacts (sections 5-6).

**Mode 2 -- TRACE THIS.** Given a symbol, endpoint, feature, observed behavior, or
bug symptom, follow the relevant implementation and relationships through the
repo. Likely graph-driven (section 9).

**Mode 3 -- ASSESS IMPACT.** Given a likely change or bug location: callers,
imports, inheritance, overrides, services, tests, dependent modules,
documentation, other likely affected areas. A natural use case for the graph once
TRACE is reliable.

**Mode 4 -- INVESTIGATE / evidence sufficiency (later).** Potential agentic
evolution: retrieve -> inspect evidence -> determine whether evidence is
sufficient -> identify missing evidence -> perform another retrieval/traversal ->
reconcile conflicts -> answer only after sufficient evidence or explicitly report
gaps. This would be the meaningful transition from deterministic graph-aware RAG
toward a graph-aware RAG agent. Do not assume this needs to be implemented now —
relates to, but does not commit to, the direction sketched in
`DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`.

## 11. Source authority is becoming a first-class concern

Today's failures reinforce a distinction between content classes the corpus
already contains as searchable text without equal epistemic authority: current
implementation, current structural fact, current authoritative documentation,
ADR/design intent, plan/spec, test result, fixture/example, archived/historical
material, derived LLM summary.

A question such as "what actually exists now?" should strongly prefer current
filesystem facts, current implementation, and current configuration over plans,
archived docs, fixtures, old test results, and examples. A question such as "what
was the intended design?" may legitimately prioritize ADRs/plans instead.

Preserve this as a future architecture/evaluation concern rather than immediately
adding hardcoded filters.

## 12. Important non-conclusions

Do **not** conclude from today's experiments that:

- code-heavy repos inherently perform worse than docs-heavy repos
- simply increasing `top_k` solves repo understanding
- #91 explains all observed failures
- historical/test docs should simply be deleted from ingestion
- an LLM should generate canonical architecture during deterministic ingestion
- we need an autonomous agent immediately
- the roadmap should be reordered now

Several code-heavy and documentation-heavy repos answered generic questions well
today (see the earlier same-day "describe yourself" comparison across TradeForge,
TradeForge-KnowledgeBase, TradeForge-ResearchCockpit, and py-coding-agent). The
observed failures are more nuanced and appear related to intent, coverage,
authority, repository identity, and structural/global retrieval — not to a
repo's code/docs ratio alone.

## 13. Evaluation ideas to preserve for later

**Repository-orientation benchmark.** Ask the same question through (A)
RAG-FOUNDRY-UNIVERSAL and (B) a direct source-reading agent. Compare: purpose,
top-level directories, packages, services, entry points, languages/frameworks,
component relationships, missing major components, unsupported claims, use of
historical/fixture evidence, repository identity preservation.

**Ambiguity test.** Compare answers to: (1) "I need information about the repo
structure." (2) "Describe the actual directory, service, and package structure of
this repository." (3) "Describe the repository graph structure and DocumentNode
relationships." A healthy system should distinguish the intents.

**Behavioral-trace benchmark.** Have RAG and a direct-reading agent independently
trace the same known behavior. Grade: correct entry point; correct function
sequence; correct cross-service calls; correct graph edges; correct
endpoint/sink; every hop supported by current code; no invented intermediate
functions; missing evidence explicitly acknowledged.

**Retrieval evidence metrics.** Continue tracking (via the `evidence_trace`
instrumentation added in #89): target discovered by vector retrieval; target
discovered by graph traversal; target rank before cap; target survives cap;
target chunk fetched; target reaches final context; final answer uses
authoritative evidence. This instrumentation proved highly useful in #89 and in
section 4.5 above.

## 14. Relationship to existing roadmap

This note is future architecture/evaluation input. It appears related
conceptually to graph depth (`DOCS/audit/02-Graph-Depth-Analysis.md`),
multi-language IR/GraphAssembler (`DOCS/audit/03-Multi-Language-Graph-Plan.md`),
retrieval quality (`DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md`,
`DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`), scalability/incremental
ingestion (`DOCS/audit/04-Scalability-Plan.md`, and the nightly-ingestion decision
in `DOCS/notes/20260906-nightly-repo-ingestion-decision.md`), observability, and
the eventual evidence-sufficiency/agentic-RAG direction already flagged as
hypotheses-not-architecture in `DOCS/audit/09-Retrieval-Technique-Decision-Gates.md`.

Do **not** modify sequencing merely because these ideas were discovered today. The
existing discipline remains: observe failure -> instrument -> reproduce -> isolate
mechanism -> create a scoped issue/work package only when justified -> measure
before/after. Today's #89 process (`DOCS/test_results/2026-09-03-rag-retrieval-quality-linux-tailscale-baseline.md`
sections 13-16) is the model for how these future ideas should eventually be
turned into implementation work, if and when they are.

## 15. Central architectural insight

Preserve this statement prominently:

> Repository-global structural facts should be first-class ingested artifacts,
> not facts the LLM is expected to infer opportunistically from arbitrary top-k
> chunks.

And a related statement:

> Behavioral traces should be derived by intentional traversal of current
> implementation relationships, not by retrieving prose that happens to describe
> a previous trace.

These two ideas may materially shape future RAG-FOUNDRY-UNIVERSAL architecture.
