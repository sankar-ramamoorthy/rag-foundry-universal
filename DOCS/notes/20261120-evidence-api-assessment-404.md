---
title: "Evidence API assessment for the first slice and the peri-Foundry agent (#404)"
date: 2026-11-20
type: note
status: proposed
summary: "Read-only assessment. Most evidence primitives exist, but they are spread across three services with no shared envelope, no structured citations and no exposed investigation surface. A bounded investigation harness already exists inside execution_policy.py and should be reused, not replaced. Proposal only; nothing here is authorized."
tags: [assessment, evidence-api, first-slice, agent, issue-404, phase-6]
related:
  - "[Issue #404](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/404)"
  - "[ADR-057](/DOCS/adr/ADR-057-react-typescript-product-frontend.md)"
  - "[Frontend API assessment update](/DOCS/notes/20261123-frontend-api-assessment.md)"
  - "[Source navigation contract](/DOCS/architecture/source-navigation-api.md)"
---

# Evidence API assessment (#404)

This assessment records the November 20 baseline. See the
[current frontend API assessment](/DOCS/notes/20261123-frontend-api-assessment.md)
for the implemented contracts, later validation evidence and remaining release gaps.

Method: read-only inspection of `main` at e58264c plus the ADR-057 branch (the
LAB assessed bf5d680, which differs from main only by that ADR). No code run,
no model calls, no database access. **Observed** means seen in code at the
cited path; **Proposal** means design suggestion.

Limits: I cannot read the LAB repository, so I have not seen its eight Mealie
development questions or its gap list in full; the seven gaps below come from
the request and are each checked against code. The "Locate" row is therefore
unmeasured, not failing.

## 1. Capability matrix

| Capability | Exists | Works (evidence) | Unvalidated or missing | Where |
| --- | --- | --- | --- | --- |
| Orient (inventory) | Yes, deterministic, no model | Byte-identical per generation; returns `commit_sha`, languages, manifests, services, gaps | Does not establish repository purpose: no README or prose is read. Facets are inventory only | `ingestion_service/src/api/v1/orient.py`, passthrough `GET /v1/repos/{id}/orient` in orchestrator |
| Locate files | Yes | Glob over current generation, paged, exact-path result with `document_id` | Not measured on natural-language locate questions | `GET /v1/repos/{id}/source/files` |
| Locate definitions/symbols | Partial | Python inventory via AST over paged reads (verified, zero model calls, #396) | No symbol lookup or definition search endpoint; the source API explicitly excludes it. Inventory is Python-only and is reachable only through `/rag` recognition, not a direct endpoint | `execution_policy.py:285`, `inventory_query.py` |
| Locate by meaning | Yes | Vector search over artifacts | Returns RAG passages with an internal manifest, not a locate result | `service.prepare_rag_evidence` |
| Read source | Yes | Strict: generation fence, 500-line cap, LF lines, `returned_text_sha256` verified by the harness | Code types only (`SOURCE_TYPES`: python, typescript, javascript, rust, java). README and Markdown cannot be read. `commit_sha` is in the response model; whether the source reads populate it is unverified. Reached only on ingestion_service directly, not through the orchestrator | `ingestion_service/src/core/source_navigation.py:26` |
| Hybrid retrieval | Yes | Vector seeds, graph expansion, final-context manifest with provenance | Expansion reporting is partial (below) | `service.py:1112` |
| Expansion frontier | Partial | `retrieval_plan` has seed ids, expanded ids, `expanded_docs_considered` vs `used`, per-document relation type | No list of declined candidates or reasons; `retrieval_plan` is an unversioned `Dict[str, Any]`, so its shape is not a contract | `service.py:1112`, `models.py:61` |
| Structured citations | No | `RAGResponse.sources` is `List[str]` labels (canonical_id, then relative_path, then document_id) | No file, line range, generation or digest per citation. The manifest has some of this internally | `agent_adapter.py:19-54` |
| Generation and commit on responses | Partial | Source reads, orient and `retrieval_plan.generation_id` carry generation | `RAGResponse` has no top-level generation or commit; `commit_sha` is nullable; no common envelope | `models.py:56` |
| Bounded investigation | Exists, not exposed | `execution_policy.py`: tool allowlist (orient, find_source, read_source, search_evidence), evidence ledger, decisions log, budgets (tool calls, model calls, bytes, wall time), stop reasons (`termination_reason`), generation re-verified around each call, duplicate-action guard, completion states | Only the `python_inventory` family is wired to an endpoint. The `execution_trace` family needs an injected model proposer and is not reachable over HTTP. No frontier output | `execution_policy.py:19-404` |
| Evidence workflow with sufficiency | Yes | `POST /v1/repos/{id}/evidence` for orient, trace, impact with an assessment, steps, stop reason | Modes are fixed; no question-aware mode | `evidence_service.py`, `routes.py:378` |
| Relationships (trace, impact) | Exist | Bounded hops, gap notes, truncation flags | Coverage and correctness not validated; #373 is paused. Per the request, exclude until validated | `routes.py:144,202` |

### Review of `execution_policy.py` (overlap with the agent)

Observed. It is already a small bounded harness, and what it does is what the
agent's tool layer needs: a tool allowlist with validated arguments, a
generation fence checked before and after every call, a ledger of admitted
evidence, citation validation (findings must point at ledger ids), and
explicit stop reasons.

It also contains an LLM-driven loop (`next_step`, an injected `propose`
callback). That part is the agent's job under the agreed boundary: the agent
owns strategy. **Proposal:** keep the tool dispatch, ledger and stop
reasons; do not expose the model-proposer loop as a Foundry endpoint. Do not
write a second orchestrator.

## 2. Proposed minimum contract (logical, not four new routes)

Common response envelope on every evidence response (**Proposal**):
`schema_version`, `repo_id`, `generation_id`, `commit_sha` (nullable, stated),
`coverage` (`complete | partial | unknown`), `limitations[]`.

| Capability | Proposal |
| --- | --- |
| `orient` | Existing ORIENT plus an optional bounded purpose-evidence section (README excerpt as a source range) once Markdown is readable. Same envelope. |
| `locate` | One request that returns candidate files and definitions with canonical id, path, line range and the reason matched (glob, name, or semantic). Built from existing file discovery, Python inventory and vector search. Language coverage stated in `coverage`. |
| `read_source` | Existing source read, exposed through the orchestrator under the common envelope, with `commit_sha` populated where known and `returned_text_sha256` retained. Markdown and docs readable (needs a decision, §4). |
| `investigate` | Bounded, question-aware retrieval, no model proposer: runs the existing search and expansion, then returns `ledger` (admitted passages with citation), `frontier` (candidates seen but not admitted, with reason code), `limitations`, `stop_reason`, and budgets used. No state kept between calls. |
| Citation | Structured object: `repo_id`, `generation_id`, `path`, `start_line`, `end_line`, `canonical_id`, `text_sha256`. Added alongside `sources`, which stays unchanged. |

Excluded until validated: relationships (trace/impact) as agent tools.

## 3. Dependency-ordered plan

Milestone here means the roadmap phase, as plain text (no GitHub milestones).
All are **Phase 6**. Each needs its own issue before code.

| # | Proposed issue | Depends on | Size | Notes |
| --- | --- | --- | --- | --- |
| 1 | Evidence envelope and schema version on existing evidence responses (additive) | none | small | Smallest step, unblocks the rest; Spec Kit spec |
| 2 | Structured citation object, additive to `sources` | 1 | small | Needed by both the agent and the React "open file at lines" experience |
| 3 | Expose read_source and file/definition locate through the orchestrator under the envelope | 1 | small to medium | Reuses `dispatch` and the inventory path |
| 4 | Locate diagnostic on the LAB's eight Mealie questions (read-only measurement) | 3, and an evaluation question set supplied by the owner | small | Measures Locate before building more |
| 5 | `investigate`: ledger, frontier with decline reasons, limitations, stop reason | 1, 2, 3 | medium | Reuses `execution_policy` ledger and stop reasons; ADR needed |
| 6 | Make Markdown and README readable by source read | decision A | medium | Changes `SOURCE_TYPES` and the accepted ADR-055 supplement |
| 7 | Orient purpose evidence | 6 | small | |
| 8 | Relationships as tools | #373 validation | deferred | |

Suggested first authorization: 1, 2, 3 and 4 together, since 4 tells us
whether 5 is the real bottleneck or Locate is.

Correction to earlier advice in this session: a bounded paged-inventory issue
is not needed. #396/#397 already delivered it on main; the restart note that
suggested it predates that work.

## 4. Decisions that need the owner

- **A. Markdown readability.** Allow source reads of Markdown and docs? This
  reverses a deliberate fail-closed choice in ADR-055's supplement, and
  README evidence for Orient depends on it.
- **B. Where `investigate` lives.** Foundry-side, deterministic, no model (my
  proposal), or Foundry also runs a model-proposer loop. The second keeps
  strategy in Foundry and conflicts with the agreed boundary.
- **C. Endpoints versus one tool surface.** Separate routes, or one endpoint
  with an operation field. Affects the generated TypeScript client.
- **D. Language scope of `locate` definitions.** Python only for now, or
  tree-sitter inventory for TypeScript, Rust and Java in the first cut.
- **E. Envelope breaking risk.** Additive fields only, or a new versioned
  route family.
- **F. Question set for item 4.** Foundry does not read the LAB, so the owner
  decides which questions item 4 uses and how they reach this repository.
