---
title: "Independent review and response: November 10 code intelligence architecture audit"
date: 2026-11-10
type: audit-review
status: discussion
source_commit: 4ba2387ecd51e869357d5d015b7c29b079da884d
source: "Independent review supplied by the owner in chat; author not independently established"
respondent: "Codex (GPT-6 Astra), author of the reviewed audit"
verification: "Assessment of the supplied review and recorded audit evidence; no new probe reproduction or live-system verification"
scope: "Code intelligence only; document intelligence excluded"
authority: "Proposed investigation priorities and contracts; no implementation or execution authorization"
aliases:
  - "Independent Review of the November 10 Audit"
  - "Code Intelligence Audit Review and Astra Response"
tags: [audit, audit-review, architecture, code-intelligence, evidence-contracts, prioritization]
related:
  - "[November 10 code intelligence audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[Strategic vision discussion](/DOCS/notes/20261110-full-vision-and-strategic-roadmap.md)"
  - "[July 9 audit overview](/DOCS/audit/00-Audit-Overview.md)"
  - "[July 9 findings](/DOCS/audit/01-Codebase-Audit-Findings.md)"
  - "[September 16 architecture audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md)"
  - "[ADR-050: repository lifecycle](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)"
  - "[ADR-054: evaluation isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[ADR-055: node-text read endpoint](/DOCS/adr/ADR-055-node-text-read-endpoint.md)"
---

# Independent review and response

> [!abstract] Purpose and attribution
> This file preserves the owner's supplied independent review of the
> [November 10 audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)
> and the audit author's response. The supplied review explicitly evaluates the
> audit's reasoning without independently reproducing its probes. The response
> below is a critical assessment, not an additional independent validation.
> Neither part changes the original audit or constitutes an accepted ADR,
> implementation plan, production finding, or experiment authorization.

The historical chain is the [July 9 audit](/DOCS/audit/00-Audit-Overview.md),
the [September 16 architecture audit](/DOCS/audit/2026-09-16-repository-architecture-audit.md),
the November 10 code-intelligence audit, and this review of that audit. Later
discussion does not erase the earlier records or automatically supersede their
decisions. Code references refer to the November 10 audit's recorded source commit.

## Part I — Supplied independent review

The following preserves the full supplied review. Heading levels and the copied
display fragments have been normalized for Markdown readability; the review's
claims and recommendations are retained.

### Independent Review of the November 10 Code Intelligence Architecture Audit

RAG-FOUNDRY-UNIVERSAL | Review of GPT-6 Astra's findings

### 1. My overall assessment

Astra's review is architecturally sound, and I agree with its central conclusion. But I would change how we prioritize some of its findings.

The most important observation is that RAG-FOUNDRY-UNIVERSAL is no longer struggling primarily with whether it has the right architectural components.

We now have a substantial foundation: a common intermediate representation (IR), multilingual extractors, a canonical graph, structural inventory, generation-aware retrieval, TRACE, IMPACT, provenance, and bounded evidence assessment.

The more significant question is:

Do the contracts between these components preserve the guarantees that each component individually provides?

For example, having a generation-aware cache does not necessarily guarantee that the graph returned belongs to the generation identified by the cache. Having extracted source code does not mean that all its content is represented in the embeddings. And successfully traversing a graph does not necessarily mean an impact assessment is complete.

This is a meaningful architectural maturity issue.

However, I would distinguish between three things:

- An architectural design that needs correction.
- A sound architecture with implementation defects.
- A capability that we have not yet chosen to build.

Astra makes these distinctions, but its priority grouping sometimes treats them too similarly.

One important limitation: I am independently evaluating the audit's evidence and reasoning, not claiming to have reproduced its source-code probes against the November 10 commit.

### 2. My assessment of all nine findings

| Finding | Astra | My assessment | Action |
| --- | --- | --- | --- |
| CI-01 Generation identity | P1 | Architectural contract defect | High priority |
| CI-02 Blocking graph I/O | P1 | Implementation defect | Fix when verified |
| CI-03 Incremental reuse identity | P1 | Architectural correctness gap | High priority |
| CI-04 IMPACT completeness | P1 | Confirmed logical defects | Fix narrowly |
| CI-05 Extraction failure visibility | P1 | Coverage and correctness gap | High priority |
| CI-06 Embedding coverage | P2 | Confirmed representation defect | Elevate investigation |
| CI-07 Unbounded graph workloads | P2 | Scalability limitation | Measure first |
| CI-08 Behavioral sufficiency | P2 | Missing capability | Research/design |
| CI-09 RAG policy composition | P2 | Maintainability and accounting debt | Defer major refactor |

My strongest agreement is with CI-01, CI-03, CI-05, and CI-06. These concern the trustworthiness of the representation and evidence itself.

I would not propose a broad architectural rewrite based on this report.

### 3. The findings I consider most consequential

#### CI-01 — Generation identity is not guaranteed end-to-end

High priority

Astra demonstrated a specific inconsistency using a synthetic probe.

The cache can:

1. Check that repository generation A is current.
2. Load a graph representing generation B.
3. Associate that graph with generation A.

That is a genuine contract defect.

The problem is not that the cache lacks generation awareness. We already invested in that. The problem is that the generation being checked is not necessarily the generation of the graph actually returned.

This becomes especially important when ingestion and queries overlap.

My recommendation is to establish an invariant:

> Every graph response must identify the generation of the data actually returned, and consumers must validate that identity before using or caching it.

The audit additionally notes that graph nodes and relationships are read separately, allowing a possible rebuild interleaving. A generation identifier alone would not fix that database-level consistency issue.

Verdict: Astra is correct. Preserve the existing architecture, strengthen the snapshot and export contract, and test the race.

#### CI-03 — Incremental ingestion does not fully identify what is being reused

High priority

This is a more subtle architectural gap.

Our reuse mechanism identifies unchanged files and considers the chunker version and embedding provider/model name.

But the final embedding depends on a longer transformation chain:

```text
Source bytes
Extractor + source representation
Chunking + preprocessing
Embedding model and effective input
Persisted chunks and vectors
```

Suppose the TypeScript extractor changes how a method's source text is rendered.

The original source file may remain byte-identical, but the representation supplied to the embedding model can change.

If the system reuses the old vector, the graph's current text and the vector's represented text might disagree.

This challenges an architectural assumption: unchanged source bytes do not necessarily imply unchanged derived evidence.

I would investigate content-derived fingerprints for the effective embedding input, together with versioned transformation identities.

A fingerprint should be tied to what actually gets embedded, not merely the repository file.

Verdict: A fundamental correctness issue worth resolving before expanding incremental ingestion further.

#### CI-05 — Extraction failure can look like code absence

High priority

This is particularly important for a code intelligence product.

The audit identifies extraction exceptions that are caught without preserving adequate per-file failure evidence.

Consider a user asking:

Where is method `process_request` implemented?

If the relevant file failed to parse, the system may lack the method in its graph.

There is a significant semantic difference between:

- We successfully analyzed the file and did not find that method.
- We were unable to analyze the file.
- That file type is unsupported.

The existing inventory records some coverage information, but Astra found that extraction-failure reasons do not adequately survive into its gap reporting.

My recommendation: Treat extraction coverage as a first-class result, rather than treating a completed ingestion as a claim of complete analysis.

This does not mean every failed file should abort ingestion. It means the system needs to distinguish known absence from unknown coverage.

Verdict: This is a foundational trust problem, closely related to the evidence-sufficiency work already undertaken.

#### CI-06 — Some stored code contributes nothing to its embeddings

Elevate investigation priority

This is arguably the most immediately interesting retrieval finding.

Astra reports that the large-artifact chunker uses:

- 1,000-character chunks
- 100-character overlap
- An Ollama embedding adapter that truncates each input to 800 characters

Consider the resulting coverage:

```text
First 1,000-character chunk:
  Characters 0–799 embedded
  Characters 800–999 omitted

Second chunk starts at character 900.
Characters 800–899 from the first window can be absent
from every embedding input.
```

Conceptual illustration of the reported character-window mismatch, not a measurement of actual tokenization.

Because the embedding window advances by 900 characters, while only 800 characters of each chunk reach the embedder, gaps are possible.

Astra tested exactly this with a marker and demonstrated that the marker appeared in stored chunks but in none of the effective embedding inputs.

That is much stronger than a speculative retrieval concern.

It does not prove that those code regions cannot be recovered through graph traversal or other evidence. It does prove that the omitted text does not contribute to the affected vectors.

I would elevate CI-06 because it directly affects the subsystem's ability to discover source evidence.

The first experiment should measure the coverage loss, not immediately change the chunker. Correcting the chunk/embedding contract may require re-embedding existing repositories.

Verdict: A genuine representation defect, supported by a reproducible probe.

### 4. Findings that need narrower treatment

#### CI-02 — Blocking graph operations

Astra traces synchronous graph-loading functions being called from asynchronous TRACE and IMPACT endpoints. Cold graph loading also uses an HTTP request without a timeout.

This is a real implementation problem. It can block the event loop and reduce responsiveness for unrelated requests.

However, I would not classify this as a failure of the overall architecture.

Our existing service boundaries can accommodate nonblocking operations, explicit deadlines, and bounded concurrency. We do not need another service or framework to address it.

I agree with P1, particularly because the proposed concurrency test is inexpensive and the risk is operationally significant.

#### CI-04 — IMPACT reports incomplete analysis as complete

Astra's probes found two defects:

- IMPACT can reach a depth limit without reporting that additional affected nodes may exist.
- When a candidate has multiple supporting relationships, the candidate limit can prevent all supporting evidence from being recorded.

These are genuine correctness bugs in the semantics of IMPACT.

I would fix them before treating IMPACT output as a reliable basis for downstream decisions.

But they do not require a redesign of graph traversal.

I would also separate structural completeness from actual breakage prediction. An exhaustive reverse-call graph still cannot prove which software components will fail following a change.

#### CI-07 — The graph workload remains partly unbounded

The audit identifies several scaling risks, including full-graph materialization, concurrent cold loads, repository-wide graph construction, and unbounded intermediate neighbor processing.

All are plausible.

What it does not establish is which of these currently causes unacceptable latency or memory consumption.

I agree with Astra's P2 classification. The next step should be a benchmark with a representative large repository, not an immediate architectural change.

#### CI-08 — Structural evidence is not behavioral understanding

This is probably the most strategically important finding, but I disagree with treating it as a defect to fix.

Our current structural evidence can help answer questions about relationships, reachability, imports, and candidate impact.

It does not establish that we understand arbitrary program behavior.

Consider the distinction:

Structural question: Which functions can call `persist_graph`?

Behavioral question: Under what circumstances could a failed rebuild leave a user querying inconsistent repository evidence?

The second requires understanding control flow, database transactions, exceptions, state transitions, and potentially runtime behavior.

We should pursue that capability because it serves the Code Intelligence vision, not because the existing structural subsystem is inherently defective.

I agree with Astra's recommendation to define a narrow behavioral-evidence contract before developing a general autonomous investigator.

#### CI-09 — RAG orchestration has become complex

Astra observes that retrieval, source policy, context allocation, diagnostics, and generation are concentrated in a large orchestration module.

It also identifies a specific accounting issue: overview policy text is inserted after the retrieved-context budget is calculated, so the reported accounting does not represent the complete model payload.

I would distinguish the two:

The accounting issue is concrete and worth correcting or explicitly labeling.

The architectural complexity is technical debt, but splitting the module into many new abstractions is not automatically an improvement.

I would defer any major refactor until we can identify stable intermediate contracts and preserve the existing evaluation results.

### 5. Where I differ from Astra on priorities

Astra proposes six investigations. I would adjust the order to separate low-cost correctness fixes, architectural contract work, and longer-term research.

| Order | Investigation | Rationale |
| --- | --- | --- |
| 1 | CI-01: Generation consistency | Protect against mixed-snapshot evidence |
| 2 | CI-06: Embedding coverage | Quantify known missing source representation |
| 3 | CI-03: Incremental reuse identity | Preserve consistency between current source and derived vectors |
| 4 | CI-05: Extraction coverage | Distinguish missing code from unexamined code |
| 5 | CI-04 + CI-02: Structural API correctness | Repair known semantics and responsiveness defects |
| 6 | CI-08: Behavioral evidence | Define the next level of capability |
| 7 | CI-07 + CI-09: Scale and maintainability | Improve based on workload measurements |

These are investigation priorities, not a proposed sequence of implementation issues.

CI-04 in particular may be inexpensive enough to fix alongside the early work, once an issue and acceptance tests are approved.

### 6. Is there a deeper architectural issue the audit didn't fully explore?

Yes. This is where I would push our thinking further.

The review analyzes the major existing components and their contracts. But the larger question is whether Code Intelligence should be organized around types of questions, rather than around the retrieval mechanisms we have implemented.

Consider four progressively more demanding capabilities:

| Capability | Purpose | Mechanisms/evidence |
| --- | --- | --- |
| 01 — DISCOVER | Find source artifacts and relevant passages | Vector search, structural lookup, graph expansion |
| 02 — ORIENT / TRACE | Understand repository structure and relationships | Inventory, service topology, deterministic paths |
| 03 — EXPLAIN | Understand what implementation actually does | Statement-level evidence, behavior and data-flow reasoning |
| 04 — ASSESS IMPACT | Determine possible consequences of changes | Cross-revision analysis, callers, contracts, tests, uncertainty |

This is my own architectural interpretation, not a four-layer model established by Astra's audit.

The capabilities require overlapping but different evidence contracts.

For example, an ORIENT question may be satisfied by a complete structural inventory. A behavioral explanation may require exact source statements and execution-path reasoning. An impact assessment may require two repository revisions and explicit uncertainty about dynamic behavior.

The interesting architectural question becomes:

> Can we establish a common evidence foundation that supports increasingly sophisticated question workflows without forcing every question through one generic RAG pipeline?

Astra touches this in CI-08, but I think it deserves its own architectural investigation.

Importantly, I am not suggesting four independent pipelines or another framework. The point is to understand which contracts can be shared and where different types of questions genuinely require different processing.

### 7. What would I preserve?

This is equally important. We should not let another audit trigger unnecessary architectural churn.

I agree with preserving the core architectural choices:

- Language-neutral IR and centralized graph assembly.
- Canonical repository-scoped identities.
- PostgreSQL-based graph and vector persistence unless measurements justify a change.
- Deterministic structural extraction and traversal.
- Explicit source provenance and generation identity.
- Separation of ingestion, retrieval orchestration, and LLM synthesis.
- Evidence-based evaluation before adopting rerankers, agents, or additional storage infrastructure.

Nothing in the November 10 audit establishes that these architectural choices should be abandoned.

### 8. Final verdict

- **4** foundational contract or representation concerns
- **2** narrow implementation correctness issues
- **3** scaling, capability, or maintainability concerns

My classification of the nine findings; these are not nine independently verified production defects.

I would rate the audit highly for its diagnosis and evidence discipline. It found meaningful issues, did not confuse absent features with bugs, and generally resisted recommending new infrastructure.

My principal disagreement is that it could have separated immediate engineering corrections from the broader evolution toward behavioral code intelligence more sharply.

#### What I recommend next

I would start with CI-01 and CI-06.

They illuminate two different but fundamental guarantees:

- CI-01: Are we reasoning over one consistent repository generation?
- CI-06: Does our retrieval representation actually cover the source code we claim to have indexed?

These are foundational questions that need credible answers before we invest much more in sophisticated behavioral reasoning.

And I would keep the entire exercise in the investigation phase for now. We have a valuable audit, but we should validate the findings and decide on the architectural contracts before creating implementation work.

My larger conclusion: the next phase of RAG-FOUNDRY-UNIVERSAL should emphasize trustworthy evidence contracts and demonstrable behavioral understanding—not additional architectural components.

## Part II — Astra's assessment and suggestions

### Overall response

I agree with the review's central argument and its recommendation to investigate
CI-01 and CI-06 early. It improves the distinction between investigation priority,
implementation urgency, and long-term product research. My original priority
table compressed those different decisions into one list.

There is less disagreement about CI-08 than the review suggests: the original
audit explicitly classified it as a missing capability and contract ambiguity,
not a defect in a correctly bounded structural subsystem. I would retain that
classification and make the separation more visible in future planning.

The most useful next output is a small set of investigated contracts with
counterexamples and acceptance criteria. Another broad review, a framework change,
or a large refactor would not establish those guarantees.

### Where I agree, and where I would qualify the review

| Finding | Response | Qualification or suggested next decision |
| --- | --- | --- |
| CI-01 | Highest-priority correctness investigation. | Bind the generation to a consistent database snapshot; returning a generation label alone is insufficient. Test the API/cache composition, not only the pure cache helper. |
| CI-02 | Narrow implementation defect; address promptly once acceptance behavior is defined. | Do not delay its inexpensive responsiveness test behind larger research. Offloading needs deadlines and bounded concurrency; cancellation of an async wrapper does not necessarily stop underlying blocking work. |
| CI-03 | High-priority correctness investigation. | An embedding-input fingerprint alone cannot attest stored passage text, source spans, metadata or generation membership. Define reuse separately for each derived product. |
| CI-04 | Preserve depth and basis incompleteness through the result. | “Satisfied” currently means the bounded mechanical contract was satisfied. Avoid interpreting the probe as proof that the API promises complete breakage prediction. |
| CI-05 | Coverage should be explicit and query-visible. | Successful parsing also does not prove complete language semantics. Include partial extraction and unsupported constructs, not only thrown exceptions. |
| CI-06 | Elevate investigation priority. | The local character-window gap is established; aggregate corpus loss and retrieval-quality impact are not. A chunk-size change is not yet a validated remedy. |
| CI-07 | Measure before selecting a new architecture. | One large repository is insufficient: graph degree, symbol count, source size, cache state and concurrency stress different allocations. |
| CI-08 | A product/design investigation. | Start with explicit question obligations and sufficient source evidence. Do not label general behavioral understanding as achieved merely because source statements reach the model. |
| CI-09 | Split payload accounting from maintainability. | Clarify/account for the full submitted payload early. Defer structural refactoring until stable contracts and non-regression evidence exist. |

### 1. Define reuse by product, not by one fingerprint

The review is right to move beyond file hashes. Its proposed effective-input hash
is useful for vectors, but insufficient for the complete reused artifact.

For example, two stored passages can have identical first 800 characters and
different tails. With the current truncation, their embedding input is identical;
the vector might legitimately be reusable while the stored passage must change.
Likewise, a path, source span or provenance classification can change without
changing the embedding input. Conversely, identical input text with a different
model revision is not the same embedding computation.

A contract investigation should distinguish:

| Derived product | Identity/equivalence to establish |
| --- | --- |
| Extracted artifact | Source snapshot, extraction configuration/version, exact artifact text and applicable structural/source-location metadata |
| Stored passage | Passage content, chunk boundaries/ordinal, source mapping and current metadata |
| Vector | Effective model input, preprocessing/truncation behavior, immutable model identity and relevant inference configuration |
| Reused record in a new generation | Verified content/representation equivalence plus refreshed generation membership and provenance |

These are candidate contract dimensions, not a prescribed database migration.
Compare a conservative transformation-version gate with finer-grained content
fingerprints. The former is simpler but can cause unnecessary re-embedding; the
latter can reduce cost but needs more computation and a careful derivation model.
Neither should silently reuse stale source text simply because a vector is reusable.

This follows the actual [reuse gate](/ingestion_service/src/api/v1/codebase_ingest.py#L354)
and [artifact retagging path](/ingestion_service/src/api/v1/codebase_ingest.py#L239)
identified by the original audit.

### 2. Keep representation coverage distinct from retrieval quality

The supplied CI-06 illustration is correct for the reported fixed-character
strategy: a stride of 900 with only 800 represented characters leaves interior
gaps. It is not a measured percentage of the entire repository, because different
artifact lengths select different strategies and overlapping parent/child artifacts
can represent some of the same text elsewhere. It is also not evidence that an
embedding model semantically captures every character it receives.

The first investigation should measure three separate outcomes on synthetic and
development inputs:

1. **Input coverage:** which source regions contribute to at least one effective
   embedding input, with a defensible source-to-input mapping.
2. **Discovery quality:** whether relevant artifacts/passages can be found for
   questions whose distinguishing evidence lies in omitted regions.
3. **Delivery quality:** whether the required exact statements survive passage
   selection and final context assembly after discovery.

Include long code regions, paragraph/sentence-selected artifacts, non-ASCII source,
and long queries. Record both stored passage text and actual adapter input. The
[chunker](/shared/chunkers/selector.py#L37) and
[embedder](/shared/embedders/ollama.py#L9) must be assessed together.

Do not change chunking or rebuild corpora merely to remove a visible arithmetic
gap. Compare alternatives against fixed development fixtures, and govern any later
evaluation through [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md).
Existing frozen E1 results or settings are not permission to tune on held-out cases.

### 3. Strengthen generation binding without silently expanding availability scope

I agree with the review's invariant, with one addition: the response's generation
must identify the snapshot from which **all** its nodes and relationships were
read. A generation field stamped before or after independent reads does not prove
this.

The investigation should cover a rebuild between generation lookup and export,
a rebuild between node and edge reads, concurrent cold-cache requests, an
unavailable generation, and the direct structural endpoints as well as RAG.
Valid outcomes are a consistently identified snapshot or an explicit retryable
failure. A cache should not turn transport failure or unavailable data into an
apparently authoritative empty graph.

Start with the [graph read](/ingestion_service/src/core/db_utils.py#L532),
[export](/ingestion_service/src/api/v1/graph.py#L149), and
[cache](/rag_orchestrator/src/retrieval/codebase_utils.py#L263).
Compare consistent snapshot reads and generation validation before choosing the
implementation. Preserve [ADR-050's accepted rebuild-unavailability scope](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)
unless the owner separately chooses staged publication. Consistent snapshots and
zero-downtime rebuilds are different requirements.

### 4. Define absence and incompleteness precisely

CI-05 and CI-04 should share vocabulary without collapsing their different causes.
An absent graph node can mean absent source, unsupported syntax, partial extraction,
failed extraction, unresolved identity, or exclusion by a query's scope. A missing
impact candidate can additionally result from depth, candidate or work limits.

Even a parser that returns successfully may not resolve dynamic dispatch or an
unsupported language construct. “Known absence” must therefore be qualified by
the analyzed snapshot, scope and analyzer capabilities. It is not a universal claim
about program behavior.

For IMPACT specifically, preserve separate facts about:

- the returned candidate set;
- whether the explored frontier was exhausted within the permitted semantics;
- which budget stopped further exploration;
- whether supporting bases for returned candidates are complete;
- what the static analysis cannot establish about runtime behavior or breakage.

The current [IMPACT assessor](/rag_orchestrator/src/retrieval/evidence_sufficiency.py#L203)
allows a bounded set to be mechanically satisfied. That can remain valid if scope
and completeness information survive. The narrow correction is to preserve those
facts, not redefine every bounded result as a failure.

### 5. Organize question contracts without inventing a mandatory four-step pipeline

The review's DISCOVER / ORIENT–TRACE / EXPLAIN / ASSESS IMPACT grouping is a useful
product lens. I would treat these as question families with shared evidence
requirements, not a maturity ladder or fixed execution order. ORIENT can read an
inventory directly; TRACE can begin from an exact symbol; neither necessarily needs
vector discovery. EXPLAIN may combine structural and source evidence.

Current IMPACT estimates candidates from one snapshot. Assessing an actual patch
may require two revisions, a diff and explicit assumptions about the change. A
hypothetical “what depends on this interface?” question does not always need two
revisions. Give these two kinds of impact assessment distinct contracts rather
than quietly expanding the meaning of the existing endpoint.

A design investigation could use this matrix:

| Question family | Minimum evidence to investigate | Honest limit to expose |
| --- | --- | --- |
| Discover a symbol or passage | Source snapshot, identity, source location, retrieval scope and extraction coverage | No match is not proof of absence when coverage or search is incomplete. |
| Orient or trace relationships | Generation-bound inventory/edges, resolution basis, traversal scope and limits | Static reachability and heuristics do not prove runtime execution. |
| Explain a bounded behavior | Exact source regions, relevant control/data/state dependencies and explicit obligations | Delivered statements do not alone establish a correct behavioral interpretation. |
| Assess hypothetical dependency impact | Relevant relationships, hypothesized change, candidate bases and uncertainty | Dependence does not imply breakage. |
| Assess a concrete revision change | Before/after identities, mapped changes, dependency/contract/test evidence | Static analysis and selected tests do not prove all runtime consequences. |

The common foundation could carry snapshot identity, source location, provenance,
derivation identity, coverage, and scope limits. What counts as sufficient should
remain specific to the question. This is a proposed contract model, not a request
for another service, orchestration framework or universal sufficiency score.

### 6. Revised investigation priorities

I would accept CI-01 and CI-06 as the first major investigations, while avoiding
a serial queue that postpones small correctness checks until research finishes.
CI-06 also informs CI-03: changing the embedding-input contract must have defined
reuse/invalidation behavior before any implementation or re-embedding.

| Work grouping | Proposed timing | Concrete output before implementation decisions |
| --- | --- | --- |
| CI-01 snapshot/export/cache identity | Start first | A stated invariant, interleaving reproductions and allowed failure behavior. |
| CI-06 embedding representation, linked to CI-03 | Start early | Coverage measurements, discovery hypotheses, transformation/reuse implications and comparison criteria. |
| CI-02 + CI-04 bounded structural correctness | Short investigations alongside the above | Reproducible responsiveness, depth-limit and basis-retention acceptance cases. |
| CI-03 + CI-05 derivation identity and coverage | Resolve before expanding reuse or making stronger absence claims | A per-product reuse contract and explicit extraction/query coverage semantics. |
| CI-09 payload accounting | Small early clarification | Precisely named evidence/context/prompt measurements and visibility of the full submitted payload. |
| CI-08 question-specific behavioral evidence | Separate design investigation | One bounded question family, required evidence, uncertainty and measurable acceptance. |
| CI-07 workload limits + CI-09 structural refactoring | Measurement-led follow-up | A workload matrix, observed bottlenecks and a justified intervention; no speculative rewrite. |

This separates **cost of investigation**, **risk of leaving a guarantee unresolved**,
and **dependency before a new capability**. A high-priority investigation does not
automatically justify a high-risk production change.

### Suggested next deliverable

Before opening implementation work, prepare short investigation records for CI-01
and CI-06. Each should state the invariant or question, current counterexample,
evidence limits, controlled fixtures, alternatives, trade-offs, acceptance criteria,
and a decision on whether implementation is justified. Keep CI-02/CI-04 acceptance
checks small and independently reviewable. These records are recommendations only;
they have not been created or approved by saving this response.

No changes are proposed to the frozen mechanism specification, preregistration or
held-out corpus as part of this review. The independent review's four/two/three
grouping is useful shorthand, but the categories overlap and are not nine newly
verified production defects.

My conclusion is that the review improves the audit's actionability. I would adopt
its emphasis on evidence contracts, elevate CI-06's investigation priority, retain
the existing architectural foundations, and make the product's claims of coverage,
consistency and sufficiency precise before pursuing broader behavioral intelligence.
