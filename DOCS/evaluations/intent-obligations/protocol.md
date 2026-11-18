---
title: "Intent recognition and answer obligations for Python repository questions"
date: 2026-11-18
type: evaluation
status: experimental
tags: [phase-6, routing, inventory, evaluation]
related:
  - "[Phase 6 architecture and restart checkpoint](phase-6-checkpoint.md)"
  - "[Experiment issue #398](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/398)"
  - "[Parent evaluation protocol](/DOCS/evaluations/evidence-aware-router/protocol.md)"
  - "[Dataset isolation and generalization](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Intent and answer obligations

Can a recognizer recover inventories the current regex misses while preserving the distinction between definitions, calls, imports and explanations? A compound request adds a second question. Even with the right intent, can the system satisfy every obligation in the answer?

## Design

The development set contains twelve labelled prototypes, five calibration questions and twenty-five questions in held-out phrasing families. Every row labels the set of intents, typed entity mentions, scope, required answer components, ordered proposed tools and expected authorized route under ordinary permissions. New cases distinguish callers from callees and include dependency impact, document comparison and summary. The CSV keeps each phrasing family in one split. These labels were authored during experiment design and are available to the scorer. They have not undergone independent human adjudication. The repository and questions have influenced development. [Cases](cases.csv) · [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)

| Arm | Input and decision |
| --- | --- |
| Regex | Applies both expressions from the current inventory recognizer. A matching question requests all definitions in the captured file. An unmatched question falls back to RAG. |
| Prototype embeddings | Embeds each prototype once with `mxbai-embed-large`. Embeds each query independently and uses the highest cosine similarity to select the prototype's intents, scope, obligations and strategy. A tie selects the first prototype in CSV order. |
| Constrained local LLM | Receives the question, fixed instruction and JSON schema. A single constrained generation predicts the entire frame, including typed entities and ordered tools. |
| Supplied labels | Sends the case labels directly through the same policy and executor. Correct recognition is given in this control, so remaining gaps expose execution or evidence limitations. |

The regex and prototype arms use a lexical extractor for filenames, documents and backtick-quoted symbols. The LLM predicts entities directly. Entity scoring compares type, spelling and mention order. It never borrows filenames from a prototype. The controller resolves exact paths or basenames against the same fixture for every arm. A request for both named files can use both. An ambiguous basename requires clarification, and an unmatched spelling yields a missing-file result.

Each prediction is replayed eight ways, including a one-read inventory budget. Explicit RAG selects RAG for every prediction. Investigation requires trace intent, caller authority, a material gap, a repair capable of addressing it and remaining investigation budget. The scenarios exercise all four conditions together and each condition absent. These evidence and permission states are supplied by the experiment. The classifier cannot set them. A recorded classifier outage or invalid output uses the regex fallback and records the reason. A missing capture remains unmeasured.

## Evidence obligations

`source_evidence` is a separate obligation only when the question asks for sources, citations, quotations or supporting passages. Callers, impact, comparison, summary and per-function explanation questions do not carry it by default. The rule applies to prototypes and held-out cases alike. The labels were corrected under this rule before any model capture. [Change log](label-changes.md)

## Tool strategy scoring

Each prediction records three views. Ordered `strategy_correct` compares the exact sequence in the CSV and is kept for continuity. `capabilities_correct` compares the set of tools and ignores order. `order_valid` checks only the hard dependencies: `source_navigation` before `ast_inventory`, `ast_inventory` before `filter_async`, `retrieve_sections` before `compare_versions`, `grounded_synthesis` last, and no repeated tool. Other orders, such as caller lookup before or after navigation, are arbitrary and are not penalized, so the CSV order for those tools is not a requirement. The inventory route requires the right tool set in a valid order. The summary adds `understood_capabilities_and_delivered_verifiable` beside the ordered joint score.

## Answer verification

The corpus pins the LF-normalized source of `codebase_ingest.py` from commit `061dda5` by SHA-256. Two small synthetic files, `api/ingest.py` and `cli/ingest.py`, cover ambiguous and multiple targets. The runner executes the merged #396 inventory policy against an in-memory source transport. The scorer compares every path, stored-text digest and qualified name, kind and span with a separate whole-module AST witness. The large module crosses the 500-line page boundary. [Witness](inventory-witness.json) · [Corpus adapter](/rag_orchestrator/experiments/intent_obligations/corpus.py)

The report distinguishes a demonstrated complete answer, partial evidence, unresolved work and unmeasured synthesis. A successful clarification can discharge an explicitly labelled clarification obligation. Asking for a missing filename leaves a requested inventory unresolved. The normal compound case initially earns credit only for discovery. RAG and investigation decisions alone earn zero demonstrated answer completions.

For separately captured downstream answers, pass `--judgments FILE`. Its JSON object maps a report row's `cell_sha256` to the captured `answer`, the independent `reviewer`, and a `supported` object mapping each satisfied obligation to the reviewer's source evidence and rationale. For an inventory answer, a reviewed definitions claim additionally needs `definition_rows` keyed by path, equal to the authoritative rows in scope. For a separate source-evidence claim in a compound inventory, supply reviewed per_function_citations keyed by path:start:name. Each citation identifies start and end lines within its function, quotes that exact source and appears as a path:start-end citation in the answer. For a compound explanation, supply `per_function_explanations` keyed by `path:start:name` with an actual answer excerpt for each function. The reviewer assesses grounding against the cited source. The scorer checks coverage, excerpts and cell identity. Preserve contradictions and omissions by withholding credit for the affected obligation.

## Run and inspect

From `rag_orchestrator`, use an interpreter with the orchestrator and test dependencies. On this Windows checkout the root virtual environment provides both. The default command runs offline. Choose a fresh output path to retain each run.

```powershell
$env:PYTHONPATH = '..'
..\.venv\Scripts\python.exe -m experiments.intent_obligations --output baseline.json
..\.venv\Scripts\python.exe -m pytest tests/test_intent_obligations.py -q
```

The JSON report contains individual decisions, executor evidence and scores. Counts are grouped by arm, split and scenario. Compare the same questions and scenario across arms. The denominator for missed inventory is the number of expected inventory or compound routes. For incorrect deterministic routes it is the number of selected inventory or compound routes. Report overall routing, extra clarification, unnecessary RAG, false investigation and demonstrated completion against all evaluated questions, alongside scheduled, missing and outage counts. A classifier outage is included in the effective system score.

Query timing and usage appear once per captured classifier request in `classifier_usage`. Embedding prototype requests are separate from query requests. Each scenario references the same underlying query capture. Local recognition time measures replay or regex processing. Capture latency includes the provider round trip. Record input/output tokens and monetary cost when available. Unknowns remain null. For embedding confidence, inspect the accepted and correct counts at the predeclared cosine cutoffs on calibration and held-out phrasing families. This runner does not apply a similarity cutoff to routing.

## Governed model comparison

The current development run covers the regex and supplied-label arms. To prepare a model run, export the exact requests. Set `$model` to the selected, installed local model tag, including its version. The request pack contains the prompts and schema. Model inputs exclude case labels, expected routes, hidden witnesses and scorer outputs.

```powershell
..\.venv\Scripts\python.exe -m experiments.intent_obligations --request-pack --llm-model $model --output requests.json
..\.venv\Scripts\python.exe -c "import json; from experiments.intent_obligations.recognition import digest; print(digest(json.load(open('requests.json', encoding='utf8'))))"
```

Freeze the named runtime commit, labelled cases, corpus and witness hashes, request-pack digest, model revisions, runtime settings, hardware, ordering, expenditure and scoring in the parent protocol's run manifest. Record independent owner approval for that exact manifest and models before live collection. The pack digest identifies requests within that manifest. Model selection and production adoption remain open. [Freeze and promotion gates](/DOCS/evaluations/evidence-aware-router/protocol.md)

For an approved run, set the digest variables from the approved manifest. The collector uses local Ollama on loopback, checks installed model digests before and after collection, and records failures and timing per request. It processes prototypes first, then one embedding and one LLM request per question in CSV order, with no warm-up. Freeze that order and record any model loading/cache effects when interpreting latency. An interrupted collection retains a partial journal. Preserve the journal as an incomplete attempt.

```powershell
..\.venv\Scripts\python.exe -m experiments.intent_obligations.collect --pack requests.json --approved-pack-sha256 $packDigest --llm-model $model --llm-digest $llmDigest --embed-digest $embedDigest --output captures.json
..\.venv\Scripts\python.exe -m experiments.intent_obligations --llm-model $model --captures captures.json --output comparison.json
```

## Comparison caveats

- **Prompting asymmetry.** The embedding arm sees twelve labelled prototypes. p09-p12 share intents with h18-h24 (callers, comparison, impact, summary), so the embedding arm is not fully held out on those questions. The LLM arm is zero-shot. Its single fixed instruction states the inventory, scope, obligation and tool-order rules but gives no examples and says nothing about callers, comparison or impact beyond the schema. The inventory and compound rules were written with these development labels in view. Read results as a development comparison of two setups, not a clean model-against-model comparison or evidence of generalization.
- **Entity resolution.** Entity scoring compares the typed mention exactly. Whether a file exists, or whether a basename is ambiguous, is decided by the controller against the fixture. h07 and h17 expect `clarify` because `ingest.py` matches two paths. h08 expects `missing` because `ingrst.py` matches none. A classifier cannot know either from the question alone, so those rows measure entity and plan accuracy, not route insight. The regex and embedding arms use a lexical extractor that finds `.py` and `.pdf` names and backticked symbols but not prose references.
- **CPU timing.** The host is an i7-8565U with integrated graphics and no GPU. Collection alternates embedding and generation calls with no warm-up, so Ollama may load and unload models between pairs. Latency therefore includes loading and switching and is not steady-state. A 60 s HTTP timeout can produce outages on this machine. They are scored as classifier outages with regex fallback and reported separately. Treat latency as an upper bound for this hardware, not a deployment estimate.

## Reading the expanded scorecard

Analysis precedes execution. The scorer compares intent sets, typed entities, obligation sets and ordered strategies independently with the case labels. A plan to retrieve two documents can receive strategy credit while the answer remains unmeasured. Scope and actual route have their own scores. The controller checks the proposed inventory tool sequence and its authority before dispatch.

Each required obligation records one of four outcomes: satisfied, unsatisfied, unsupported by available evidence, or blocked by resource limits. Source-evidence credit for a compound question requires reviewed support for each discovered function. The supplied-label control establishes which obligations this executor demonstrably fulfills in the same scenario. Among cases with at least one such obligation, report both delivery of all verifiable obligations and the stricter joint score requiring exact understanding, strategy and delivery. Full-answer completion still requires every requested obligation.

Keep prototype setup latency separate. For each classifier count one provider latency sample per measured question, include outages, report token usage and unknown costs, and compare identical question IDs. Keep development families separate from any future sealed generalization set.

## Original development result at 72a02c2

In the ordinary-permissions replay, the regex chose the expected route on 3 of 5 calibration questions and 8 of 17 held-out questions. Of the five held-out questions requiring executable inventory discovery, it missed four. It made zero incorrect deterministic selections. The inputs include both a direct phrasing the regex recognizes and a fronted phrasing it misses.

The supplied-label control chose the expected route on all 17 held-out questions. Six had demonstrated complete answers, including four inventories and two explicit clarification obligations. The compound answer remained partial after verified discovery. Four remained unresolved, and six required downstream synthesis that this run did not measure. For the large-file case, two reads and zero model calls recovered all 15 definitions. This development run made no model comparison or production routing change. [Raw capture index](/DOCS/test_results/raw-index.json)
