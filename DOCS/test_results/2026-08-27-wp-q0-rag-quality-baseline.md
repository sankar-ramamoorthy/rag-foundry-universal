# WP-Q0: RAG Quality Baseline — Evidence

**Spec**: `specs/001-rag-quality-baseline/spec.md`
**Tasks**: `specs/001-rag-quality-baseline/tasks.md`
**Tracking Issue**: #49

This file accumulates evidence across Scenarios 1-4 (spec.md) as tasks
T001-T024 execute. Sections are appended in task order; nothing here is
retroactively edited except to correct a recording error.

---

## Environment Verification (T001-T002)

Executed 2026-08-27.

- Stack brought up via `docker compose up --build`; all 6 containers
  (`ingestion-db`, `ingestion-service`, `vector-store-service`,
  `llm-service`, `rag-orchestrator`, `gradio-ui`) reached `healthy`/`Up`,
  all four service `/health` endpoints returned 200.
- Migrations applied: `alembic upgrade head` → `20260719_typed_cols` (head).
- Local Ollama (`localhost:11434`) and remote Tailscale Ollama
  (`100.105.24.12:11434`, `LLM_DEFAULT_ALIAS=remote`) both reachable;
  required models present on each (`mxbai-embed-large:latest` embedder,
  `phi4-mini:latest` local LLM alias, `Qwen3:4b` remote LLM alias).
- `shared/smoke_repo` confirmed present on host and correctly volume-mounted
  into `ingestion-service` at `/app/shared/smoke_repo` (4 files: `README.md`,
  `animals.py`, `dogs.py`, `kennel.py`), ingestable without modification.

**Environment notes (not product bugs, recorded for reproducibility):**
- An unrelated project's container (`tradeforge-postgres-1`) was squatting
  on host port 5432, blocking `ingestion-db` from starting on first `up`.
  Stopped with user confirmation.
- After that conflict was cleared, `docker compose up -d` started
  `ingestion-db` without actually publishing port 5432 to the host (Docker
  Desktop/WSL2 quirk following the earlier failed `up`) — required
  `docker compose up -d --force-recreate postgres` to fix.

---

## Evaluation Corpus (T004-T005)

Executed 2026-08-27.

### Repo ingestion (T004)

Ingested via `POST /v1/ingest-repo` with `local_path=/app/shared/smoke_repo`:

| Field | Value |
|---|---|
| `repo_id` | `a9d1aeb1-066c-5663-8d95-1681c165077f` |
| `ingestion_id` | `8937ca0d-aa67-4451-a1f1-9358646a7989` |
| `ingested_at` | 2026-08-27T21:57:00.649927Z |
| `file_count` (reported) | 5 |
| `node_count` | 16 |

**Note:** `GET /v1/repos` reports `file_count: 5`, but the repo has 4 physical
files (`README.md`, `animals.py`, `dogs.py`, `kennel.py`) and the persisted
`document_nodes` rows for this `repo_id` show exactly 4 distinct
`relative_path` values (16 nodes total: 4 file-level + section/symbol nodes,
including one `EXTERNAL_SYMBOL:dog.speak` placeholder node with no
`relative_path`). The `file_count` field appears to overcount by one relative
to actual ingested files. Not investigated further here — out of scope for
this task (would need filing as a separate issue per spec.md Non-Goals /
FR-008 if it turns out to be a real defect rather than an intentional count
of some non-file artifact).

### Document ingestion (T005)

Per research.md Decision 1, selected 3 pre-existing project documents (not
newly authored) mixing project-overview and factual/planning content.
Ingested via `POST /v1/ingest/file`:

| File | `ingestion_id` | Root `document_id` (canonical_id = filename) | doc_type |
|---|---|---|---|
| `README.md` | `dd063881-4675-4023-9783-511c05340837` | `98317fb3-5eee-45f1-bc1b-f755629f6fb2` | markdown_module |
| `DOCS/audit/04-Scalability-Plan.md` | `25e4b5ca-b1b8-4074-b7f2-ad8c394b1096` | `3736db8c-c11c-4821-942f-1ba19e9d357f` | markdown_module |
| `DOCS/audit/07-Roadmap.md` | `99c65ffc-17bc-4329-83ad-f4bd8e3d8cb4` | `302ed1c1-61c8-497d-a2c8-36a7be5ff97c` | markdown_module |

Each file was chunked by the Markdown section extractor into one root
`markdown_module` node plus one `markdown_section` node per heading (README.md:
11 sections; 04-Scalability-Plan.md: 15 sections; 07-Roadmap.md: 9 sections)
— confirmed directly against `document_nodes` (37 rows total across the three
`ingestion_id`s). For document ingestion, `repo_id` on each row equals that
document's own `ingestion_id` (per ADR-042's documented asymmetry between
codebase- and document-ingestion `document_id`/`repo_id` ownership).

All three ingestions reported `status: completed` via
`GET /v1/ingest/{ingestion_id}`.

**Observation (README.md chunking, not an ingestion_service bug):** the
Architecture section (`README.md#rag_foundry_universal.architecture`) in the
source file opens a fenced code block (line 42, ` ``` `) that is not closed
until after the "Service URLs", "Tech Stack", and "Ingestion Capabilities"
headings (closes ~line 131). Per Markdown syntax, headings inside an open
code fence are not real headings, so the section extractor correctly folded
all four sections into one large chunk under "Architecture" — confirmed by
reading the source file and the persisted `vector_chunks.chunk_text`. This is
a pre-existing authoring defect in `README.md` (a missing closing fence), not
a chunker defect. Recorded here because it affects Q8 below and is exactly
the kind of chunking-adjacent artifact this evaluation exists to surface — not
filed as a separate issue since it's a doc-authoring nit with no functional
impact, but noted in case Scenario 2/4 classification needs the context.

---

## Known-Answer Question Set (T006)

Drafted 2026-08-27. 10 questions (5 code against `shared/smoke_repo`, 5
document against the three ingested docs above), deliberately spanning:
plain-vector-friendly lookups, questions that require graph traversal
(INHERITS/OVERRIDES/CALL edges) rather than surface text similarity,
exact-identifier/structural questions, semantic paraphrases, and one question
that deliberately targets the chunking artifact noted above. None are
adversarially worded; none are trivially guaranteed to pass.

### Code questions (`repo_id = a9d1aeb1-066c-5663-8d95-1681c165077f`)

| ID | Question | Expected `canonical_id` | What it exercises |
|---|---|---|---|
| Q1 | What does the `Animal` class define? | `animals.py#Animal` | Baseline — direct vector-similarity match, no graph needed |
| Q2 | What class does `Dog` inherit from? | `dogs.py#Dog` | `INHERITS` edge — the class definition line names the base, but the *relationship* is graph-modeled |
| Q3 | Which functions call `train_dog`? | `kennel.py#run_demo` | Reverse-caller query — cross-file `CALL` edge; low textual overlap between question and callee body |
| Q4 | Which method does `Dog` override from its parent class? | `dogs.py#Dog.speak` | `OVERRIDES` edge |
| Q5 | When `Dog.fetch` executes, which inherited method does it end up calling? | `animals.py#Animal.eat` | Inherited self-call resolution — hardest case; answer isn't textually near `fetch`'s definition |

### Document questions

| ID | Question | Source doc | Expected section (`canonical_id`) | Expected passage (excerpt) | What it exercises |
|---|---|---|---|---|---|
| Q6 | What does `rag-foundry-universal` let you query across, and how does it combine graph traversal with LLM reasoning? | README.md (`ingestion_id=dd063881-4675-4023-9783-511c05340837`) | `README.md#rag_foundry_universal.overview` | "Combine deterministic graph traversal with LLM reasoning" | Baseline — semantic paraphrase of Overview content, vector-friendly |
| Q7 | What ANN index does the vector store use for similarity search, and what was its measured p95 latency in the Phase 1 benchmark? | README.md | `README.md#rag_foundry_universal.key_features` | "HNSW (cosine) ANN index plus filter indexes on pgvector — search latency independent of corpus size (p95 ≈ 62 ms in the Phase 1 benchmark)" | Exact-fact retrieval, distinctive keyword ("HNSW") |
| Q8 | What port does `rag_orchestrator` run on, and what are its two main endpoints? | README.md | `README.md#rag_foundry_universal.architecture` (see chunking note above — "Service URLs" is not a separate node) | "`rag_orchestrator` \| 8004 \| `/v1/rag`, `/v1/rag/simple`" | Deliberately targets the merged-fence chunk — tests whether retrieval surfaces a fact buried inside a much larger, differently-titled chunk |
| Q9 | What does WP-S6 in the scalability plan address, and why is it called "the massive-repo unlock"? | `DOCS/audit/04-Scalability-Plan.md` (`ingestion_id=25e4b5ca-b1b8-4074-b7f2-ad8c394b1096`) | `...wp_s6_incremental_ingestion_the_massive_repo_unlock` | "nightly re-ingest of a 1M-LOC monorepo touches only changed files" | Exact-identifier/structural — one specific WP among 15 sibling sections |
| Q10 | According to the roadmap, what has to happen before the reranker sub-task in Phase 4 can proceed? | `DOCS/audit/07-Roadmap.md` (`ingestion_id=99c65ffc-17bc-4329-83ad-f4bd8e3d8cb4`) | `...phase_2_75_rag_quality_baseline_empirical_precedes_any_phase_4_reranker_work` | "WP-S8's reranker sub-task in Phase 4 either proceeds with evidence or is explicitly deferred with a recorded reason" | Semantic paraphrase requiring cross-reference between Phase 2.75's exit criteria and Phase 4's WP-S8 line — no shared exact phrasing with the question |

**Checkpoint (per tasks.md):** corpus ingested, 10-question set defined and
reviewable — independent of any measurement being run yet (spec.md SC-001,
SC-002).

---

## Scenario 2 Dry Run (T007)

Executed 2026-08-27 against **Q3** ("Which functions call `train_dog`?",
expected `canonical_id = kennel.py#run_demo`) — chosen as the pilot because
it's the one question purpose-built (per `smoke_repo`'s own README) to
exercise graph expansion, giving the dry run the best chance of exercising
every field in the diagnostic record, not just the easy ones.

### Procedure followed

1. **Source presence** — two-step check: `GET /v1/graph/repos/{repo_id}/nodes?canonical_ids=kennel.py%23run_demo`
   (metadata) → found; `POST /v1/vectors/search-by-doc` with
   `document_id=e99f66fa-9249-424d-a2a7-c26b2960cbdf` (vector) → 1 chunk
   returned. **Present.**
2. **Seed rank** — embedded the query text directly via local Ollama
   (`mxbai-embed-large:latest`, matching the embedder config), then
   `POST /v1/vectors/search` with `k=20` and the **same `metadata_filter`
   shape production actually sends** (see finding below — this mattered).
3. **Expanded rank** — called production `POST /v1/rag` at `top_k=1` and
   `top_k=5` and read `retrieval_plan.expanded_canonical_ids`.
4. **Duplicate count** — inspected the top-20 candidate set for repeated
   `canonical_id`/near-identical `chunk_text`.
5. **Repo leakage** — reran the identical query vector scoped to an unrelated
   repo (`TradeForge`, `repo_id=d2fcf1f0-...`) and confirmed zero
   `smoke_repo`-related hits in its own top-20.
6. **End-to-end answer quality** — read `/v1/rag`'s `answer` field against the
   expected fact (that `run_demo` calls `train_dog`).

### Diagnostic Record — Q3 (pilot)

| Field | Value |
|---|---|
| `source_present_in_index` | **true** |
| `seed_rank` | **6** of 20 (see finding #1 — would be rank 4 if the intended code-only filter actually applied) |
| `expanded_rank` | Absent from seed at `top_k=1`; recovered via graph expansion at `top_k=5` (`expanded_canonical_ids: ["kennel.py#run_demo"]`) |
| `duplicate_count` | 3 near-identical chunk pairs among top-17 (see finding #2) — 6 of 17 slots are duplicate content |
| `repo_leakage` | **false** — confirmed zero cross-repo hits |
| `end_to_end_answer_quality` | **pass** at both `top_k=1` and `top_k=5` (correct answer: `run_demo`) |

### Findings surfaced by the dry run (not fixed — recorded per Constitution Compliance)

**Finding 1 — code-path seed filter never matches (confirmed bug, not a
tuning issue).** `rag_orchestrator/src/core/service.py`'s `hybrid_retrieve()`
sends `metadata_filter={"doc_type": "code", "repo_id": repo_id}` for every
code-repo query. But `vector_chunks.doc_type` (a typed column per WP-S4B,
written from `source_metadata.get("doc_type")` at ingest time — see
`pgvector_store.py` `add()`) is **never** `"code"` for code artifacts; the
ingestion pipeline writes `"python source"`. The intended marker
(`"source_type": "code"`) exists only inside the JSONB `source_metadata`, not
as a promoted typed column, and isn't what's being filtered on. Confirmed
live: `vector-store-service` logs show **two** `/v1/vectors/search` calls per
`/v1/rag` request — the primary `doc_type="code"` filter returns empty every
time, silently triggering the documented fallback
(`service.py`: *"No code chunks found... Falling back to repo-scoped
search"*), which drops `doc_type` filtering entirely. Net effect: the
"code-only seed search" ADR-045 describes never actually runs as code-only —
every code query's seed set is contaminated with markdown chunks from the
same repo competing for the same top-k slots. Measured impact on this
question: `kennel.py#run_demo` ranks 6th instead of 4th once two README
chunks (rank 3–4) crowd in. This is systemic — it affects every code-repo RAG
query in the system, not just this one question.
**Not fixed here** (Constitution Compliance / spec.md Non-Goals — a
production retrieval-path change is out of scope for this evaluation).
**Filed as [issue #64](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/64).**

**Finding 2 — near-duplicate chunk crowding, `smoke_repo`'s README.**
`README.md` (this repo) has exactly one top-level heading, so the Markdown
section extractor produces two document nodes — the root `markdown_module`
(`README.md`) and its sole `markdown_section`
(`README.md#smoke_repo_live_smoke_test_fixture`) — whose text is
near-identical (same source, same chunk boundaries). Both get embedded and
persisted independently, so 3 chunk-index pairs (6 total chunk rows) carry
duplicate content and occupy 6 of the top-17 candidate slots for this query.
Not a bug in the general sense (module-root + single-section duplication is
an inherent consequence of "one H1, no sub-sections" Markdown files under the
current extractor design), but a real instance of the "duplicate crowding"
failure mode §2 of the methodology asks about. Recorded, not fixed.

### Assessment: is the procedure ready to run across all 10 questions?

**Yes, with one adjustment carried into T008:** seed-rank measurements for
*code* questions must use the same `metadata_filter` shape production
actually sends (repo_id-only, since the `doc_type` filter never contributes)
— not an idealized code-only filter — so the recorded `seed_rank` reflects
what production really returns, warts included. Both findings above are
now expected background conditions for every code question in this corpus,
not anomalies specific to Q3; T008-T013 should record them as they recur
rather than re-discovering them each time.

**Checkpoint:** dry run complete, procedure validated end-to-end, two
real conditions identified for the full pass to account for. Stopping here
per tasks.md before running T008 across all 10 questions.

---

## Scenario 2 Full Pass (T008-T013)

Executed 2026-08-27 across all 10 questions, one pass per question per the
methodology's "single pass per question" rule (so T008-T013 are reported
together below, not as six separate sweeps). Procedure per question: same
as T007's validated dry run — direct `/v1/vectors/search` with the query's
own embedding for `seed_rank` (code questions scoped by `repo_id` only, per
T007's finding that `doc_type` never contributes; document questions scoped
by `{"source_type": {"ne": "code"}}`, matching what `/v1/rag/simple` itself
sends), then the actual production endpoint (`/v1/rag` for code at
`top_k=5`, `/v1/rag/simple` for documents at `top_k=5`) for `expanded_rank`
and `end_to_end_answer_quality`, judged by hand against each question's
expected fact/passage from the Known-Answer Question Set above.

**Source presence (T008/T009):** all 10 expected `canonical_id`s confirmed
present in `document_nodes` before any ranking was measured. **Zero
ingestion-defects** — every question proceeds to full ranking.

### Diagnostic Record

| ID | `source_present` | `seed_rank` (of top-20) | `expanded_rank` | `duplicate_count` | `repo_leakage` | `end_to_end_quality` |
|---|---|---|---|---|---|---|
| Q1 | true | 2 | present in seed (`top_k=5`) | 4 (see note) | false | **pass** |
| Q2 | true | 1 | present in seed (`top_k=5`) | 4 | false | **pass** |
| Q3 | true | 6 | recovered via expansion | 4 | false | **pass** |
| Q4 | true | 12 | absent even after expansion (see note) | 4 | false | **pass** |
| Q5 | true | 17 (last of 17) | recovered via expansion | 4 | false | **pass** |
| Q6 | true | 1 | n/a (`/v1/rag/simple`, no expansion needed) | 0 | n/a — no repo scoping on `/v1/rag/simple` (see note) | **pass** |
| Q7 | true | 3 | n/a | 0 | n/a | **FAIL** |
| Q8 | true | 2 | n/a (recovered via `DEFINES`-edge expansion, see note) | 0 | n/a | **pass** |
| Q9 | true | 2 | n/a | 0 | n/a | **pass** |
| Q10 | true | 1 | n/a | 0 | n/a | **pass** |

**9 of 10 pass end-to-end. One failure: Q7.**

### Notes on individual rows

- **`duplicate_count = 4` for every code question (Q1-Q5), not a per-question
  variation** — this is a static property of the corpus, not something that
  changes with the query: `smoke_repo`'s `animals.py` has exactly one
  top-level symbol (the `Animal` class), so its module-level chunk and
  `animals.py#Animal`'s class-level chunk are near-identical text (same
  pattern as T007 Finding 2's `README.md` module/section duplication, which
  contributes 3 of the 4 groups here). This is an inherent consequence of
  ADR-039's "artifact is the embedding unit" applied to a file with exactly
  one top-level symbol — not a bug, but a real, reproducible instance of the
  "duplicate crowding" condition the methodology's decision table asks about.
- **Q4 — absent from index vs. absent from top-20, kept distinct.** The
  *exact* expected artifact (`dogs.py#Dog.speak`) never appears in the
  seed or expanded set at `top_k=5` — but `dogs.py#Dog` (the containing
  class, whose embedded text includes the `speak` method's full body and a
  docstring naming the override) is retrieved, and the model answered
  correctly from that. `source_present_in_index` is **true** (confirmed
  independently via `document_nodes`, unrelated to retrieval rank) — this is
  a retrieval-rank fact about one specific artifact, not an ingestion defect,
  and since `end_to_end_answer_quality = pass`, no Failure Classification
  applies (data-model.md: classification is only for failed questions). Not
  a bug, but a real illustration of why "expected canonical_id absent" and
  "question failed" are different questions — the parent-artifact containment
  from ADR-039's whole-block embedding papered over the miss.
- **Q6/Q7/Q8/Q9/Q10 — `/v1/rag/simple` has no repo/document scoping by
  design** (confirmed in `simple_service.py`: `SimpleRAGQuery.repo_id` is
  accepted but never passed to `run_simple_rag()`; the vector search is
  global across all non-code content). "Repo leakage" in the ADR-030 sense
  doesn't apply here — there's no boundary to violate, so `n/a` rather than
  `false`. **Also worth recording:** `run_simple_rag()` filters on
  `{"source_type": {"ne": "code"}}` — the field name issue #64 is filed
  against — confirming issue #64 is specific to `hybrid_retrieve()`'s
  code-query path, not a repo-wide inconsistency.
- **Q8 — preserving the distinction the user asked for.** Per the earlier
  review note: this question's expected content lives inside the
  `README.md#rag_foundry_universal.architecture` chunk because of the
  unclosed-code-fence condition recorded in the T004/T005 section above
  (**source content exists in the stored chunk; structural heading
  segmentation is wrong — "Service URLs" never became its own node**). That
  is distinct from "absent from index" (it isn't — the fence-merged chunk is
  present and was retrieved, rank 2) and distinct from "present, correctly
  chunked, but ranked too low" (it isn't mis-ranked; the structural boundary
  itself is wrong, not the rank). Retrieval surfaced the merged chunk
  correctly and the model successfully extracted the specific port/endpoint
  fact from within it — **pass**, despite the structural defect. Recorded
  explicitly so a future reader doesn't misattribute this pass (or a
  potential future fail on similar content) to embedding or reranking.

### Q7 — the one failure, examined

**Question:** "What ANN index does the vector store use for similarity
search, and what was its measured p95 latency in the Phase 1 benchmark?"
**Expected:** HNSW, p95 ≈ 62 ms (README.md Key Features: *"p95 ≈ 62 ms in
the Phase 1 benchmark"*; corroborated by README.md's own Performance section:
*"Vector search p95 (HNSW, filtered, k=10) | 61.7 ms"*).

**What happened:** at `top_k=5`, the production seed set included **both**
correct chunks — `README.md#rag_foundry_universal.key_features` (rank 3) and
`README.md#rag_foundry_universal.performance_phase_1_baseline` (rank 2) —
alongside two chunks from `DOCS/audit/04-Scalability-Plan.md`'s WP-S4 section
(rank 1) and WP-S2 section (rank 5). The model's answer named the ANN index
correctly (HNSW) but reported the wrong latency figure — **"seconds
(seq scan)" / "< 100 ms"** — a number belonging to a *different* row in
04-Scalability-Plan.md's WP-S4 capacity table (`Vector search p95 @ 1M
chunks | seconds (seq scan) | < 100 ms`, a before/after scaling projection,
not the actual measured Phase 1 result), even though both chunks stating the
correct ~62 ms figure were present in the same context window.

**Classification (per methodology §2 decision table):** relevant evidence
was already in the top 3 of the retrieved context, but the answer is wrong —
this is **`top-3-but-poor-answer`**, a generation/context-assembly problem,
**not** a retrieval or reranker problem. Retrieval did its job; the model
picked the wrong number out of a context that contained two chunks with
superficially similar "p95 latency" phrasing but different values for
different things. Queued for Scenario 3's clean-context test (T014-T017).

---

## Scenario 3: Clean-Context Test (T014-T017, combined)

Only one question failed end-to-end (Q7), so T014's dry run and the full
T015-T017 pass are the same single case, recorded together below rather
than as two separate passes.

**Procedure (research.md Decision 4):** hand-picked the 2 known-correct
chunks — `README.md#rag_foundry_universal.key_features` and
`README.md#rag_foundry_universal.performance_phase_1_baseline`, the exact
`vector_chunks.chunk_text` for each, verbatim, no retrieval involved — joined
as `context`, and called the existing `llm_service` `POST /generate` with
`{context, query}`: the same endpoint and shape production uses, so its
response provenance (`model`, `model_alias`, `provider`, `prompt_template`)
is the real one, not bypassed. Called twice (cold, then warm with the
identical payload) to get both latency figures.

### Clean-Context Score — Q7

| Field | Value |
|---|---|
| `grounding` | **pass** — both runs assert only what's in the supplied context, no fabrication |
| `citation` | **pass** — both runs explicitly quote and attribute to "Key Features" and "Performance (Phase 1 baseline)", by name |
| `omission` | **pass** — both runs report both the index type (HNSW) and the exact figure (61.7 ms), and correctly note the Key Features section's "≈62 ms" is a rounding of the Performance table's precise 61.7 ms rather than treating them as two different numbers |
| `latency_cold` | 33.29 s |
| `latency_warm` | 12.88 s |
| `model` / `model_alias` / `provider` | `ollama/Qwen3:4b` / `default` / `ollama` |
| `prompt_template` | `rag_answer.v1` |

**Answer (warm run):** *"The vector store uses an HNSW (cosine) ANN index for
similarity search... The measured p95 latency in the Phase 1 benchmark is
61.7 ms, as confirmed by the performance table..."* — fully correct on both
the index type and the latency figure, in both runs.

### What this confirms

With the distractor chunk (04-Scalability-Plan.md's WP-S4 capacity-table row,
a *different* p95 figure describing a different, hypothetical scaling
scenario) removed and only the two correct chunks supplied, the same model
answers **completely correctly, twice**. This confirms the Scenario 2
classification precisely: Q7 is **not** a fundamental generation-capability
problem (the model can ground and cite correctly when given clean evidence)
and **not** a retrieval-rank problem (the correct chunks were already top-3
in production). It's specifically a **multi-document context-composition /
distractor problem** — production's context assembly presented two chunks
with superficially similar "p95 latency" phrasing but different referents
(actual measured baseline vs. a scaling-plan's before/after projection table)
side by side, and the model conflated them. Confirms the methodology's
`top-3-but-poor-answer` bucket's guidance: the next lever is prompting or
context assembly (e.g., surfacing which document/section each chunk came
from more saliently, or a stricter same-topic filter), not a reranker —
reranking cannot fix distractor confusion when the correct chunk is already
top-3.

**T017 completeness check:** confirmed — the clean-context test above was
run for exactly one question (Q7). No `POST /generate` clean-context call
was made for any of Q1, Q2, Q3, Q4, Q5, Q6, Q8, Q9, or Q10 — all nine passed
`end_to_end_answer_quality` in Scenario 2, so per spec.md FR-004 there is
nothing to isolate for them. No production code or configuration was
changed to run this test — `/generate` was called exactly as production
calls it, with only the `context` argument substituted.

**Checkpoint:** Scenario 3 complete — the corpus's one failure has a
recorded Clean-Context Score (spec.md SC-004); no passing question was
tested (there were none to skip here, only the one failure). Stopping here
per plan, before Scenario 4's classification pass and verdict.

---
