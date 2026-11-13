---
title: "Evidence planning, context capacity, and multi-pass processing"
date: 2026-11-12
created: 2026-11-12
type: note
status: proposed
summary: "Working discussion capture and restart point; experiments and architecture choices remain undecided"
tags: [code-intelligence, evidence-assessment, query-understanding, context-budget, multipass, brainstorm]
authority: "Owner discussion and assistant responses; not accepted requirements, an ADR, or execution authorization"
verification_status: "Prior retrieval measurements linked; context defaults inspected locally; new generation and multi-pass experiments not run"
related:
  - "[Strategy discussion index](./00-Strategy-Discussion-Index.md)"
  - "[Measured retrieval diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md)"
  - "[Earlier investigation-loop hypothesis](./03-Evidence-Driven-Investigation-Loop.md)"
  - "[Earlier model experiments](./05-Models-Embeddings-and-Reranking.md)"
---

# Evidence planning, context capacity, and multi-pass processing

## Trigger

After the retrieval diagnostics, the owner continued exploring what the system
needs to do. The owner explicitly said they were still ruminating and should
not be assumed to have understood or accepted every assistant conclusion.
This note preserves that exploratory state before conversation context is lost.

The immediate objective remains improving this system's retrieval, navigation
and delivery of implementation evidence using the known self-repository and
LightRAG failures. Coding-agent utility remains a broader product priority,
but is not a prerequisite for diagnosing these engineering failures.

The sequence of discussion was: evidence requirements and assessment; whether
4,096 bytes is too restrictive; larger context versus serial/independent
evidence processing; whether existing local inference hardware can support a
useful experiment. No new architectural principle was formally adopted.

## Raw input: selected discussion excerpts

The following excerpts preserve the user's wording from the supplied discussion;
the sections below organize the remaining ideas and assistant qualifications.

> RAG-FOUNDRY-UNIVERSAL needs to understand what evidence a question requires,
> select an appropriate retrieval approach, and assess whether the evidence it
> found actually satisfies the question.

> These are three distinct responsibilities, and we shouldn't assume all three
> require an LLM.

> I would start by investigating query understanding and evidence assessment,
> not by building a general-purpose agent loop.

> A repository question should drive an evidence-gathering process, not merely
> a similarity search. Retrieval should stop when the required evidence is
> adequately supported, or when it can explain precisely why it cannot obtain
> that evidence.

> First demonstrate that we can find and deliver sufficient evidence using the
> capabilities we already have. Then automate the decisions. Finally, add
> adaptive investigation where a fixed plan genuinely falls short.

The owner then asked whether the 4,096-byte budget was a major restriction and
supplied an additional discussion of larger prompts, serial evidence processing,
parallel extraction/consolidation, and local versus cloud inference.

## Observations: three responsibilities

1. **Query understanding:** identify the subject and what would constitute a
   supported answer. An `implementation` label alone is insufficient.
2. **Retrieval planning and execution:** choose discovery methods, artifact
   preferences, source reads and graph relationships appropriate to those needs.
3. **Evidence assessment:** identify supported relationships and remaining gaps,
   including evidence lost during selection.

A loop connects assessment to another action when a specific actionable gap
remains. Many actions can be deterministic. Model-directed adaptation becomes
interesting when a discovery changes what needs investigating, such as dispatch
through a configuration-selected implementation.

| Question | Evidence obligations | Candidate starting action |
| --- | --- | --- |
| Trace `POST /v1/rag` | Correct handler, internal transitions, vector retrieval, transport boundary | Resolve verb/path through route graph |
| Trace LightRAG query processing | API handler, receiver identity, dispatch and retrieval calls | Locate API module, inspect definitions and calls |
| What happens during ingestion? | Entry point, processing stages, completion/failure transitions | Locate subsystem and navigate its implementation |

An illustrative requirement record could contain intent, subject, repository
scope, required evidence, preferred artifacts and secondary artifacts. This is
not a proposed production schema. Likely stages suggested by a model are
hypotheses to investigate, not facts about the repository.

### Distinguish requirements from discoveries

The question can require a handler and a supported path to vector retrieval.
Function names such as `run_rag` and `hybrid_retrieve` should normally emerge
from source inspection. Supplying their names manually is useful for an oracle
experiment, but tests delivery of known evidence rather than autonomous discovery.

Finding a symbol, retrieving its body, and verifying a transition involving it
are different achievements. A useful execution-trace witness includes caller,
target, source location, supporting excerpt, relevant conditions and unresolved
bindings. A graph edge may identify a candidate; a source excerpt may verify a
call expression without resolving the receiver's runtime identity.

Assessment should distinguish:

- Necessary evidence was located.
- Retrieved source supports the required relationship under stated conditions.
- That supporting source survives into the actual generation prompt.

If evidence is found but discarded, the next action may be better allocation,
deduplication or excerpt selection. Another search is not automatically useful.
Adequacy is relative to the requested scope: a supported static trace does not
prove every possible runtime execution.

## Observations: the context restriction is material

The [measured diagnostics](/DOCS/test_results/2026-11-12-retrieval-mechanism-diagnostics.md)
show that the captured LightRAG final contexts contained about 3,650-3,730 source
characters. The 4,096 allowance is enforced as UTF-8 bytes, including labels and
separators, despite token-oriented field names. A reproduction-script passage
consumed 1,936 bytes, approximately 47% of the allowance.

For a trace spanning a handler, service function, dispatch condition, retrieval
operation and HTTP boundary, this is a substantial capacity constraint.
Capacity and allocation interact: a larger allowance can admit useful evidence,
but may also admit more irrelevant material. Neither fixes undiscovered source
or unresolved graph relationships.

The proposed capacity-only comparison holds fetched passages and their ordering
fixed while varying the byte cap. A separate comparison changes selection while
holding the cap fixed. Required evidence survival and answer correctness should
be measured separately.

### Three different limits must be checked

| Limit | What it controls | What is known here |
| --- | --- | --- |
| Orchestrator evidence allowance | What source reaches generation | Captures demonstrate a 4,096-byte cap |
| Inference runtime context allocation | Tokens available to the loaded model | Effective deployed allocation not verified in this discussion |
| Model capability and hardware capacity | Supported sequence length and practical memory/latency | Published model specification is not a measurement of this deployment |

At local checkout `b24d093d3679cc964dbf61695a646a9cadebfe0e`,
[orchestrator defaults](/rag_orchestrator/src/core/config.py) specify 8,192 for
`CONTEXT_WINDOW_TOKENS`, 1,024 for `PROMPT_RESERVE_TOKENS`, and 2,048 for
`OUTPUT_RESERVE_TOKENS`. [The service](/rag_orchestrator/src/core/service.py)
computes the evidence cap as the minimum of the requested allowance and the
remaining allowance after those reserves and the query estimate. Under current
byte accounting, raising the request allowance alone therefore still leaves
roughly 5 KB or less with these defaults. Local defaults are not proof of
effective production values.

Any experiment must measure actual model tokens as well as bytes, including
question, instructions, chat template, carried records and output allowance.
Changing the numerical evidence cap alone does not establish a correctly
configured model context.

## Ideas: larger context versus multi-pass evidence processing

| Approach | Operation | Potential benefit | Main concern |
| --- | --- | --- | --- |
| Larger single prompt | All reviewed source available together | Direct reasoning across conditions and relationships; simplest control | Model may overlook evidence or lack practical context capacity |
| Serial passes | Each source package plus compact findings from preceding passes | Later evidence can resolve earlier uncertainty | Early mistakes propagate; carried records grow |
| Independent extraction and consolidation | Separate packages produce witnesses; final pass combines them | Focused local tasks may be easier for the model | Cross-package conditions and connections can be lost |
| Deterministic extraction where feasible | Parse explicit relationships; use model interpretation selectively | Fewer model calls and inspectable extraction | A call expression alone does not establish receiver identity or runtime behavior |

The owner's supplied discussion tentatively favored a hybrid: independent
processing for independent packages, sequential investigation for newly
discovered relationships, and consolidation through a shared evidence ledger.
The assistant's recommendation was to retain that as a candidate and test a
larger single prompt first. Neither position is an accepted design.

Example packages for the endpoint trace were API, orchestration and vector
transport. Package construction is itself a decision: a condition in one package
may govern a call in another. Arbitrary byte boundaries can split necessary
context; variable-sized coherent packages may be preferable.

### Preserve witnesses rather than only summaries

A record labeled `source_supported` remains an assertion unless its source
witness is available. Preserve source identity/range, the relevant excerpt,
conditions, uncertainty and unresolved bindings. The final synthesis should
receive enough original source to check critical transitions. A citation alone
does not repair a distorted summary.

Serial processing only remains bounded if old source is deliberately replaced
by a compact record. A 4 KB new package plus an accumulated ledger is more than
4 KB of input. The final consolidation pass also needs a declared context cap;
otherwise the original capacity problem merely moves to the last stage.

Independent processing does not require simultaneous GPU execution. Initially
run independent extraction calls sequentially if needed, to separate reasoning
quality from scheduling/concurrency. Parallel requests may compete for the same
GPU and need not reduce wall time.

## Ideas: smallest controlled experiment and possible extensions

Start with the failed self-repository endpoint trace and manually stated evidence
obligations. Resolve the route, locate implementing functions, obtain original
source, verify required transitions, assemble evidence and ask the existing
Qwen3:4b model the original question.

Separate two questions:

1. **Evidence/model ceiling:** can manually reviewed sufficient source, within
   a declared allowance, support a correct answer from the existing model?
2. **Infrastructure capability:** can existing retrieval interfaces obtain and
   assemble those same witnesses? Record every manual intervention or unavailable
   operation. Direct database source reads do not prove the query API can do it.

Suggested sequence, still proposed:

1. Establish a reviewed sufficient source set. Let its contents determine its
   size rather than forcing an arbitrary 12 KB target.
2. Compare the existing truncated version against that complete set in one
   prompt, verifying that the complete prompt fits the runtime allocation.
3. If complete evidence still yields errors, compare staged extraction and
   consolidation using the same evidence. Multi-pass remains worth testing
   later for larger tasks even if this short trace succeeds in one pass.
4. Identify which relationship or condition is lost at each stage.
5. Automate plan creation and gap detection only after the manual path works;
   add adaptation where a fixed plan demonstrably falls short.

The owner's proposed expanded experiment matrix was one 12 KB prompt, serial
processing of three 4 KB packages, independent processing plus consolidation,
and deterministic extraction with selective model interpretation. Keep a
separate 4 KB single-shot control. These sizes are illustrative, not a frozen
protocol; distinguish 4,096 bytes from decimal KB when fixing exact limits.

Hold source generation, original question, model, sampling/thinking settings
and rubric fixed. Measure correctness, transition coverage, unsupported claims,
evidence lost between passes, total input/output tokens, latency and memory.
The same source input does not imply equal compute: repeated instructions,
intermediate outputs and consolidation incur additional inference. Report this
cost rather than attributing every gain to decomposition alone.

## Hardware and cloud discussion: claims and limits

The supplied discussion describes a GTX 1080 Ti with 11 GB VRAM running Qwen3:4b
through Ollama. GPU inventory, quantization, active allocation, concurrent load
and offloading were not independently measured during this follow-up.

The [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B), checked during
the discussion, lists a native 32,768-token context.
[Ollama's context documentation](https://docs.ollama.com/context-length)
describes separately configurable allocation, increased memory demand at larger
contexts, and inspection with `ollama ps`. These do not guarantee that the
advertised maximum fits the owner's running configuration.

A local experiment with approximately 12 KB of source was considered plausible,
not demonstrated. Character-to-token estimates in the supplied discussion are
illustrative; source code and identifiers vary. A successful large-context run
must also confirm that evidence was not silently omitted or truncated.

Suggested operator checks were `nvidia-smi`, `ollama ps`, and
`ollama show <installed-model-tag> --modelfile`, plus effective `num_ctx`, any
`OLLAMA_CONTEXT_LENGTH`, and application-side limits. The commands were not
executed on the Linux host during this discussion. Model-file settings alone
may not reveal every runtime/request override.

The supplied text also suggested RunPod for a later stronger-model comparison,
keeping ingestion/storage/retrieval on the existing host. It included GPU rental
prices and estimated costs; those prices were not verified or adopted here.
No GPU rental, cloud migration or model switch was authorized. First determine
whether the current model succeeds with correctly delivered evidence. A later
model comparison should keep evidence identical so model changes are not
confounded with retrieval improvements.

## Questions, concerns and restart point

- How much reviewed source actually suffices for the endpoint trace?
- Does the larger source set fit the effective deployed model allocation with
  question, instructions and output space included?
- Can current interfaces retrieve original witnesses, or do manual source reads
  conceal an infrastructure gap?
- Does selection lose evidence even after candidate discovery succeeds?
- Does Qwen fail with complete evidence, and if so, which transitions or conditions?
- Does staged processing preserve those details better, or simply spend more
  inference on the task?
- Which witnesses can be extracted deterministically, and which require
  disambiguation or model interpretation?

**Resume here:** agree on the narrow endpoint-trace experiment and its evidence
requirements; verify the three context limits; preserve the same source snapshot;
then compare complete versus constrained evidence before selecting a multi-pass
design. These discussions have not yet been turned into an approved execution
protocol.

Governance remains investigation first, explicit decisions second, GitHub issues
and milestones before implementation. Saving this note authorizes none of the
proposed configuration changes, harness implementation, generation experiments,
deployment changes or cloud expenditure. The owner is still exploring the ideas.
