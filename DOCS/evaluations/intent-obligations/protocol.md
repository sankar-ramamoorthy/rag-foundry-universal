---
title: "Intent recognition and answer obligations for Python repository questions"
date: 2026-11-18
type: evaluation
status: experimental
tags: [phase-6, routing, inventory, evaluation]
related:
  - "[Experiment issue #398](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/398)"
  - "[Parent evaluation protocol](/DOCS/evaluations/evidence-aware-router/protocol.md)"
  - "[Dataset isolation and generalization](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Intent and answer obligations

Can a recognizer recover inventories the current regex misses while preserving the distinction between definitions, calls, imports and explanations? A compound request adds a second question. Even with the right intent, can the system satisfy every obligation in the answer?

## Design

The development set contains eight labelled prototypes, five calibration questions and seventeen questions in held-out phrasing families. Labels identify literal file mentions, intent, definition scope, required answer components and the expected route under ordinary permissions. The CSV keeps each phrasing family in one split. These labels were authored during experiment design and are available to the scorer. They have not undergone independent human adjudication. The repository and questions have influenced development. [Cases](cases.csv) · [ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)

| Arm | Input and decision |
| --- | --- |
| Regex | Applies both expressions from the current inventory recognizer. A matching question requests all definitions in the captured file. An unmatched question falls back to RAG. |
| Prototype embeddings | Embeds each prototype once with `mxbai-embed-large`. Embeds each query independently and uses the highest cosine similarity to select the prototype's intent, scope and obligations. A tie selects the first prototype in CSV order. |
| Constrained local LLM | Receives the question, fixed instruction and JSON schema. A single generation proposes intent, scope and obligations. |
| Supplied labels | Sends the case labels directly through the same policy and executor. Correct recognition is given in this control, so remaining gaps expose execution or evidence limitations. |

The two model arms use the same lexical extractor for Python file mentions. The extractor retains spelling and path order. It never borrows filenames from a prototype. The controller resolves exact paths or basenames against the same fixture for every arm. A request for both named files can use both. An ambiguous basename requires clarification, and an unmatched spelling yields a missing-file result.

Each prediction is replayed seven ways. Explicit RAG selects RAG for every prediction. Investigation requires trace intent, caller authority, a material gap, a repair capable of addressing it and remaining investigation budget. The scenarios exercise all four conditions together and each condition absent. These evidence and permission states are supplied by the experiment. The classifier cannot set them. A recorded classifier outage or invalid output uses the regex fallback and records the reason. A missing capture remains unmeasured.

## Answer verification

The corpus pins the LF-normalized source of `codebase_ingest.py` from commit `061dda5` by SHA-256. Two small synthetic files, `api/ingest.py` and `cli/ingest.py`, cover ambiguous and multiple targets. The runner executes the merged #396 inventory policy against an in-memory source transport. The scorer compares every path, stored-text digest and qualified name, kind and span with a separate whole-module AST witness. The large module crosses the 500-line page boundary. [Witness](inventory-witness.json) · [Corpus adapter](/rag_orchestrator/experiments/intent_obligations/corpus.py)

The report distinguishes a demonstrated complete answer, partial evidence, unresolved work and unmeasured synthesis. A successful clarification can discharge an explicitly labelled clarification obligation. Asking for a missing filename leaves a requested inventory unresolved. The normal compound case initially earns credit only for discovery. RAG and investigation decisions alone earn zero demonstrated answer completions.

For separately captured downstream answers, pass `--judgments FILE`. Its JSON object maps a report row's `cell_sha256` to the captured `answer`, the independent `reviewer`, and a `supported` object mapping each satisfied obligation to the reviewer's source evidence and rationale. For an inventory answer, a reviewed definitions claim additionally needs `definition_rows` keyed by path, equal to the authoritative rows in scope. For a compound explanation, supply `per_function_explanations` keyed by `path:start:name` with an actual answer excerpt for each function. The reviewer assesses grounding against the cited source. The scorer checks coverage, excerpts and cell identity. Preserve contradictions and omissions by withholding credit for the affected obligation.

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

## Development result

In the ordinary-permissions replay, the regex chose the expected route on 3 of 5 calibration questions and 8 of 17 held-out questions. Of the five held-out questions requiring executable inventory discovery, it missed four. It made zero incorrect deterministic selections. The inputs include both a direct phrasing the regex recognizes and a fronted phrasing it misses.

The supplied-label control chose the expected route on all 17 held-out questions. Six had demonstrated complete answers, including four inventories and two explicit clarification obligations. The compound answer remained partial after verified discovery. Four remained unresolved, and six required downstream synthesis that this run did not measure. For the large-file case, two reads and zero model calls recovered all 15 definitions. This development run made no model comparison or production routing change. [Raw capture index](/DOCS/test_results/raw-index.json)
