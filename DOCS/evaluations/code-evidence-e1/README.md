---
title: "E1 frozen code-evidence regression cases"
date: 2026-10-14
type: evaluation-manifest
status: frozen-baseline-captured
tags: [evidence-coverage, regression, development-corpus]
related:
  - "[Accepted experiment decisions](/DOCS/evaluations/2026-10-14-code-evidence-experiment-decisions.md)"
  - "[Frozen manifest](/DOCS/evaluations/code-evidence-e1/manifest.json)"
  - "[Baseline capture record](/DOCS/test_results/2026-10-14-code-evidence-e1-baseline.md)"
  - "[Completed baseline results](/DOCS/test_results/2026-10-14-code-evidence-e1-results.md)"
---

# E1 frozen code-evidence regression cases

All six baseline cases are now captured: required-operation coverage is 6/26
and dependency expression coverage 6/20. The first prototype control replay
timed out on the full graph download; candidate quality remains unverified.

The manifest and its SHA-256 checksum were written before new baseline answers
were captured. Questions, expected expressions and persisted source bodies are
frozen. Both repositories are development/diagnostic corpora; these cases provide
cross-repository regressions, not held-out generalization evidence. No #243
repository was queried and no #254 agent-loop case was reopened.

| Case | Repository | Target and control-flow shape | Operations | Dependencies |
| --- | --- | --- | --- | --- |
| L1 | LightRAG | Exact `_build_query_context`; long function and helper budgets | 4 | 4 |
| L2 | LightRAG | Natural-language discovery of graph-context construction | 4 | 4 |
| L3 | LightRAG | `_apply_token_truncation`; independent entity/relation branches | 4 | 3 |
| F1 | RAG-FOUNDRY-UNIVERSAL | `assemble_context`; skip branch and byte-count helper | 4 | 3 |
| F2 | RAG-FOUNDRY-UNIVERSAL | `get_cached_graph_with_generation`; state, locks and LRU | 5 | 3 |
| F3 | RAG-FOUNDRY-UNIVERSAL | `run_rag`; long async pipeline and manifest/payload handoff | 5 | 3 |

Total: 26 operation obligations and 20 dependency obligations. The exact
questions, canonical IDs, document IDs, source text/hashes and generation pins
are in the manifest. Foundry source is commit
`109f12d83ab83a306318423be618c195f8c4e6ea`, generation
`60d5ed0a-a294-4276-890f-741d7cad5c41`. LightRAG source is commit
`4d0afc1bc36e6a34d4a5895b68efe9413748627a`, generation
`128c494e-0aae-4e1d-81d0-b7e52f2006b1`.

Comparison settings are model `ollama/Qwen3:4b`, Top K 20, five adapter chunks
per document, reranking off, overview controls off and a 4096-byte final cap.
The local orchestrator retains its existing 20-document expansion cap,
three-chunk fetch and 50-chunk global adapter cap. These implementation questions
are separate from the existing overview controls, whose original questions and
settings remain unchanged for the eventual adoption gate.

The scorer checks expressions against chunks labeled with the expected symbol
or its containing source file. It rejects identical expressions attributed to
tests or unrelated components. Automated expression coverage does not establish
branch coherence; dependencies and answers still require source-based review.
The source-line efficiency field is a source-membership proxy, not a semantic
relevance classification or a lower bound on useful implementation evidence.
The results distinguish it from exact expression bytes and citation overhead.

Reproduce baseline capture using the existing repository virtual environment:

```powershell
./.venv/Scripts/python.exe scripts/code_evidence_experiment.py baseline
```

The harness refuses to rewrite the frozen manifest, preserves completed baseline
captures, checks generation pins and records actual local generation payloads.
It uses unchanged local runtime code with remote HTTP services, not a deployment.
Source text in this manifest is exclusively an evaluation oracle; a future
selector must not consume it as if it were retrieved evidence.
