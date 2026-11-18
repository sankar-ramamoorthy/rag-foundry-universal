---
title: "Ordinary RAG byte-budget comparison"
date: 2026-11-17
type: test-result
status: complete
related:
  - "[Capacity configuration](/DOCS/deployment/rag-evidence-budgets.md)"
  - "[Historical local inference](/DOCS/test_results/2026-11-12-345-round2.md)"
---

# Phase 6 offline comparison, issue #386

From `rag_orchestrator/`, run `python ../scripts/compare_rag_context_386.py`
in the service environment. The input is the frozen docs-first #345 development
fixture at revision `908d82b`, with four documentation passages followed by
nine reviewed implementation passages. The discovery-miss control removes
those nine before selection. Order and text are fixed within each comparison.

| Evidence ceiling (bytes) | Mixed delivered bytes | Implementation delivered / available | Discovery-miss delivered / available |
| ---: | ---: | ---: | ---: |
| 2048 | 1698 | 0 / 9 | 0 / 0 |
| 4096 | 3950 | 0 / 9 | 0 / 0 |
| 8192 | 7828 | 2 / 9 | 0 / 0 |

The larger allowance delivered two additional implementation passages on
this fixture. The test exercises the assembler at fixed effective ceilings.
It measures neither live discovery nor answer quality.

The historical November 12 experiment observed Qwen3:4b digest prefix
`359d7dd4` on the GTX 1080 Ti. Requests explicitly setting 16,384 returned
that same runner context length and 4.75 GiB VRAM. Under the same captured
documentation-only prompt, increasing the window from 4096 to 16384 still
yielded insufficient answers at both seeds. An implementation-only context
produced different answers. Those runs changed different variables than this
byte-budget comparison. Current runner state, answer correctness, unsupported
claims, prompt tokens, latency and memory for the three new arms are unmeasured.
Auto continues to select its compatibility ceiling.

**Boundary check.** Ordinary RAG runs hybrid discovery, applies chunk and byte
limits, and forwards the assembled text. For overview requests it may prepend
policy material before generation. The LLM service adds its system and user
messages and transforms them per provider attempt. Simple RAG uses the shared
assembler with its existing 2048 default and an independent generation path.
