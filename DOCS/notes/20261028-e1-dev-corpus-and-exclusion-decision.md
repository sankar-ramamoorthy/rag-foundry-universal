---
title: "E1 development corpus: pin loss, answer-bearing documents and the decision"
date: 2026-10-28
type: decision
status: decided-implementation-tracked
tags: [e1, evaluation, corpus, contamination, exclusion, adr-054]
related:
  - "[Issue #290: the decision issue](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/290)"
  - "[Issue #291: path-level exclusion](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/291)"
  - "[Issue #292: clean F1-F3 corpus](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/292)"
  - "[E1 development cases](/DOCS/evaluations/code-evidence-e1/README.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Nightly re-ingestion decision (contamination warning)](/DOCS/notes/20260906-nightly-repo-ingestion-decision.md)"
---

# E1 development corpus: pin loss, answer-bearing documents and the decision

Roadmap phase: Phase 6, workstream E ([roadmap](/DOCS/audit/07-Roadmap.md)). Tracked by #290.

## What happened

On 2026-10-28 this repository was re-ingested through the web UI (the first attempt failed,
see #285-#287; the retry completed). A read-only check, recorded on #290, found:

- The generation pinned by the E1 development manifest for the F1-F3 cases (ingestion
  `60d5ed0a-a294-4276-890f-741d7cad5c41`, source commit `109f12d8`) **no longer exists**:
  its ingestion row and vectors are deleted. The current generation is
  `e423d1bb-e1d3-4d71-8200-3826c5987c95` at commit `8e063350`, a fresh ingestion with 10,973
  nodes.
- The stored text of the four foundry functions the cases target is **identical** to the
  manifest's sources (same SHA-256). The F1-F3 code did not change.
- The corpus now contains **answer-bearing documents**: 32 nodes under
  `DOCS/evaluations/code-evidence-e1/` (including the development manifest with its expected
  expressions) and 580 nodes under `DOCS/test_results/` (including the E1 results, the
  forensics, the feasibility reports and `baseline-audit.json`).
- LightRAG's pinned generation for L1-L3 is intact.

## Decision (repository owner, 2026-10-28)

> option 3 plus a clean corpus for F1-F3

Option 3 is excluding answer-bearing documents from the corpus. The clean corpus is a
dedicated corpus for the F1-F3 cases that never contained them.

### What it means (the interpretation recorded here; the owner can amend it)

1. **Standing rule.** No corpus used to evaluate a case may contain documents that state that
   case's expected evidence, its earlier results or its answers. This applies to the
   development cases and to the held-out set (whose repositories are separate, so their
   corpora cannot contain this repository's documents; the rule is about not creating the
   problem by other routes).
2. **Exclusion in this repository's own ingestion.** Answer-bearing paths are to be kept out
   of ingestion by a path-level exclusion that covers Markdown **and** non-Markdown files,
   recorded with the generation. Today no such mechanism exists (ingestion accepts only a
   source and an embedding provider; only hard-coded directory names are skipped), so this is
   implemented in #291. The front-matter directive of #241 is complementary and cannot cover
   JSON or checksum files. The files remain in git and readable by people; only ingestion
   skips them.
3. **A clean corpus for F1-F3.** The F1-F3 cases are evaluated on a separate corpus whose
   source is **the tree at commit `109f12d8`** (2026-10-12), published as that same commit
   object under its own repository identity. That tree contains no E1, held-out, oracle or
   feasibility files (the first E1 files were committed on 2026-10-21), so it reproduces the
   baseline's corpus without the answer keys. Created and verified in #292. The production
   repository stays as it is for ordinary use and is **not** used for F1-F3 runs.
4. **The 2026-10-14 F1-F3 baseline** is kept as historical evidence. It is comparable to new
   F1-F3 runs only to the extent the verification in #292 shows the clean corpus matches the
   original (commit, function texts, node count, embedder). This is a consequence of the
   decision rather than a separate choice, and is recorded so it can be corrected.

### Initial standing exclusion list for this repository (to be applied by #291; amendable)

- `DOCS/evaluations/code-evidence-e1/**`
- `DOCS/evaluations/code-evidence-held-out/**`
- `DOCS/test_results/code-evidence-e1/**`
- E1-related reports in `DOCS/test_results/`: `2026-10-13-lightrag-*`,
  `2026-10-14-code-evidence-e1-*`, `2026-10-21-e1-4096-byte-evidence-feasibility.md`,
  `2026-10-28-e1-structural-context-feasibility.md`

Any later artifact that records expected evidence or results for an evaluation case joins this
list when it is created.

## Read-only check recipe (used to verify #291 and #292)

For a repository id: nodes grouped by path prefix (the answer-bearing prefixes above must
return zero rows); the generation endpoint's `commit_sha`, `ingestion_id` and status; and, for
F1-F3, the SHA-256 of the stored text of the four foundry functions against the E1 manifest.
Run on request by the owner or an agent, read-only.

## Not decided here

The exclusion mechanism (request parameter or repository config) is left to #291. No F1-F3
control or candidate run happens before #292 is complete and a trustworthy matched control
exists (#270).
