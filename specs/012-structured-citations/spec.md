# Structured citations alongside `sources`

[Phase 6 implementation issue #407](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/407).
Depends on the evidence envelope (`specs/011-evidence-envelope/spec.md`).

## Contract

`POST /v1/rag` responses gain an additive `citations` list next to the
unchanged `sources: List[str]`. One citation per passage that entered the final
context (`retrieval_plan.final_context_manifest`), in manifest order.

| Field | Meaning |
| --- | --- |
| `repo_id` | Repository |
| `generation_id` | Generation the passage came from (the response's generation) |
| `path` | Repository-relative file path from the passage's chunk metadata, or `null` |
| `canonical_id` | Canonical identity of the artifact (ADR-031), or `null` |
| `document_id`, `chunk_id` | Stored artifact and passage identifiers, or `null` |
| `text_sha256` | SHA-256 of the cited passage text as it entered the context |
| `start_line`, `end_line` | 1-based inclusive line range in the file, or `null` |
| `range_reason` | Why the range is `null`; `null` when a range is present |

The Python inventory path cites the whole inspected file: `path`, the verified
`returned_text_sha256` as `text_sha256`, no canonical or chunk identifiers.

## Line ranges (stage 1)

Definition spans exist in the extractor IR but are not persisted by ingestion,
so no stored passage carries a line range. Stage 1 therefore returns every
range as `null` with `range_reason` = `"line span not persisted at ingestion"`.
Nothing is dropped and nothing is guessed. Persisting spans is a separate
ingestion change (schema, incremental-reuse retagging, ADR review) tracked
by its own issue; when it lands the same fields fill in without a contract
change.

## Acceptance cases

| Case | Observable result |
| --- | --- |
| Ordinary RAG answer | `len(citations)` equals the final-context manifest length; each carries generation, path, canonical id and the passage digest |
| Passage without a file path in its metadata | Listed with `path: null`, never dropped |
| Any citation today | `start_line` and `end_line` are `null` and `range_reason` says why |
| Python inventory answer | One citation for the file with the verified whole-file digest |
| Existing consumers | `sources` and every other field are unchanged |
| No manifest in the plan | `citations` is an empty list |

## Non-goals

Persisting spans; resolving citations through the source read (issue #408);
Markdown; changing retrieval, ranking, the manifest's selection logic or
generation. The manifest gains one additive key, `relative_path`.
