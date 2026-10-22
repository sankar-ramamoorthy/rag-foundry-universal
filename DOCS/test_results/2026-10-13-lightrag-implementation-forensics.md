---
title: "LightRAG implementation retrieval: stored bodies, missing passages, and context exclusion"
date: 2026-10-13
type: diagnostic-report
status: complete-with-original-trace-limits
tags: [lightrag, retrieval, behavioral-completeness, read-only]
related:
  - "[Inventory and pinned source](/DOCS/test_results/2026-10-13-lightrag-forensic-inventory.json)"
  - "[Live traces](/DOCS/test_results/2026-10-13-lightrag-live-traces.json)"
  - "[Observed replay](/DOCS/test_results/2026-10-13-lightrag-observed-replay.json)"
  - "[Integrity audit](/DOCS/test_results/2026-10-13-lightrag-forensic-audit.json)"
  - "[Operator read-only SQL](/DOCS/test_results/2026-10-13-lightrag-readonly.sql)"
  - "[Direct PostgreSQL results](/DOCS/test_results/2026-10-13-lightrag-direct-sql.json)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# LightRAG implementation retrieval forensics

## 1. Executive summary

Direct production PostgreSQL inspection now confirms **ten chunk records** for
`_build_query_context`, including Stage 2 in **ordinal 3**. Their IDs and full text
match the earlier API response exactly. The full `DocumentNode.text` and combined
chunk text match the pinned implementation when whitespace is ignored. The initial
ten-chunk finding was API-backed; the subsequent SQL verification independently
confirms it.
The explicit-symbol replay finds the function in initial vector results, but
within-artifact fetching returns **0, 9, 6**, the three highest-similarity chunks.
Stage 2 ranks seventh and never enters that fetched function context. Final
assembly then retains only ordinal 0 and excludes the already fetched return
and Stage 4 passages. Both budget helpers are discovered/fetched but excluded
from the final context. This is a combined passage-coverage and byte-allocation
failure, not an established inability to index or discover the symbol.

Natural-language discovery has another boundary: at Top K=20 the graph discovers
the function at expanded rank 34, but the 20-document cap prevents fetching it.
At Top K=5 the target is absent from both seeds and expansion. These are distinct
from the explicit-symbol failure. No single ranking or model-only explanation
accounts for every case.

Five live diagnostic queries and one locally observed replay were completed.
There were no application-code edits, database writes, migrations, re-ingestion,
deployments or LightRAG fixes. Only this report and diagnostic snapshots were
written. Existing unrelated workspace changes were preserved.

## 2. Indexed revision and generation

| Identity | Verified value |
| --- | --- |
| Repository | `HKUDS/LightRAG` |
| Repository ID | `4f76a36f-caf8-5532-9ee2-977ec412ed6c` |
| Ready ingestion | `128c494e-0aae-4e1d-81d0-b7e52f2006b1` |
| Indexed source commit | `4d0afc1bc36e6a34d4a5895b68efe9413748627a` |
| Completion timestamp reported by generation API | `2026-10-13T02:05:33.531663` |
| Local HEAD / remote main / four deployed runtime SHAs | `109f12d83ab83a306318423be618c195f8c4e6ea` |
| Deployed release | `prod-2026-10-13-0835am` |
| Answer model | `ollama/Qwen3:4b`; no fallback reported |
| Explicit-query context cap / delivered bytes | **4096 / 3960 UTF-8 bytes** |

The generation is a nonincremental ingestion. Versions/generation are checked
before/after the live queries and after the rank inventory. Exact public source
is fetched from the indexed commit, never GitHub HEAD. Runtime versions are
self-reports, not independent image/configuration attestation. Unknown deployed
settings are not assumed equivalent to local defaults.

The user-supplied failures already expose LightRAG results. This investigation
also inspects its source and answers: it is now **development/diagnostic data**,
not an untouched held-out #243 corpus.

## 3. Database inspection and limits

The initial investigation incorrectly reported that direct PostgreSQL access was
unavailable. The existing personal diagnostic script `scripts/db_inspect.py`
already provides a connection to the production database at `100.105.24.12:5434`.
After the user identified it, direct SQL inspection succeeded using the repository
virtual environment. The script was run with database-enforced read-only settings;
the full follow-up queries ran in a repeatable-read, read-only transaction ending
with `ROLLBACK`. No database writes occurred.

### Evidence provenance clarification

| Evidence class | Finding | Verification boundary |
| --- | --- | --- |
| Direct production SQL | Node bodies, chunk IDs/text/counts, generation record, live column schema, vector dimensions and call relationships | Six SELECT result sets captured in the direct-SQL snapshot. |
| Actual API response | Ten target records, ordinals 0-9, with chunk IDs, text and generation metadata | Captured HTTP response, not fixtures, model testimony or source-derived chunk counts. |
| Application source inspection | The vector endpoint implementation selects from `ingestion_service.vector_chunks` | Explains the expected backing store; does not independently attest the deployed SQL execution or live schema. |
| Derived source comparison | API-returned text covers the pinned function, including Stage 2 | Comparison against the indexed revision, ignoring whitespace; source line spans are derived from that comparison. |
| Retrieval/context observations | Which passages are selected and delivered in diagnostic replays | Establishes observed application behavior, not independent database integrity. |

The ten-record finding comes from the captured response under
`chunks["lightrag/operate.py#_build_query_context"].response.results` in the
[inventory](2026-10-13-lightrag-forensic-inventory.json). The request was
`POST /v1/vectors/search-by-doc` with `k=100`, document ID
`42b2fb9d-5730-4b5b-93d4-d96f849c786a`, repository ID
`4f76a36f-caf8-5532-9ee2-977ec412ed6c` and ingestion ID
`128c494e-0aae-4e1d-81d0-b7e52f2006b1`. Ten entries were returned, each with
its own chunk ID and text. This was a separate inventory request, not the
three-chunk retrieval request used by the answer pipeline.

Direct SQL confirms counts of 10, 19 and 17 for the target and its two budget
helpers. All 46 chunk IDs and texts match the API inventory exactly, all vectors
have 1024 dimensions, and there are zero missing vectors, canonical mismatches,
generation mismatches or duplicate ordinals. The three full node bodies match the
pinned source and their chunk unions when whitespace is ignored. The ingestion
record confirms commit `4d0afc1bc36e6a34d4a5895b68efe9413748627a` and status
`completed`. Full SQL, returned text and comparison results are retained in the
[direct-SQL snapshot](2026-10-13-lightrag-direct-sql.json).

The initial API inventory used these existing service-owned read APIs:

- Ingestion `GET /v1/repos` and `/v1/repos/{repo_id}/generation` identify the index.
- `POST /v1/graph/repos/{repo_id}/nodes/lookup` resolves canonical IDs.
- `GET /v1/graph/repos/{repo_id}` exposes nodes and actual relationships; this
  generation contains 41,635 graph nodes. The snapshot retains relevant edges.
- Vector `POST /v1/vectors/search-by-doc`, scoped by document/repository/generation,
  returns actual stored text, ordinals, IDs and metadata. Out-of-band `k=100`
  inventories are never supplied back to retrieval or generation.

The vector implementation reads `ingestion_service.vector_chunks`, including its
`vector` column, at `vector_store_service/src/core/vectorstore/pgvector_store.py:340`
and the materialized query at line 366. All ten target records return finite
query-distance scores in the full ranked inventory. Their canonical IDs and
ingestion IDs match the pin; there is no missing ordinal in 0-9.

Schema definitions were inspected in `shared/models/document_node.py:40`,
`shared/models/document_relationship.py:43` and the vector-chunk migrations.
The current vector service uses `vector_chunks`; the legacy ORM class in
`shared/models/vector_chunk.py` names **vectors** and declares 768 dimensions.
That stale declaration is not evidence of the live table's dimensions. Migration
`20260301_update_vector_dimensions_1024.py` declares 1024-dimensional columns;
the direct SQL now confirms 1024 dimensions for every inspected vector.

The graph API does **not** expose `DocumentNode.text` or its live content hash;
those values were subsequently inspected directly with SQL. The live column
schema and per-record dimensions were inspected, but exhaustive database
constraint inspection was not performed. The attached SQL supplied the six
executed SELECT statements; psql variable syntax was replaced with the fixed
repository/generation literals for execution through psycopg. Its Linux command
remains an operator alternative, not the execution route used here.

## 4. Structural symbols and chunk coverage

| Canonical symbol | Document ID | Pinned source lines | Stored chunks |
| --- | --- | --- | --- |
| `lightrag/operate.py#_build_query_context` | `42b2fb9d-5730-4b5b-93d4-d96f849c786a` | 6075-6197 | 10 |
| `lightrag/operate.py#_apply_token_truncation` | `737853c2-43b9-47ed-8440-bc2cef5456f7` | 5501-5716 | 19 |
| `lightrag/operate.py#_build_context_str` | `36ab72ed-5453-44d4-b2c5-81887685ff3e` | 5873-6071 | 17 |
| `lightrag/operate.py#_merge_all_chunks` | `1ba0e121-1397-446b-9925-03d1943af1a9` | 5765-5870 | 8 |
| `lightrag/operate.py#kg_query` | `37866cad-2d5e-4006-9bda-8684377859a3` | 4693-4972 | 13 |
| `lightrag/lightrag.py#LightRAG.aquery` | `1edada3c-74d1-41b4-adac-c1e09d44b64d` | 4843-4874 | 6 |

The file-level `lightrag/operate.py` document is
`be95e4e3-f949-46f7-bfb4-6b77d37bf93f`.

The target's chunk map is:

| Ordinal | Source lines | Content |
| --- | --- | --- |
| 0 | 6075-6090 | Signature and first docstring portion |
| 1 | 6092-6097 | Docstring remainder and empty-query guard |
| 2 | 6099-6111 | Stage 1 search invocation |
| **3** | **6113-6125** | Search-result guards and **Stage 2 truncation call** |
| 4 | 6127-6139 | Stage 3 chunk merge |
| 5 | 6141-6146 | Empty merged/context guard |
| 6 | 6148-6162 | Stage 4 `_build_context_str` invocation |
| 7 | 6164-6170 | Keyword/metadata initialization |
| 8 | 6172-6188 | Processing metadata |
| 9 | 6190-6197 | Logs and return |

Stage 2 chunk ID is `128e3c87-2e00-40ae-80c9-033c6e566d79`.
All ten ordered chunk texts match **all non-whitespace source characters** in the
pinned function. The same check succeeds for the truncation, merge and final
context helpers. This establishes complete code/content coverage, while avoiding
a claim that separately dedented passages preserve executable indentation or
byte-identical `DocumentNode.text`. The `kg_query` plain-text chunks overlap;
simple concatenation is not a valid integrity test for that artifact.

Actual CALL edges support the full chain:
`LightRAG.aquery → LightRAG.aquery_llm → kg_query → _build_query_context`, then
the truncation/merge/final-context helpers. `aquery_llm` is
`6ad540bd-7033-44ae-89f2-dcfa059e8873`, source lines 5114-5271.
Structural discovery is possible; useful graph relationships are not absent.

## 5. Retrieval and context trace

The live replay freezes supplied discovery wording at K=5 and K=20, an explicit
function/path query with backticks, and two clearly marked reconstructions of
the follow-implementation question and detailed bug report. Original UI trace
IDs, exact detailed/follow payloads and settings were not supplied. These are
diagnostic reproductions, not assertions that historical UI requests were identical.
The snapshots contain every request, answer, manifest, evidence trace and new
trace ID. Model is explicitly Qwen3:4b; deployment-default flags remain omitted.
All responses report reranking off and overview controls inactive/off.

| Replay | Target discovery | First observed blocking boundary |
| --- | --- | --- |
| Discovery K=5 | Neither vector nor graph finds target | Seed/expansion discovery |
| Discovery K=20 | Graph finds target at rank 34 | `MAX_EXPANDED_DOCS=20` cap; never fetched |
| Follow, reconstructed | Target is a vector seed | Partial target evidence delivered; truncation helper is graph rank 483 and capped out |
| Bug report, reconstructed | Truncation helper is a vector seed; final-context helper graph rank 498 | Required implementation incomplete; answer falsely claims a guaranteed total cap |
| Explicit symbol K=20 | Target is a vector seed | Relevant continuation outside per-artifact fetch, followed by byte exclusion |

The explicit live trace is `d6ac0895c003495ea76ffa698430d1b2`.
Global initial vector ranks **1, 2, 8** (zero-based) contain target ordinals **0, 9, 6**.
The observed per-document fetch requests **k=3** and returns exactly the same
three passages. It adds no new target chunk because these are already seeds.
The out-of-band rank inventory reproduces those scores and top-three IDs.

| Needed witness | Stored ordinal | Within-artifact rank, zero-based | Fetched? |
| --- | --- | --- | --- |
| Target Stage 2 call | target 3 | **6** | No |
| Entity truncation invocation | truncation 11, lines 5626-5632 | **10** | No |
| Relation truncation invocation | truncation 13, lines 5643-5653 | **3** | No |
| Combined-budget arithmetic | context 7, lines 5971-5976 | **6** | No |

This is **similarity-ranked fetching**, not always ordinals 0-2.
`EXPANDED_DOC_CHUNKS` also governs hydration of seed artifacts, despite its name:
see `rag_orchestrator/src/core/service.py:1056` and the requested count at line 346.
Global Top K=20 does not mean twenty passages per selected function.

Target 0/9/6 survive the five-per-document slice and adapter selection. Final
assembly at `rag_orchestrator/src/retrieval/agent_adapter.py:75` selects whole
passages within the UTF-8 byte cap. Three file-level fragments consume **3094
bytes**. Target ordinal 0 adds **655**, leaving **347**. Ordinal 9 costs **479**
and ordinal 6 costs **797**, so both are excluded. Fetched helper chunks cost
more than the remaining allowance and are likewise excluded. A 211-byte test
stub fits afterward, leaving 136 unused bytes.

The retained file passages are **289, 232, 291**: partial source fragments,
including a prefix of Stage 1 and part of Stage 4. They do not contain Stage 2's
call or actual budget arithmetic. Thus the historical description of a partial
function is directionally supported, but the live delivered context is not
literally limited to the signature/docstring/Stage 1 alone.

A process-local observer wraps unchanged main functions and returns their
original outputs. It captures HTTP requests/results and the actual `/generate`
payload, without editing repository code. The observed final manifest matches
the live explicit request **exactly**, including order/IDs/text hashes. Its
3960-byte context is reproduced byte for byte from the retained passages.
Local pre-budget pools differ (37,691 versus live 36,393 bytes), so complete
intermediate runtime/configuration parity is not asserted. The captured wire is
the local replay's actual LLM request, not a server-side interception of the UI.

## 6. First confirmed point of evidence loss

For the explicit query, Stage 2 is absent from initial seed passages and is
**not recovered when hydrating the already discovered symbol**: its rank 6 lies
outside the k=3 per-artifact cut. This is the first confirmed continuation-loss
boundary, before final assembly. Actual truncation calls and total arithmetic
are outside their helper fetch cuts too. Separately, fetched Stage 4/return and
helper evidence is then lost at the final byte budget.

For natural discovery at K=20, the earlier boundary is expanded-document
selection, despite successful graph discovery. At K=5 the target is not
discovered at all. The evidence does not support a universal single-stage cause.

## 7. Independent LightRAG budget-code assessment

At the pinned revision, `_build_query_context` delegates Stage 2 at lines
6120-6125. `_apply_token_truncation` reads independent entity/relation limits at
5537-5547 and applies them separately at 5626-5648; it does not apply the combined
total there. `_build_context_str` reads the total at 5905-5910, measures the
already-selected graph context and prompt, then subtracts those costs, the query
and a 200-token reserve from the total to obtain a **text-chunk** allowance at
5971-5989. It does not re-truncate graph records to that remainder.
`kg_query` formats the resulting prompt at 4809-4815; 4828-4838 counts it for a
debug log, without enforcing a final cap. The reported mechanism is therefore
supported by the [pinned implementation](https://github.com/HKUDS/LightRAG/blob/4d0afc1bc36e6a34d4a5895b68efe9413748627a/lightrag/operate.py#L5501).

Independent fields in `QueryParam` are at `lightrag/base.py:122-136`;
`lightrag/constants.py:59-61` defines 6000/8000/30000 defaults. API limits at
`lightrag/api/routers/query_routes.py:76-96` bound individual values; inspection
found no cross-budget constraint. With no chunks, `process_chunks_unified`
returns immediately (`lightrag/utils.py:7078-7079`); it cannot reduce graph records.

**The approximately 5550-token numerical reproduction is not verified.** Its
graph records and exact tokenizer inputs were not supplied. No LightRAG execution
or fix was attempted; this source assessment is separate from retrieval diagnosis.

## 8. Root cause and confidence

- **High:** complete target/helper content exists in stored chunks, with correct
  canonical/generation IDs and usable scored vector records.
- **High:** exact-query passage fetching omits required continuations; byte
  assembly separately drops useful fetched evidence. Live trace plus a matched
  final manifest and observed wire substantiate the latter.
- **High for these replays:** natural discovery can reach the target in graph
  expansion but lose it at breadth selection. No claim that every original UI
  request or model produces the same result is made.
- **High:** the pinned budget code supports the mechanism; the stated numerical
  example is unverified.
- **Directly verified:** full node bodies and chunk records for the target and
  budget helpers, live column schema, vector dimensions and pinned generation.
- **Unknown:** original UI settings and original server-side wire/logs. Retrieve
  original trace IDs to connect the diagnostic replays to those exact requests.
- **Not demonstrated:** model failure despite complete implementation delivery.
  The reconstructed bug answer invents a total-cap guarantee, but its evidence
  is incomplete; changing models is not an established remedy.

## 9. Minimal recommended intervention

Start with **existing evidence selection and bounded continuation/callee
fetching for exact implementation questions**, not another subsystem. Preserve
the directly named function ahead of redundant file-level fragments and test
stubs, then fetch/select the missing stage/callee witnesses for requested budget
fields under the existing cap. The current explicit-mention path is restricted
to `ClassName.method_name` (`traversal_selector.py:353-415`); this free function
receives no explicit-priority marker in the observed plan. Extending that existing
mechanism is a candidate to evaluate, not a validated fix or a reason to alter
claim classification.

Merely promoting ordinal 0 would still omit Stage 2. Merely increasing k would
still lose the extra passages to bytes: all ten target chunks alone render to
**5102 labeled bytes**, exceeding 4096 before helpers. Require source-coherent
passage coverage, avoiding misleading branch fragments and repeated signatures.
No claim is made that an automatic compact complete context has been demonstrated
here. Only afterward characterize natural discovery's graph breadth/ranking
loss; existing query decomposition or structural traversal may suffice.

## 10. Regression test design

Freeze this pinned development corpus and exact request/settings before a
candidate. Keep implementation/mechanics gates separate from answer gates:

1. **Indexed content:** a long async function's beginning, branch, middle and
   return are stored with correct IDs/ordinals/vectors; verify full content, not
   counts. Include code chunking with overlap and separate callee budgets.
2. **Discovery versus survival:** distinguish K=5 seed miss, K=20 graph discovery
   beyond breadth, and exact-symbol discovery. Assert reasons separately; do not
   let source IDs alone count as a successful implementation explanation.
3. **Continuation/callee coverage:** the exact request must deliver the Stage 2
   call, entity/relation truncation operations, combined-budget arithmetic and
   final prompt handoff, with branch/state relationships preserved.
4. **Byte accounting:** labels/separators remain inside 4096 bytes. Keep retained
   identities/hashes equal to actual `/generate` context. Exercise file-level
   duplicate evidence and competing test stubs. No silent cap increases.
5. **Answer grounding:** correctly attribute helper operations, explain that
   the combined remainder constrains text chunks, and do not invent a final
   graph/whole-prompt clamp. Score facts, attribution and citations independently.
6. **Controls/generalization:** keep existing overview and explicit-code controls
   intact; add other long-function/branch/callee shapes before adoption. LightRAG
   is now diagnostic data and cannot establish held-out generalization by itself.

These are proposed tests, not implemented tests or passing behavior claims.
