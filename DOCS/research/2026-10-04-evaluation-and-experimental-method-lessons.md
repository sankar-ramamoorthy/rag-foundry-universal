---
title: "Evaluation and Experimental Method Lessons"
date: 2026-10-04
type: research-note
status: draft
scope:
  - evaluation
  - experiment-design
  - retrieval-quality
  - evidence-survival
  - repository-intelligence
  - document-intelligence
  - llm-evaluation
tags:
  - rag
  - evaluation
  - experiments
  - evidence
  - regression
  - benchmarking
  - research
related:
  - "[[2026-10-04-repository-intelligence-research-lessons]]"
  - "[[2026-10-04-document-intelligence-research-lessons]]"
  - "[[08-RAG-Quality-Evaluation-Methodology]]"
---

# Evaluation and Experimental Method Lessons

## Purpose

This note records cross-cutting evaluation and experimental-method lessons developed through independent ChatGPT analysis, controlled RAG experiments, production diagnostics, and external evaluation material.

It applies to both major intelligence tracks in RAG-FOUNDRY-UNIVERSAL:

- repository intelligence,
- document intelligence.

This is **not an implementation specification** and does not automatically create roadmap work.

Its purpose is to preserve how we learned to evaluate the system, especially as the project moved from simple end-to-end answer checking toward:

- pinned experimental baselines,
- stage-by-stage evidence tracing,
- claim-level error localization,
- controlled ablations,
- regression protection,
- and decision gates for adopting new techniques.

The central principle is:

> Evaluate the path from evidence to answer, not only the final answer.

---

# 1. Final-answer correctness is necessary but insufficient

The earliest natural evaluation question is:

```text
Did the model answer correctly?
```

That remains important, but it is too coarse to guide engineering.

A wrong answer can arise because:

- the source was not ingested,
- the correct chunk was not embedded,
- seed retrieval missed it,
- graph traversal failed,
- document selection dropped it,
- chunk fetch omitted it,
- context packing removed it,
- stale or lower-authority evidence displaced it,
- the model misread correct evidence,
- the model invented a fact not present in context.

Therefore:

```text
wrong answer
!=
retrieval failure
```

A useful evaluation framework must identify **where** the failure occurred.

---

# 2. Evaluate trajectories, not only outcomes

A strong external evaluation lesson was that complex AI systems should be evaluated across their **trajectory**, not merely on final output.

For RAG-FOUNDRY-UNIVERSAL, a repository-query trajectory can look like:

```text
question
  ↓
claim classification
  ↓
seed retrieval
  ↓
graph / structural expansion
  ↓
authority selection
  ↓
document / evidence selection
  ↓
passage fetch
  ↓
context assembly
  ↓
generation
  ↓
answer claims
```

A document trajectory may instead look like:

```text
upload
  ↓
parse / OCR / visual processing
  ↓
structured blocks
  ↓
chunking
  ↓
embedding
  ↓
retrieval
  ↓
context
  ↓
generation
```

The correct unit of evaluation is therefore often the **whole evidence trajectory**.

---

# 3. The system should expose evaluation checkpoints

A trajectory becomes useful only if intermediate state can be inspected.

Useful checkpoints include:

```text
source present?
indexed?
embedded?
seeded?
graph-discovered?
selected?
fetched?
final-context?
answer-used?
```

For repository intelligence, this may mean recording:

- canonical IDs,
- seed ranks,
- graph paths,
- mapped document IDs,
- chunk IDs / indices,
- context hashes,
- provenance,
- evidence roles,
- final context manifest.

For document intelligence, this may include:

- parser used,
- page number,
- OCR/vision provider,
- structured block identity,
- chunk lineage,
- page confidence,
- retrieval rank,
- final context membership.

## Lesson

Evaluation needs observability hooks in the product.

Without them, diagnosis degenerates into guessing.

---

# 4. Exact evidence survival is a first-class metric

A recurring project lesson was that a source appearing somewhere in retrieval is not enough.

The correct question is:

> Did the exact answer-bearing passage survive all the way into the generation payload?

This changed the evaluation model from:

```text
correct document retrieved?
```

to:

```text
exact required evidence survived?
```

That distinction is critical because:

```text
correct document
→ wrong chunks
→ wrong context
→ bad answer
```

is a retrieval failure even though the document itself appears in the source list.

---

# 5. Pin all moving parts before comparing results

A valid experiment requires stable inputs.

At minimum, serious evaluations should pin:

```text
runtime SHA
indexed source SHA
repository/document snapshot
generation or ingestion ID
model
embedding model
retrieval settings
context budget
prompt version
```

Without this, a comparison can accidentally mix:

- new source,
- stale corpus,
- old runtime,
- changed prompt,
- different model,
- different top-k.

That can make apparent regressions or improvements meaningless.

## Lesson

Snapshot identity is part of experimental validity.

---

# 6. Runtime, corpus, and source are separate identities

A particularly important repository lesson was that three revisions can differ:

```text
code being inspected
deployed runtime
ingested repository source
```

These must not be treated as equivalent.

Similarly, on the document side:

```text
uploaded file version
parser/model version
stored chunks
current runtime
```

may differ.

## Lesson

Every evaluation record should make these identities explicit.

---

# 7. Freeze the question set before changing the candidate

A useful experiment needs a stable benchmark.

The project increasingly adopted a pattern like:

```text
freeze questions
freeze expected evidence
freeze baseline
then modify candidate
```

This prevents "improvement" from becoming:

```text
change code
change questions
change interpretation
declare success
```

The benchmark should remain unchanged until the measured arm is complete.

---

# 8. Preserve failed experimental arms

A major methodological improvement during #240 was to avoid silently repairing a candidate mid-run.

The better pattern is:

```text
candidate v1
→ run
→ record result

candidate v2
→ explicit revision
→ rerun
```

Do not overwrite the failed arm.

## Why this matters

Preserving failed revisions gives:

- honest comparison,
- causal traceability,
- regression history,
- evidence for what actually changed.

This is especially important when a small presentation or aggregation fix materially changes scores.

---

# 9. Use explicit controls and counterfactuals

A good evaluation includes controls, not only the target question.

Examples:

### Historical-control case

If current-state authority filtering is added:

```text
current question
→ historical evidence should be suppressed

explicit historical question
→ historical evidence should remain retrievable
```

### Clean-context replay

If the final answer is wrong:

```text
same model
same question
only correct evidence
```

If the answer becomes correct, the likely problem is context competition rather than model incapacity.

### Forced retrieval

If graph traversal is suspected:

```text
normal seeds
vs
forced correct seed
```

This isolates seeding from traversal.

## Lesson

Counterfactuals are often more informative than another end-to-end rerun.

---

# 10. Separate retrieval, context, and generation experiments

One of the strongest project lessons is to avoid changing multiple layers at once.

For example:

```text
new embedder
+ new top_k
+ new reranker
+ new prompt
```

may improve an answer, but teaches almost nothing.

A better sequence is:

```text
baseline
→ one retrieval change
→ one context change
→ one generation change
```

## Lesson

Prefer single-variable or tightly bounded experiments.

---

# 11. Controlled ablation is often the fastest way to understand a failure

Useful ablations include:

```text
vector only
vs
vector + graph
```

```text
raw chunk
vs
structural-context prefix
```

```text
current authority policy
vs
claim-specific policy
```

```text
full context
vs
only answer-bearing evidence
```

```text
cap 20
vs
cap 40
```

The goal is not always to improve the score immediately.

The goal is to identify **which component contributes value or harm**.

---

# 12. A candidate should be evaluated on both correctness and evidence quality

Answer correctness alone can hide fragile behavior.

A model may produce the right answer using:

- stale evidence,
- wrong evidence,
- an unsupported guess,
- accidental memorization,
- contradictory context.

Therefore evaluation should distinguish:

```text
answer correct?
evidence complete?
evidence authoritative?
claim supported?
```

A correct answer with unsupported reasoning should not necessarily count as a full pass.

---

# 13. Claim-level evaluation is more useful than answer-level grading

Long answers can contain:

- correct claims,
- unsupported claims,
- incorrect aggregation,
- overgeneralization,
- invented values.

A single PASS/FAIL obscures this.

The #240 work reinforced the value of evaluating individual claims.

Example:

```text
"Six services"
→ count claim

"Each has pyproject.toml"
→ universal structural claim

"All communicate over HTTP"
→ architecture-edge claim
```

Each claim can be classified independently.

## Lesson

Where feasible, score:

```text
claim
→ required evidence
→ evidence present?
→ claim supported?
```

---

# 14. Unsupported universal claims deserve special scrutiny

LLMs frequently turn partial evidence into:

```text
all
each
none
every
always
```

These words imply complete enumeration.

A useful evaluation rule is:

> Universal claims require either complete inventory evidence or explicit bounded scope.

For example:

```text
"all services have tests"
```

should fail unless the inventory actually proves complete service coverage and test-directory presence.

---

# 15. Missing evidence must not become a negative fact

Evaluation should distinguish:

```text
not observed
not established
absent by complete enumeration
```

These are not interchangeable.

A model saying:

```text
"service X has no directory"
```

when the inventory merely omitted a directory field is an unsupported claim.

## Lesson

Tests should explicitly penalize absence inference when the evidence is incomplete.

---

# 16. Arithmetic and aggregation deserve deterministic checking

Some errors are not semantic ambiguity.

Examples include:

- 9 declarations reported as 9 distinct services,
- 5 Rust files reported as 4,
- duplicated entities counted twice,
- application services and databases merged into one count.

These should be checked mechanically where possible.

## Lesson

Use deterministic evaluators for deterministic facts.

Do not rely on an LLM judge to count rows that code can count exactly.

---

# 17. Prefer deterministic checks before LLM judges

A useful evaluation hierarchy is:

```text
exact assertion
→ deterministic parser/checker
→ domain-specific scorer
→ LLM judge
→ human review
```

Use an LLM judge only when the property itself is semantic.

Examples suitable for deterministic checking:

- file count,
- hash match,
- required source present,
- chunk survived context,
- port value,
- service name,
- answer contains forbidden unsupported claim.

Examples potentially suitable for LLM judging:

- explanation quality,
- relevance,
- clarity,
- nuanced completeness.

---

# 18. LLM judges should not become a second source of truth

LLM-as-judge can be useful, but it introduces:

- variance,
- model bias,
- hidden assumptions,
- possible disagreement with deterministic evidence.

Therefore:

> Use LLM judges to evaluate semantic quality, not facts that can be mechanically verified.

When used, the judge prompt and model should be versioned and pinned.

---

# 19. Human review remains valuable for ambiguous cases

Some failures are difficult to reduce to a scalar score.

Examples:

- misleading but technically true phrasing,
- partial architecture implication,
- overconfident wording,
- useful but incomplete answers,
- subtle authority mistakes.

Human review can still serve as the final arbiter for:

- benchmark design,
- edge-case adjudication,
- promotion decisions.

The goal is not to eliminate human judgment, but to reserve it for the places where it adds the most value.

---

# 20. Repeated runs matter when generation is stochastic

Even at low temperature, some models can vary.

A single failure may not represent stable behavior.

Useful practice:

```text
same question
same context
same model
repeat N times
```

This helps distinguish:

```text
systematic failure
vs
generation variance
```

Repeated runs are especially useful when testing prompt changes or noisy context effects.

---

# 21. Evaluation sets should include positive and negative controls

A mature benchmark should contain:

- cases expected to succeed,
- cases expected to refuse or say unknown,
- historical controls,
- current-state controls,
- distractor cases,
- near-duplicate cases,
- stale-document cases,
- exact-symbol cases,
- global-orientation cases.

## Lesson

A system that answers everything confidently can score well on easy questions while still being unsafe.

Refusal/uncertainty correctness matters.

---

# 22. Keep benchmark questions uncontaminated where possible

If evaluation answers or explanatory audit documents are included in the searchable corpus, they can accidentally answer the benchmark.

This is especially relevant in self-ingestion.

Possible contamination sources include:

- test-result documents,
- audit writeups,
- benchmark explanations,
- notes containing expected answers.

## Lesson

Known-answer evaluation should either:

- exclude such material,
- label it and test authority handling,
- or deliberately include it as a contamination stress test.

But the choice must be explicit.

---

# 23. Self-ingestion requires contamination-aware evaluation

Self-querying RAG-FOUNDRY-UNIVERSAL is valuable, but uniquely difficult because the corpus contains:

- historical notes,
- prior evaluations,
- architecture analysis,
- issue investigations,
- test fixtures,
- old descriptions.

Evaluation should therefore distinguish:

```text
cross-repo contamination
same-repo historical contamination
evaluation-answer contamination
```

These are separate phenomena.

---

# 24. Build regression tests from confirmed failures

Once a failure is localized and corrected, it should become a regression case.

Examples:

```text
exact passage lost after graph expansion
→ regression test

historical note overrides current implementation
→ regression test

Compose declarations counted as distinct services
→ regression test

missing package evidence converted to "No"
→ regression test
```

## Lesson

Evaluation should feed the test suite.

Otherwise the project repeatedly rediscovers the same bugs.

---

# 25. But do not overfit only to known failures

A benchmark can become too easy if every engineering change targets the same small set of frozen questions.

Therefore evaluation should eventually include:

```text
development set
holdout set
```

Potentially also:

```text
adversarial / challenge set
```

The development set can guide iteration.

The holdout set should be touched less often and used to detect overfitting.

---

# 26. Evaluation should be task-family aware

Different questions require different evidence and scoring.

Examples:

```text
purpose
structure
exact symbol
architecture
trace
impact
historical explanation
document fact lookup
table extraction
multi-page synthesis
```

One global accuracy number can hide major weaknesses.

## Lesson

Report results by task family.

---

# 27. Repository and document evaluations should share method but not benchmarks

The repository and document paths have different failure modes.

Repository examples:

- graph traversal,
- symbol resolution,
- authority,
- snapshot identity,
- structural inventory.

Document examples:

- parser quality,
- OCR,
- layout preservation,
- table structure,
- chunking,
- page provenance.

The experimental framework can be shared:

```text
pin
trace
compare
localize
regress
```

But the datasets and expected evidence should remain domain-specific.

---

# 28. Evaluation should distinguish mechanism quality from answer quality

A system can improve answer quality for the wrong reason.

For example:

```text
increase top_k
→ one benchmark improves
```

but:

```text
distractor rate rises
latency rises
other questions regress
```

Therefore each experiment should measure mechanism-specific outcomes.

Examples:

### Retrieval experiment

Measure:

- recall,
- MRR,
- exact passage survival,
- distractor ratio.

### Context experiment

Measure:

- answer-bearing coverage,
- competing-evidence share,
- token usage.

### Model experiment

Measure:

- correctness with fixed context,
- consistency,
- latency.

---

# 29. Latency and resource usage belong in quality evaluation

A technique that improves answer correctness but makes the system operationally unusable may not be an improvement.

Useful non-quality measurements include:

- latency,
- memory,
- VRAM,
- number of model calls,
- retrieval calls,
- token count,
- ingestion time,
- cost where applicable.

## Lesson

Evaluation should be multi-dimensional.

---

# 30. Every external technique should have a decision gate

External posts, papers, repositories, and benchmarks frequently suggest:

- rerankers,
- BM25,
- better embeddings,
- larger context,
- agents,
- decision models,
- graph databases,
- visual parsers,
- learned routing.

The mature evaluation rule is:

> Define the failure that would justify the technique before implementing it.

Examples:

### Reranker

Adopt when:

```text
correct evidence repeatedly appears below candidate cutoff
```

### Lexical retrieval

Adopt when:

```text
exact strings exist but vector retrieval repeatedly misses them
```

### Larger context

Adopt when:

```text
required evidence survives retrieval but repeatedly exceeds justified context budget
```

### Agentic follow-up

Adopt when:

```text
bounded deterministic evidence obligations repeatedly remain unsatisfied
```

### Visual document model

Adopt when:

```text
plain OCR/parser repeatedly destroys answer-bearing structure
```

This converts inspiration into testable engineering.

---

# 31. "GO / NO-GO / INVESTIGATE" is a useful experiment outcome

Not every experiment should end in implementation.

A useful decision vocabulary is:

```text
GO
→ measured benefit, acceptable regressions

NO-GO
→ no sufficient benefit or unacceptable regression

INVESTIGATE
→ evidence ambiguous; next targeted experiment identified
```

This is better than letting every experiment quietly become backlog work.

---

# 32. No PR should follow a failed quality gate

A strong discipline emerged during #240:

```text
implementation exists
tests pass
quality gate fails
→ no PR / merge / deploy
```

Passing unit tests is necessary but not sufficient.

A retrieval policy can be internally correct and still degrade answer quality.

## Lesson

Quality gates are part of release readiness.

---

# 33. Unit tests and evals serve different purposes

Unit tests answer:

```text
Does the code behave as implemented?
```

Evaluations answer:

```text
Does the system accomplish the intended task correctly?
```

Both are required.

A candidate can pass:

```text
298 unit tests
lint
type checks
```

and still fail its RAG quality gate.

That is not a contradiction.

---

# 34. Production verification should follow acceptance, not substitute for evaluation

A live production check is valuable for:

- deployment correctness,
- runtime revision,
- integration,
- real service behavior.

But production should not be the place where an unvalidated experimental policy is first discovered to regress.

Preferred sequence:

```text
local/controlled eval
  ↓
quality gate
  ↓
PR/CI
  ↓
deploy exact SHA
  ↓
production verification
```

---

# 35. Save raw evaluation artifacts, not only summaries

A final score report is not enough for later diagnosis.

Useful saved artifacts include:

- raw responses,
- selected evidence,
- context manifests,
- text hashes,
- trace IDs,
- scoring breakdown,
- runtime/source metadata,
- candidate version.

This allows later reviewers to reproduce or challenge conclusions.

---

# 36. Text hashes are valuable for proving matched evidence

The #240 experiments used exact text hashes to verify that retrieved chunks matched saved evaluation records.

This is a strong technique because it avoids vague statements like:

```text
"it looked like the same context"
```

and replaces them with:

```text
exact saved passage == exact live passage
```

## Lesson

Use content hashes where practical in reproducibility-critical evaluations.

---

# 37. Context size should be measured, not guessed

Prompt envelopes, retrieved evidence, system instructions, and context budgets can interact in unexpected ways.

A policy envelope can consume significant space even if it is outside the nominal retrieved-context budget.

Potential effects include:

- synthesis pressure,
- lower attention to evidence,
- truncation elsewhere,
- slower generation.

## Lesson

Measure actual payload composition before blaming or optimizing context size.

---

# 38. Avoid causal claims that exceed the experiment

A recurring good discipline was:

```text
7.6 KB policy envelope exists
→ possible synthesis pressure
```

not:

```text
7.6 KB envelope caused the failure
```

until a controlled test establishes that.

This distinction should be preserved in all experiment writeups.

---

# 39. Write experimental conclusions at the right level

Good conclusions look like:

```text
candidate improves canonical-purpose retrieval
but still produces unsupported architecture claims
therefore overall gate fails
```

Bad conclusions look like:

```text
authority selection is solved
```

when only one task family improved.

## Lesson

State exactly what the evidence establishes—and no more.

---

# 40. Failure localization should precede new implementation

When Q2–Q4 failed, the next step was not immediately:

```text
change retrieval again
```

Instead, the failures were localized separately as:

- incorrect aggregation,
- missing package-boundary evidence,
- generation despite sufficient evidence,
- edge-type conflation,
- ungrounded port invention.

This prevented unrelated fixes from being bundled together.

## Lesson

Before changing code:

```text
identify unsupported claim
→ identify missing or misused evidence
→ classify failure stage
→ design smallest next experiment
```

---

# 41. The smallest next experiment is usually the best next experiment

A useful experimental habit is to ask:

> What is the minimum change needed to distinguish between the competing hypotheses?

Examples:

- provide one typed fact table,
- isolate one question,
- replay one context,
- force one seed,
- remove one distractor,
- compare one cap,
- add one explicit package-marker field.

This yields more knowledge per change than broad rewrites.

---

# 42. Evaluation should preserve historical context without letting it dominate current facts

A good benchmark can intentionally test both:

```text
"What is true now?"
```

and:

```text
"What did the October investigation conclude?"
```

A strong system should answer each using the appropriate evidence.

This is not merely retrieval quality.

It is an **authority-sensitive evaluation problem**.

---

# 43. Evaluation itself should be versioned

As the project matures, the evaluation framework will change.

Useful versioned assets may include:

- benchmark set version,
- scoring rubric version,
- prompt version,
- judge model version,
- metric implementation version.

## Lesson

"Same score" is meaningful only if the evaluation procedure is also stable.

---

# 44. Recommended evaluation record template

A strong evaluation record should include:

```text
Purpose
Scope
Runtime SHA
Source / corpus SHA
Generation / ingestion ID
Model
Prompt version
Retriever settings
Context budget
Question set version
Candidate revision
Controls
Raw measurements
Claim-level findings
Failure localization
Decision
Next smallest experiment
```

This makes later comparison much easier.

---

# 45. Recommended experiment lifecycle

The accumulated lessons suggest this workflow:

```text
1. Observe failure
2. Define expected evidence
3. Pin environment and snapshots
4. Freeze question/control set
5. Capture baseline trajectory
6. Form one narrow hypothesis
7. Make one bounded change
8. Run candidate
9. Compare intermediate stages
10. Score final claims
11. Check regressions and controls
12. Decide GO / NO-GO / INVESTIGATE
13. Preserve artifacts
14. Promote confirmed failure to regression test
```

---

# 46. Shared evaluation architecture

A future evaluation harness could conceptually support:

```text
EvaluationCase
- question
- task_family
- expected_sources
- required_facts
- forbidden_claims
- allowed_uncertainty
- controls
```

and produce:

```text
EvaluationTrace
- seeds
- graph_paths
- selected_docs
- selected_chunks
- context_manifest
- parser/page provenance
- final_answer
- extracted_claims
- deterministic_checks
- semantic_scores
```

This is only a conceptual direction, not a committed implementation.

---

# 47. Recommended design principles

The accumulated evaluation work suggests the following principles.

1. **Evaluate trajectories, not only final answers.**
2. **Trace exact answer-bearing evidence through the pipeline.**
3. **Pin runtime, source, corpus, model, prompt, and settings.**
4. **Freeze evaluation cases before modifying a candidate.**
5. **Preserve failed experimental arms.**
6. **Use controls and counterfactuals.**
7. **Change one mechanism at a time where possible.**
8. **Prefer deterministic checks for deterministic facts.**
9. **Use LLM judges only for genuinely semantic properties.**
10. **Score claims, not only whole answers.**
11. **Treat universal claims as requiring complete evidence.**
12. **Distinguish unknown from absent.**
13. **Turn confirmed failures into regression tests.**
14. **Maintain holdout cases to reduce benchmark overfitting.**
15. **Report results by task family.**
16. **Measure latency/resource cost alongside quality.**
17. **Require explicit decision gates before adopting external techniques.**
18. **Do not merge or deploy candidates that fail their quality gate.**
19. **Save raw artifacts so conclusions remain auditable.**
20. **State only what the experiment actually proved.**
21. **Prefer the smallest experiment that discriminates between hypotheses.**

---

# 48. Relationship to the two intelligence tracks

This document is intentionally cross-cutting.

## Repository intelligence asks:

```text
Did the correct repository evidence survive?
Was the source authoritative for this claim?
Was the typed fact derived correctly?
```

## Document intelligence asks:

```text
Was the page parsed correctly?
Was structure preserved?
Did the correct chunk survive retrieval?
```

Both ultimately use the same experimental discipline:

```text
pin
trace
compare
localize
regress
```

That shared discipline should become part of the project’s identity.

---

# 49. Roadmap implications

Evaluation should no longer appear only as a final testing phase.

It is a capability that supports every roadmap track.

A future roadmap should therefore treat evaluation infrastructure as a horizontal layer:

```text
Repository Intelligence
        │
Document Intelligence
        │
Shared Retrieval / Model Infrastructure
        │
        └──────────────┐
                       ▼
          Evaluation / Experiment Harness
                       │
           - pinned snapshots
           - trajectory traces
           - claim checks
           - controls
           - regression suites
           - holdouts
           - release quality gates
```

This is not merely QA.

It is how the project decides what to build.

---

# 50. Status of this note

This document intentionally contains a mixture of:

- lessons already supported by project evidence,
- evaluation practices that have proven useful,
- and future framework ideas.

It is **research input**, not a specification.

Before new evaluation infrastructure becomes roadmap work, it should itself follow the same evidence-first discipline described here.

The key lesson is:

> RAG-FOUNDRY-UNIVERSAL should not adopt techniques because they are fashionable, nor reject them because they are complex. It should make changes when controlled evaluation shows exactly where the current system fails and exactly what the proposed change improves.
