---
title: "E1 isolated prototype contract"
date: 2026-10-14
type: experiment-contract
status: frozen-before-prototype-results
tags: [local, ablation, evidence-selection]
related:
  - "[E1 cases](/DOCS/evaluations/code-evidence-e1/README.md)"
  - "[Accepted decisions](/DOCS/evaluations/2026-10-14-code-evidence-experiment-decisions.md)"
---

# E1 isolated prototype contract

The six live-service baseline answers are captured before prototype execution.
Each prototype below is one local candidate, not an adopted policy. Do not tune
its parameters against the results from these cases in this experimental round.
Neither selectors nor their ranking functions may consume witness ranges or the
manifest's source bodies. The manifest is used only to score outputs.

First observe unchanged local retrieval again with the original query embeddings
and cached vector-service responses. Capture the pre-budget candidate pool and
per-document passages. Reuse a baseline answer only if query and context exactly
match its original generation request. Record any unmatched replay separately;
never report a reused answer as a new model run. Compare each candidate with its
own unchanged replay control, reporting control drift from the original baseline.

1. Discovery-only: re-order already discovered code symbols by literal symbol
   match, then query-token overlap with the terminal symbol, then original rank.
   Other artifacts retain zero symbol score. Keep seeds, the 20-document cap,
   passage fetching, adapter and assembly unchanged. This tests moving lexical
   implementation relevance ahead of the existing relation ordering. Success is
   target survival in all six cases without loss of discovery or budget compliance.
2. Passage-only: preserve the control's selected document set and order. Select
   at most three existing code-symbol documents using the same literal/lexical
   relevance score. Fetch at most 24 source-ordered chunks for each through the
   existing scoped search-by-document endpoint, without a query vector. Choose
   one contiguous window of at most five original chunks per document, scored
   by query-token overlap on operation-bearing lines, then operation-line count,
   then earliest source ordinal. Retain individual original chunk identities;
   do not invent code, repair indentation or pack chunks to evade adapter caps.
   The 24-chunk allowance is a bounded targeted-fetch treatment, not a global
   configuration change: at most three additional requests/72 returned records.
   Report returned bytes and latency. The existing five-chunk per-document,
   50-chunk global adapter limits, document cap and 4096-byte final cap remain.
3. Allocation-only: use exactly the unchanged replay's post-adapter candidate
   pool. Prefer current implementation symbol passages, then current file-level
   implementation, tests/examples, current documentation and archived documents.
   Within a class use literal/lexical symbol relevance, then original order.
   Remove normalized exact duplicates within a source file. Use unchanged whole-
   passage assembly, citation labels and the 4096-byte cap. No new fetching,
   source rewriting, clipping or model/prompt changes.

Passage and allocation candidates must satisfy every frozen operation and
dependency on all cases before they can form an adoption candidate. Expression
coverage alone does not establish source/control-flow coherence; review it
against the frozen source. Contiguous stored chunks are only a conservative
coverage candidate, not proof of branch completeness or original indentation.

Capture prototype generation payloads locally but do not submit them to the
model until evidence gates pass. These are planned payloads, not evidence proven
delivered to a model. Score model reasoning only on actual generation requests.
If no complete evidence candidate passes, do not combine failed mechanisms or
run an adoption/control suite as if a viable production candidate exists.
Preserve overview and explicit-code controls for the eventual adoption gate.
