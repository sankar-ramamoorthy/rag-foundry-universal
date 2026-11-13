---
title: "Codebase Metadata, Retrieval Constraints, and Evidence Authority"
date: 2026-11-12
type: technical-analysis
status: raw
project: RAG-FOUNDRY-UNIVERSAL
tags: [metadata, source-type, doc-type, provenance, retrieval-filter, source-authority]
aliases: ["Why Code-Only Filtering Includes Documentation"]
authority: "Source-inspection and query-result reports; runtime behavior needs confirmation for each deployed generation"
related: ["[[01-Evidence-and-Failure-Analysis]]", "[[02-Retrieval-Strategies-and-Planning]]", "[[08-Experiments-Gates-and-Open-Decisions]]"]
---
# Metadata, Constraints, and Authority

## The owner's key question

**When we ingest a repository, do we distinguish code from documentation, and does retrieval actually honor that distinction?**

Based on Claude's local read-only source inspection and LightRAG database probe, the answer is **classification exists, but the tested primary seed filter is too coarse**.

## Distinguish separate metadata dimensions

| Dimension | Purpose | Reported/illustrative values | Do not confuse with |
| --- | --- | --- | --- |
| `source_type` | Type of ingestion pathway | `code` | Executable source fidelity |
| `doc_type` | Artifact-specific kind | `python source`, `typescript source`, `markdown_section`, `markdown_module` | Repo scope |
| Graph node type | Structural entity kind | Function, class, module, markdown section, external placeholder | Chunk-level authority |
| Provenance role | Evidentiary relevance | `implementation`, `documentation`, tests/other classification by artifact | Automatic ranking policy |
| File path / lineage | Repo structure and origin | `lightrag/operate.py`, `examples/...`, `DOCS/...` | Language-specific syntax type |
| Generation ID | Consistent ingestion snapshot | Pinned completed generation | Index recency by itself |

For codebase ingestion, Claude reported `pipeline._chunk(node.text, "code", ...)` and `_chunk` recording that value as `source_type`. Thus Markdown ingested from a repository can have `source_type="code"` while its `doc_type` is `markdown_section`.

## Reported LightRAG chunk counts

In one inspected LightRAG generation (77,625 chunks), Claude reported:

| source_type | doc_type | chunks |
| --- | --- | ---: |
| code | python source | 64,276 |
| code | markdown_section | 7,636 |
| code | typescript source | 3,891 |
| code | markdown_module | 1,816 |
| code | javascript source | 6 |

These counts sum to 77,625. They demonstrate why a `source_type="code"` restriction **does not exclude documentation** in that reported corpus. Verify against the exact production generation before using as a generalized invariant.

## Historical #64 and the newer gap

- The historical `doc_type="code"` search was reportedly nonmatching because code nodes use more specific `doc_type` values; the query fell back to unfiltered repo-scoped retrieval.
- Current local inspection reported use of `metadata_filter={"source_type":"code","repo_id":...}` in `hybrid_retrieve`.
- This avoids the original nonmatching `doc_type` value but still admits Markdown and codebase-ingested tests/examples.
- `DOC_TYPE_TIE_BREAK_ENABLED=False` was reported; when enabled, the tie break is limited to a narrow score window and cannot promote code ranked hundreds/thousands of positions away.
- Thus: **do not call #64 either wholly fixed or wholly unchanged**; treat it as a changed mechanism with a continuing code-authority weakness.

## Hard constraints versus soft preferences

**Hard constraints: never relax automatically**

- Repository identity / explicit user scope.
- Authorized access and source confidentiality.
- Completed committed generation and consistent graph/vector snapshot.
- Explicit language/file/path restrictions imposed by user, where applicable.

**Soft preferences: adapt with evidence needs**

- Implementation before historical reports for current runtime behavior.
- Library/source implementation before example usage for defining a function.
- Tests before prose for expected regression behavior.
- ADRs, design notes and dated releases for rationale/history questions.
- Smaller proof passages before redundant long test reports when context budget is tight.

These preferences should be *query-sensitive*, not a universal global exclusion. A bug report may require both source and tests; a why-question may require historical ADRs.

## A richer source authority policy to evaluate

Candidate fields (not approved schema): `artifact_role`, `is_production_path`, `is_test`, `is_example`, `is_generated`, `is_documentation`, `defining_symbol`, `source_fidelity`, `generation_id`, `resolution_confidence`. Prefer deriving reproducible metadata at ingestion, but avoid duplicating conflicting classification taxonomies.

Before changing schema, reconcile the existing provenance model and language-neutral IR. Several useful distinctions may already exist as graph node type, path classification, or provenance role and only require retrieval-time use.

## What would a correct retrieval gate do?

- For `Trace POST /v1/rag`, resolve the route and pin its defining implementation passage before using docs as context.
- For `Which test proves behavior X?`, prefer tests even if production code is lexically similar.
- For `Why was ADR-045 chosen?`, prefer the ADR and historical design records.
- For `What happens during ingestion?`, mix structural entry points, implementation call chains, lifecycle state transitions and tests as needed.
- Never let a `source_type="code"` filter be presented as an implementation-only guarantee.

## Diagnostic proof requirements

Record metadata and score/rank for exact target symbols under: unfiltered repo search; existing `source_type=code`; true `doc_type` implementation set (if API supports); path-role exclusions; and combined lexical/symbol retrieval. Also inspect the **final context**, not just initial candidates.
