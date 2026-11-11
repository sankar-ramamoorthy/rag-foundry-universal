---
title: "CI-06 independent review: PR #339 and proposed ADR-056"
date: 2026-11-10
type: audit
status: complete
summary: "Recommend holding PR #339 and retaining ADR-056 as proposed: live truncation counterexamples, a generation-mixing path, and incomplete token-fit and delivery evidence"
source_commit: 6c944dd019b246eb1f91501ab972ec701aaea9e1
base_commit: 75c3b4c68b5aa784eb2ac62723ad0583901b91a0
scope: "CI-06 implementation, embedding-input contract, incremental reuse, retrieval evidence, and rollout"
method: "Independent source review, local Ollama probes, focused tests, Unicode coverage probes, and raw-evidence verification"
authority: "Point-in-time review evidence and recommendations; does not accept an ADR, authorize implementation, or change specifications"
verification_status: "Local model and unit verification completed; local PostgreSQL unavailable; remote PR status and CI not independently verified"
tags: [audit, ci06, ci03, embedding, chunking, incremental-ingestion, issue-337, pr-339]
related:
  - "[Issue #337](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/337)"
  - "[PR #339](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/339)"
  - "[Audit index](/DOCS/audit/00-Audit-Overview.md)"
  - "[November 10 architecture audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[Independent review and audit-author response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md)"
  - "[CI-06 investigation](/DOCS/audit/2026-11-10-ci06-embedding-input-coverage-investigation.md)"
  - "[CI-06 verification](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md)"
  - "[Proposed ADR-056](/DOCS/adr/ADR-056-embedding-input-contract.md)"
  - "[CI-06 implementation plan](/specs/005-production-correctness/ci06-plan.md)"
  - "[Incremental-ingestion specification](/specs/006-incremental-ingestion-lineage/spec.md)"
  - "[CI-06 handoff](/DOCS/notes/2026-11-10-ci06-embedding-input-contract-handoff.md)"
---

# CI-06 independent review: PR #339 and proposed ADR-056

**Recommendation: do not accept ADR-056 as written; PR #339 is not ready to
merge.** Two high-severity correctness findings undermine its central
guarantees. One is reproduced against the actual local embedding model; the
other follows directly from the generation lifecycle and retag SQL.

The shared input contract and explicit reuse-version transition are useful
improvements. The source-slicing implementation also passed additional coverage
checks. Those results do not establish that every accepted passage fits the
model, or that legacy vectors cannot enter a new-contract generation.

## Scope, authority, and verification limits

Reviewed local branch `fix/337-ci06-embedding-input-coverage`, head
`6c944dd019b246eb1f91501ab972ec701aaea9e1`, against base
`75c3b4c68b5aa784eb2ac62723ad0583901b91a0`. The local remote-tracking branch
matched the reviewed head. GitHub CLI authentication failed with HTTP 401 and
the browser could not retrieve the PR, so current remote head, checks, and
mergeability were not independently established. The author's green-CI record
remains historical evidence, not a fresh check from this review.

The assessment compared actual changes with the November 10 audit and response,
CI-06 investigation and implementation plan, incremental-ingestion requirements,
bounded-memory specification, and relevant embedding/evaluation ADRs. ADR-056
is proposed, not an accepted requirement. This review does not itself amend or
accept any governing document.

Evidence labels used below:

- **Live:** actual local Ollama requests and production adapter behavior.
- **Source:** inspected code and a concrete execution path; not a claim that a
  production incident or database reproduction was observed.
- **Probe:** executed local synthetic inputs or focused tests.
- **Captured evidence:** author-produced files whose hashes and reported
  aggregates were independently checked.
- **Risk / unanswered:** consequences or acceptance gaps not established as
  observed end-to-end failures.

Local Ollama reported `bert.context_length = 512` for
`mxbai-embed-large:latest`, digest
`468836162de7f81e041c43663fedbbba921dcea9b9fefea135685a39b2d83dd8`.
No production service was contacted, deployed corpus rebuilt, or held-out
evaluation executed. The local PostgreSQL connection on port 5433 timed out;
the attempted temporary-table probe stopped before creating anything.

Application code, specifications, ADRs, and test files were not modified during
the review. The owner subsequently requested this documentation record. No
commit, merge, deployment, or vector-store write was performed. The existing
untracked `scripts/code_evidence_prototypes.py` and
`tests/test_code_evidence_prototypes.py` were left untouched.

Source links and line numbers below describe the reviewed commit. This is a
dated assessment, not a replacement for [project status](/DOCS/status.md).
`status: complete` means the review is complete, not that its findings are fixed.

## Findings by severity

| ID | Severity | Classification | Finding |
|---|---|---|---|
| R1 | High | Confirmed, live + source | Budget-compliant passages still produce truncated embeddings |
| R2 | High | Confirmed, source | Failed cleanup can mix legacy and new-contract vectors into a later generation |
| R3 | Medium | Confirmed, live + probe | The verification script's claimed exact token counter differs from Ollama |
| R4 | Medium | Unresolved acceptance risk; proxy regressions measured | Discovery improvements do not establish delivery-quality safety |
| R5 | Medium | Existing limitations and operational risks | Reuse identity and rollout guarantees need narrower claims and explicit controls |

### R1 — Budget-compliant passages still produce truncated embeddings

The estimator counts an ASCII alphanumeric run of length L as ceil(L/3).
That is not a conservative upper bound on the serving model's tokens:
[text.py:15](/shared/chunkers/text.py#L15).

The following inputs each produce one passage through the production factory
with `source_type="code"`. All satisfy its 800-character and 480-estimated-token
limits, but the actual model rejects them with `truncate=False`:

| Input expression | Characters | Estimated tokens | Strict Ollama result |
|---|---:|---:|---|
| `"xyz " * 200` | 800 | 200 | HTTP 400: context overflow |
| `"qz" * 300` | 600 | 200 | HTTP 400: context overflow |
| `"# " + "xyz " * 195 + "TAIL_CI06"` | 791 | 201 | HTTP 400: context overflow |

The last example is a valid Python comment. The failure is therefore reachable
with source text, not only an oversized direct adapter call.

At [ollama.py:84](/shared/embedders/ollama.py#L84), the adapter sets the
truncation flag and retries with `truncate=True`. Ollama documents that this
permits inputs to be truncated to the context window:
[API documentation](https://docs.ollama.com/api/embed).

The actual adapter and
[record builder](/ingestion_service/src/core/http_vectorstore.py#L29) produced
the following for the comment example, without sending the record to storage:

```text
stored_chars: 791
stored_tail: TAIL_CI06
embedding_input: {contract: exact-input-v2, truncated: true}
vector_dim: 1024
```

The full passage is retained although the model encoded a shortened input.
This contradicts [ADR-056 rule 1](/DOCS/adr/ADR-056-embedding-input-contract.md#L41).
Rule 5's degradation flag discloses the exception but cannot satisfy the
exact-input invariant. Metadata alone also does not prevent a successful
generation from containing these vectors or a later ingestion from reusing them.

**Recommended correction:** prohibit truncating fallback for indexed passages.
Either fail ingestion explicitly or split overflowing passages and encode every
resulting piece. Splitting must preserve actual persisted text, metadata, and
document-local ordinals; returning extra vectors from the current one-vector-per-
chunk adapter interface alone would not be sufficient. An accurate tokenizer can
improve fitting, but strict provider rejection should remain the final guard.
Define query overflow separately from indexed-passage overflow.

**Missing tests:** the three cases above, strict overflow through the persistence
boundary, and a guarantee that an exact-contract generation cannot complete with
truncated indexed inputs. The current suite tests the estimator against itself
and uses a fake provider whose overflow boundary is character count.

### R2 — Cleanup failure can mix contracts in a later generation

The version gate correctly forces the first full re-embedding. The stronger
claim that contracts never mix in a generation does not hold under the existing
best-effort cleanup path.

Concrete sequence:

1. G1 contains legacy vectors.
2. G2 re-embeds the repository under CI-06. Surviving canonical artifacts retain
   their document IDs, so their old and new vectors can coexist temporarily.
3. G2 completes, but deletion of G1's vectors fails. Completion precedes cleanup,
   and cleanup exceptions are logged without failing the ingestion:
   [codebase_ingest.py:550](/ingestion_service/src/api/v1/codebase_ingest.py#L550).
4. G3 sees unchanged files and configuration matching G2, making them reusable.
5. Retagging selects every vector for each eligible document ID, without
   restricting the old ingestion ID. Both G1 and G2 vectors become G3 vectors.

Both SQL branches are affected:
[pgvector_store.py:312](/vector_store_service/src/core/vectorstore/pgvector_store.py#L312)
and [pgvector_store.py:328](/vector_store_service/src/core/vectorstore/pgvector_store.py#L328).
The normal provenance-refresh branch updates rows by document ID alone.
Subsequent cleanup by G1 or G2 ingestion ID cannot remove rows already relabeled
G3. A generation-scoped retrieval filter consequently cannot distinguish them.

This is a pre-existing lifecycle weakness exposed by the migration, rather than
new SQL introduced by this PR. It nevertheless contradicts
[ADR-056's generation-isolation claim](/DOCS/adr/ADR-056-embedding-input-contract.md#L86).
The new migration test expressly excludes cleanup behavior:
[test_incremental_ingest.py:406](/ingestion_service/tests/api/test_incremental_ingest.py#L406).

**Recommended correction:** carry the expected prior generation through the
retag API and constrain updates to it, rather than relying on successful garbage
collection to establish vector identity. Verify the expected reused vector set.
Keep obsolete-vector cleanup independent of correctness.

**Missing test:** three generations with injected cleanup failure after the
legacy-to-CI-06 rebuild. Assert that only the immediate eligible generation's
vectors acquire G3 membership, including the provenance-refresh branch.

**Verification limit:** this is confirmed from the explicit predicates and
lifecycle ordering. The local test database was unavailable, so no database
reproduction or production occurrence is claimed.

### R3 — The verification counter is not equivalent to the serving tokenizer

The offline counter substitutes one unknown token for words longer than 100
characters at
[ci06_embedding_coverage.py:249](/scripts/ci06_embedding_coverage.py#L249).
It also applies NFD normalization at
[line 225](/scripts/ci06_embedding_coverage.py#L225).
Live requests exposed differences in both directions:

| Input expression | Offline counter | Actual Ollama result |
|---|---:|---|
| `"qz" * 51` | 3 tokens | 104 tokens; accepted |
| `"qz" * 300` | 3 tokens | Context overflow; rejected |
| `"\uac01 " * 240` (Korean syllable plus space) | 722 tokens | 242 tokens; accepted |

The Korean case does **not** demonstrate a production overflow. It demonstrates
that the offline normalization is not equivalent to the serving tokenizer.
The long ASCII word is a false negative for the overflow measurement itself.

The reported 43/43 calibration therefore does not justify a general claim of
exact token counts. **This review has not proved that the published corpus-level
zero-overflow totals are wrong.** A supplemental scan of the current foundry
worktree found no produced passages with words above the counter's 100-character
threshold; that scan was not a rerun of both original pinned corpora. The finding
is that the measurement tool can miss the condition it purports to detect.

**Recommended correction:** use the actual serving tokenizer or validate corpus
passages through Ollama with `truncate=False`. Add long-word, normalization, and
multilingual calibration cases. Revalidate token-fit evidence before using it
to justify deferring exact tokenization. Record the serving implementation and
model identity with that evidence.

### R4 — Delivery-quality acceptance remains unestablished

The raw captures support meaningful improvements on omitted-text needles. Their
reported aggregates reproduce. They also show regressions on already-covered
LightRAG queries:

| Control metric | Legacy | CI-06 line windows |
|---|---:|---:|
| Verbatim hit@5 | 90/125 | 85/125 |
| Identifier-word hit@5 | 92/125 | 83/125 |
| Verbatim MRR | 0.671 | 0.639 |
| Identifier-word MRR | 0.671 | 0.622 |

These are measured proxy regressions, not proof of worse generated answers.
Likewise, nonsignificant paired tests do not demonstrate non-inferiority. See
the [reported control effects](/DOCS/test_results/2026-11-10-ci06-embedding-input-coverage-verification.md#L135).

The experiment excludes documentation retrieval and artifacts above 12,000
characters, uses short source-derived queries, and ranks deduplicated artifacts
over a sampled passage pool:
[sampling](/scripts/ci06_embedding_coverage.py#L603),
[ranking](/scripts/ci06_embedding_coverage.py#L480).
It does not reproduce production candidate limits, graph expansion, passage
selection, final context assembly, or long-query behavior.

Production limits passages by count at
[execute_plan.py:65](/rag_orchestrator/src/retrieval/execute_plan.py#L65), then
selects whole passages within a UTF-8-byte allowance at
[agent_adapter.py:75](/rag_orchestrator/src/retrieval/agent_adapter.py#L75).
Different boundaries can alter evidence survival independently of discovery.
An 800-character cap also does not imply 800 bytes for multilingual content.
The rationale for deferring 400-character passages recognizes this interaction,
but the chosen 800-character policy changes it too.

The [audit response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md#L454)
requested separate coverage, discovery, and delivery evidence. The
[constitution](/.specify/memory/constitution.md#L85),
[quality methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md), and
[ADR-054](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)
govern evaluation; unit success is not a substitute for quality evidence.

**Recommended correction:** run a matched development-corpus delivery evaluation
with fixed context budgets and explicit acceptance criteria. Include large
artifacts, evidence spanning windows, multilingual repository documentation,
long queries, and supported document-upload paths affected by the shared change.
Use isolated generations so deployed E1 pins remain intact. Report discovery,
statement survival, and answer effects separately. No held-out tuning is
recommended or authorized by this review.

### R5 — Remaining CI-03 and rollout risks require explicit limits

The version addition at
[codebase_ingest.py:375](/ingestion_service/src/api/v1/codebase_ingest.py#L375)
handles the intended transition, but does not identify extractor behavior,
immutable model digest, dimension, or effective inference configuration.
These are largely acknowledged pre-existing CI-03 limitations. Dimension
identity is also explicit in
[FR-006](/specs/006-incremental-ingestion-lineage/spec.md#L269).

Re-extraction can update an artifact's current text or structure while file-hash
reuse retains its older passages. A mutable model alias can change the embedding
computation without changing this gate. A matching contract string alone does
not prove representation equivalence. The broader per-product identity work
belongs to CI-03; it should not be represented as resolved by CI-06.

Degraded vectors from R1 also remain eligible for ordinary reuse: no gate
examines `embedding_input.truncated`. For queries, the temporary metadata is
discarded by [embed_query](/shared/embedders/query.py#L25), so the new flag does
not provide request-level visibility into query truncation. Long queries also
change behavior immediately when the shared adapter changes, even before stored
legacy corpora are re-ingested; the short-query experiment does not assess this.

Operational consequences and unanswered questions:

- Every repository's next ingestion performs full embedding work. Fewer
  aggregate passages do not establish migration duration or resource cost.
- Counts can rise for individual artifacts despite aggregate savings. The
  updated 128,000-character fixture goes from 143 to 160 passages.
- With a 50-input batch, one rejected batch is followed by 50 singleton strict
  requests and one truncating request per offender: 51 plus the number of
  overflowing inputs. Provider work and latency can increase substantially.
- Existing uploaded documents do not receive the repository generation gate's
  automatic transition. The existing Markdown/Docling section failure remains
  separately tracked under #338; this review does not attribute it to CI-06.
- Rolling back the ingestion implementation changes the contract back and
  requires another rebuild to restore the prior passages. It is not a free
  restoration of the old index. Pinned evaluation generations need deliberate
  preservation or re-baselining, as the handoff already recognizes.
- `_split_line` repeatedly copies the remaining suffix at
  [text.py:50](/shared/chunkers/text.py#L50). Synthetic single-line timings grew
  from about 0.85 seconds at 2 million characters to 3.84 seconds at 4 million
  and 16.46 seconds at 8 million. These exceed the default repository artifact
  ceiling of 1 MiB; they establish a scaling risk if that ceiling is raised,
  not a demonstrated default-envelope availability defect.

**Recommended correction:** specify the supported model/configuration envelope,
migration inventory, degraded-input policy, representative full-ingestion cost,
and rollback procedure. Retain the broader CI-03 work as open. Pin operational
model configuration during migration; do not claim the version strings enforce
properties that they do not encode.

## Independent verification record

| Check | Observed result | Scope limit |
|---|---|---|
| New embedding-input contract tests | 57 passed | Includes mocked provider behavior; does not prove real token fit |
| Bounded-batch contract tests | 30 passed | Focused mechanics, not full CI or database acceptance |
| Additional source-coverage probes | 300 cases; 9,646 windows passed | Source slicing and estimator budgets, not semantic or real-token coverage |
| Local Ollama overflow and tokenizer probes | R1 and R3 reproduced | Recorded local model, not deployed runtime |
| Actual adapter plus persistence-record builder | Full 791-character passage retained with truncation flag | No vector-store HTTP request or database write |
| CI-06 raw-index verification | All nine files matched recorded size and SHA-256 | Integrity of captures, not independent regeneration of their embeddings |
| Retrieval aggregate recomputation | Reported gap/control hit@5 and MRR reproduced | Recomputed from captured per-query ranks |
| Local PostgreSQL probe | Connection timed out before table creation | R2 not reproduced against a database |
| Remote PR/CI verification | Authentication/fetch unsuccessful | Current remote status remains unknown |

The additional coverage probes used seed 339 and included ASCII, CJK, Korean,
combining accents, emoji sequences, tabs, CRLF, CR, NEL, and Unicode line/paragraph
separators, including oversized lines. They checked in-order verbatim windows,
coverage through the end of the source, forward progress, and both configured
budgets. This supports character preservation. It does not guarantee preservation
of grapheme or semantic units, source-span metadata, or model-token fit.

Raw author captures remain referenced through the
[raw index](/DOCS/test_results/raw-index.json). The additional review probes ran
in memory; their compact observations are recorded here, not claimed as newly
indexed raw artifacts.

## Reproduction notes

Focused test commands, run from `ingestion_service` with bytecode generation
disabled and pytest's cache provider disabled:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
..\.venv\Scripts\python.exe -m pytest tests/codebase/test_embedding_input_contract.py -q -p no:cacheprovider
..\.venv\Scripts\python.exe -m pytest tests/codebase/test_bounded_batch_contract.py -q -p no:cacheprovider
```

The following compact reproducer uses the reviewed production chunker and a
local Ollama. Run its Python body from the repository root. It performs embedding
requests only; it does not persist vectors or alter a corpus:

```python
import requests
from shared.chunkers.selector import ChunkerFactory
from shared.chunkers.text import estimate_tokens
from shared.embedders.ollama import OllamaEmbedder

text = "# " + "xyz " * 195 + "TAIL_CI06"
chunker, params = ChunkerFactory.choose_strategy(text, source_type="code")
chunks = chunker.chunk(text, **params)
print([(len(c.content), estimate_tokens(c.content)) for c in chunks])

base = "http://localhost:11434"
model = "mxbai-embed-large:latest"
response = requests.post(
    base + "/api/embed",
    json={"model": model, "input": [c.content for c in chunks], "truncate": False},
    timeout=(5, 60),
)
print(response.status_code, response.json().get("error"))
vectors = OllamaEmbedder(base, model).embed(chunks)
print(len(vectors[0]), chunks[0].metadata, chunks[0].content[-9:])
```

Observed: one `(791, 201)` passage, HTTP 400 with
`the input length exceeds the context length`, followed by a successful
1024-dimensional adapter result marked `truncated=True` with the source tail
still present. Reproduction depends on the recorded model and serving behavior;
verify the model digest and context before comparing results.

## Decision recommendation

Keep **ADR-056 proposed**. Its direction is sound, but the invariant and the
allowed truncation fallback contradict each other. Its no-mixing consequence
requires generation-fenced reuse, not just a version mismatch on the first
rebuild. It should also explicitly resolve the acknowledged relationship with
ADR-040's artifact/sub-artifact wording rather than leave competing guarantees
for future readers.

Hold **PR #339** until R1 and R2 are corrected, token-fit evidence is revalidated,
and a matched delivery-quality evaluation meets explicit acceptance criteria.
The remaining CI-03 scope can stay separate if its limits and operational
assumptions are stated accurately. These are review recommendations, not owner
acceptance or authorization to implement, merge, re-ingest, or deploy.
