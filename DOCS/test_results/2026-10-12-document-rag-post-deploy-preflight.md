---
title: "D0 post-deployment preflight: repository fixtures are not document uploads"
date: 2026-10-12
type: test-result
status: blocked-awaiting-isolated-document-stack
tags: [document-rag, d0, preflight, corpus-isolation]
related:
  - "[Frozen baseline protocol](/DOCS/evaluations/2026-10-12-document-rag-baseline.md)"
  - "[Raw preflight](/DOCS/test_results/2026-10-12-document-rag-post-deploy-preflight.json)"
  - "[Current status](/DOCS/status.md)"
---

# D0 post-deployment preflight

The twelve-question baseline has **not run**. All four frozen fixture files are
indexed, but their sixteen root-document chunks are tagged `source_type: code`.
The unchanged document pipeline excludes that source type. Repository
re-ingestion therefore does not satisfy the document-upload prerequisite.

The [read-only preflight runner](/scripts/document_rag_preflight.py) verifies
runtime versions, ready generation, local manifest hashes, exact pinned Git
source bytes, root artifact identities and stored chunks. It checks versions and
generation again afterward, failing on drift. It performs no ingestion, retagging,
deployment, query-answer generation or database access outside service APIs.

| Check | Observation |
| --- | --- |
| Four service versions | `109f12d83ab83a306318423be618c195f8c4e6ea`, release `prod-2026-10-12-1731pm` |
| Repository source | Same `109f12d` commit |
| Generation | `60d5ed0a-a294-4276-890f-741d7cad5c41`, ready |
| Frozen original document bytes | All four hashes match pinned Git source |
| Fixture root artifacts / stored chunks | 4 / 16 |
| Chunks passing `source_type != code` | **0 / 16** |
| Baseline answer requests | **0 / 12** |

Repository Markdown and uploaded Markdown use different ingestion paths. This
preflight establishes an eligibility/setup blocker, not a retrieval regression,
parser quality failure or failed answer score. It does not inventory every
descendant artifact or claim an end-to-end document baseline from repository
chunks. The production corpus also contains other data, and the simple-query
route does not forward a corpus filter. Local Docker remains unavailable.

The next prerequisite is an isolated document test stack with the four frozen
files uploaded through its document-ingestion endpoint. Reuse of the existing
LLM endpoint is compatible with data isolation; ingestion/vector data must remain
separate from production. Confirm terminal ingestion status, extracted sections,
table structure and frozen corpus identity before the twelve answer requests.
Keep the frozen questions, scoring, source-type filter and budget unchanged.
Do not reinterpret repository ingestion as uploaded-document validation or
remove the exclusion to make these fixtures eligible.

Decision: **INVESTIGATE test setup; baseline execution blocked.** No quality
gate is passed, no production fix is proposed, and PDF/OCR/MCP work remains
behind the Markdown gate. #254 and #243 remain deferred. Ruff and Pyright check
the local preflight helper; those checks do not establish document answer quality.
