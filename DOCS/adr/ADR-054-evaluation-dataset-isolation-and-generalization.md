---
title: "ADR-054: Evaluation dataset isolation and generalization"
date: 2026-10-10
type: adr
status: accepted
tags: [evaluation, generalization, retrieval-quality]
related:
  - "[Issue #240 frozen evaluation](/DOCS/evaluations/2026-10-03-issue-240-frozen-overview-quality.md)"
  - "[Issue #240 production verification](/DOCS/test_results/2026-10-10-issue-240-per-request-controls-production-verification.md)"
  - "[Python coding agent live evaluation](/DOCS/test_results/2026-10-10-py-coding-agent-real-repo-verification.md)"
  - "[PR #248](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/248)"
  - "[PR #249](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/249)"
---

# Evaluation dataset isolation and generalization

**Status: Accepted.** This ADR establishes evaluation methodology for
future retrieval work; it does not authorize or prescribe a retrieval change.

## Context

Issue #240 passed 11/11 frozen checks on `rag-foundry-universal` in the
[production verification](/DOCS/test_results/2026-10-10-issue-240-per-request-controls-production-verification.md)
([PR #248](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/248)).
The separately re-ingested `py-coding-agent` then exposed source-selection,
authority, and cross-file reasoning failures in the
[live evaluation](/DOCS/test_results/2026-10-10-py-coding-agent-real-repo-verification.md)
([PR #249](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/249)).
Both repositories and their observed failures have now influenced our
diagnosis. Success on either cannot, by itself, establish generalization
to repositories the team has not used for development.

## Decision

1. Treat `rag-foundry-universal` and `py-coding-agent` as **development and
   diagnostic repositories**. Their questions can guide fixes and remain
   regression tests, but are not independent evidence of generalization.
2. Keep existing frozen suites, including #240's 11 cases, as **regression
   benchmarks**. Preserve their questions and scoring history; label their
   independence limit whenever reporting results.
3. Reserve previously unseen repositories for **held-out generalization
   tests**. Choose the repository and its source commit without using its
   evaluation answers to tune the candidate being tested.
4. Report three evidence classes separately: software correctness tests
   (contracts and invariants), retrieval-quality evaluations (evidence
   discovery, survival, citation, answer quality), and held-out
   generalization tests (the same quality checks on unseen repositories).
   A pass in one class does not substitute for another.
5. Before a held-out run, freeze the repository commit, ready generation,
   questions, expected authoritative evidence, scoring rules, runtime/model,
   retrieval settings, and context budget. Record the observed answers,
   source citations, and per-stage evidence traces against that contract.
   Keep candidate changes and any matched baseline on the same corpus
   generation when comparing them.
6. Once a held-out repository's results or source details influence
   development, reclassify that dataset as development/validation data.
   Obtain a fresh held-out repository and frozen protocol before making a
   subsequent generalization claim.

## Consequences

This policy makes quality claims more credible and keeps regression wins
useful without overstating them. It requires maintaining additional
repositories, versioned evaluation records, and clear dataset labels.
Results from a held-out run can still reveal defects and guide engineering;
they simply cannot remain independent after that use. Retrieval routing,
ranking, graph expansion, source authority, and model changes remain
separate design and implementation decisions supported by those diagnostics.
