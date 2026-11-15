---
title: "Protocol: graph completeness and correctness, routes and call resolution (#373)"
date: 2026-11-14
type: evaluation
status: proposed
summary: "Pre-registered, read-only protocol for #373. It measures route-node completeness against an independently authored static route reference (M1), how call sites in in-repository functions are represented (M2), and whether resolved CALL edges point to the right target (M3). The corpora are the self-repository, mealie (regression only) and two new repositories chosen by a frozen structural rule. Freezes on merge; the status field is deliberately left unedited after merge so the file hash stays valid. No execution is authorized until frozen."
tags: [evaluation, protocol, code-intelligence, graph, call-resolution, routes, overfitting, issue-373, issue-359]
related:
  - "[Issue #373](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/373)"
  - "[#359 final report and recommendation](/DOCS/test_results/2026-11-14-359-final-report-and-recommendation.md)"
  - "[#359 held-out mealie results](/DOCS/test_results/2026-11-14-359-H-mealie-held-out-results.md)"
  - "[ADR-031: canonical identity](/DOCS/adr/ADR-031-canonical-identity-model.md)"
  - "[ADR-032: symbol resolution and call graph](/DOCS/adr/ADR-032-symbol-resolution-call-graph.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
---

# Protocol: graph completeness and correctness (#373)

**This protocol freezes on merge to `main`.** From then on, any change makes a
new protocol version, and results under both versions are reported. Nothing
in it authorizes an extractor, retrieval, configuration or corpus change.

## 1. Purpose

#359 located its failures in the graph:
- route identification failed on all three `mealie` routes;
- with the correct handler supplied, every lost relationship was "not
  discovered", and the handlers' onward calls ended at `EXTERNAL_SYMBOL`
  nodes.

That is three questions in one repository. This protocol measures what the
graph represents, across four repositories, before any repair is chosen.

It measures three things separately:
- **M1, route-node completeness:** do framework-declared routes have route
  nodes with the correct public path, method, handler and service scope?
- **M2, call-site representation:** how is each call site in an
  in-repository function represented? How many internal calls are
  represented as external, or not represented at all, and in which
  resolution category?
- **M3, resolved-edge correctness:** do resolved in-repository CALL edges
  point to the right target?

**Coverage (M1, M2) and correctness (M3) are reported separately.** An added
edge is not an improvement if it is wrong.

## 2. Evidence class (ADR-054)

| Repository | Class | Disclosure |
|---|---|---|
| Self (`f7641840-ba13-5f9d-9ae6-87e1f924709d`) | Development | Heavily studied (#342, #354, #359). The protocol author has seen its graph |
| `mealie` (`7da95a1b-11dc-5f74-8d3b-fabe24489ad7`) | **Regression and diagnostic only** | Its #359 answers and graph counts are known. It is not held-out |
| N1, N2 (selected under §4) | Diagnostic | Unseen at freeze. They become development material once measured |

**No result under this protocol is a generalization claim.** A later claim
that an extractor change generalizes requires a different, newly sealed
held-out repository (§11).

## 3. Fixed inputs

| Input | Value |
|---|---|
| Self generation | `8cbedbb9-9ad6-4c63-83f7-2b7d7659f7e5`, commit `9f039c43604b2e96a6f96351e00afa178c9c81f8` |
| `mealie` generation | `611fce96-93f4-4869-b176-2ab668fd2483`, commit `1624c22bf70988c7fe404ad586e2f9689f77748d` (pinned fork `sankar-ramamoorthy/mealie`) |
| N1, N2 generations | recorded on #373 at ingestion (§9 step 3) |
| Services | `/version` of all four services, recorded at every stage |
| **Extractor identity** | the git tree ID of `ingestion_service/src/core` at the ingestion service's deployed `git_sha`, plus per-file sha256 of `ingestion_service/src/core/extractors/**`, `ingestion_service/src/core/codebase/{graph_assembler,symbol_table,service_topology,structural_inventory,module_conventions,identity,ir,repo_graph_builder}.py`, and the tree-sitter query files. There is no extractor version identifier (#313), so this is the identity. `PYTHON_TREESITTER_*` settings are recorded when the owner supplies them; otherwise they are recorded as `unobserved` |
| Python for the census | the interpreter version that runs the harness, recorded |

**Comparability rule.** All four generations must share one extractor
identity, and self and `mealie` were both ingested at `9f039c4`. N1 and N2 must
therefore be ingested by a deployment whose `ingestion_service/src/core` tree ID
equals the one at `9f039c4`. If that is not possible, the difference is
recorded, and cross-repository comparisons involving N1 and N2 are labelled
`different_extractor_identity`.

## 4. Selection of N1 and N2 (frozen; structural only)

The rule is applied by an independent selector (Codex, as in #359), not by
the protocol author. The selector must not ingest candidates, run our
extractor on them, or look at execution paths or graph outcomes. Eligibility
is decided only from repository metadata and plain-text search of the source
tree.

1. **Candidate pool.** Run the GitHub repository search
   `topic:fastapi language:Python stars:>=200 archived:false fork:false pushed:>=2025-11-14`,
   sorted by stars (descending), and take the first 100 results. Record the
   query, timestamp and full result list as a JSON snapshot, with its sha256.
2. **Order.** Sort the pool by `sha256(protocol_sha256 + ":" + full_name)`
   ascending, where `protocol_sha256` is this file's frozen hash. This removes
   popularity and the selector's preference from the order.
3. **Eligibility.** Walk the ordered pool and take the first two candidates
   that meet every condition below. Each condition is checked at the
   candidate's default-branch HEAD, which becomes its pinned commit.
   - **E1:** an OSI-approved licence in the GitHub licence field.
   - **E2:** 150–2,500 in-scope Python files (§5.1).
   - **E3:** `fastapi` is declared as a dependency in `pyproject.toml`,
     `setup.cfg`, `setup.py` or `requirements*.txt`.
   - **E4:** at least 20 matches of `@\w+\.(get|post|put|delete|patch|api_route)\(`
     in in-scope files, **and** at least one `include_router(` call or
     `APIRouter(` call with a `prefix=` argument.
   - **E5:** not on the exclusion list: self, `mealie`, LightRAG, hatch,
     werkzeug, pdfminer.six, code-graph-rag, py-coding-agent, the E1 corpora,
     any repository owned by the project owner, and any repository named
     anywhere under `DOCS/`.
   - **E6:** a shallow clone of at most 500 MB.
4. **Owner review.** The owner reviews the two selections for identity and
   resources before ingestion. A rejection must state its reason, and the
   next eligible candidate in the order is taken. Every rejection is recorded.
5. **Record.** The selector posts on #373 the snapshot hash, the ordered
   list, each candidate's eligibility outcomes up to the second selection,
   and the two pinned commits.

**Ingestion** is the owner's action, through pinned forks with the default
branch set to the pinned commit, as with `mealie`. The generation is verified
read-only: ready, full, non-incremental, at the recorded commit.

## 5. Populations

### 5.1 In-scope files (all measurements)

- **In scope:** tracked `.py` files at the pinned commit.
- **Excluded** (counted, never measured), where any path component matches:
  - `test`, `tests`, `testing`, `fixture`, `fixtures`, `example`, `examples`;
  - `migrations`, `alembic`;
  - `vendor`, `third_party`, `site-packages`;
  - `docs`, `doc`.

  Also excluded: file names `test_*.py`, `*_test.py`, `conftest.py`.
- **Parsing:** every in-scope file is parsed with Python's `ast`. A file that
  fails to parse is **NOT_EVALUABLE** (`parse_failure`), with its call sites
  uncounted and reported by file.

### 5.2 Call-site census (M2, M3)

The harness enumerates call sites from the pinned source with Python's `ast`.
It does not import or use any ingestion-service code.

- **Unit:** every `ast.Call` node whose innermost enclosing scope is a
  function or method (`def` or `async def`), including nested functions.
  Calls inside lambdas and comprehensions belong to the enclosing function.
- **Excluded:** module-level and class-body calls (counted, not measured).
- **Recorded per site:** relative path, `lineno`, `col_offset`, the enclosing
  qualified name (`Class.method`, `outer.inner`, `Outer.Inner.method`), the
  callee expression text, the **simple name** (the `attr` of an
  `ast.Attribute` or the `id` of an `ast.Name`, else `None`), and the
  receiver text when the callee is a dotted name.
- **Caller identity:** `<relative_path>#<qualified name>` (ADR-031).

### 5.3 Syntactic strata (fixed, mechanical)

| Stratum | Callee form |
|---|---|
| S1 | bare name `f(...)` |
| S2 | `self.m(...)` or `cls.m(...)` |
| S3 | `self.a.m(...)` (attribute chain of depth ≥ 2 on `self` or `cls`) |
| S4 | dotted name whose head is a parameter of the enclosing function |
| S5 | dotted name whose head is bound by an `import` in the same file |
| S6 | any other dotted name (head is a local or other name) |
| S7 | non-name receiver (call result, subscript, literal, etc.) |

Strata come from the syntax alone, never from the graph.

## 6. Matching the census to the graph

The graph is read from the pinned generation's export
(`GET /v1/graph/repos/{repo_id}`, with its sha256 recorded) and node lookup.
For each call site:

1. **Caller indexed?** If no graph node has the caller identity, the site is
   `G_caller_missing`.
2. **Matching edges.** Find CALL edges from the caller whose
   `relationship_metadata.call_sites` contains the site's line (§6.1) and
   whose target simple name equals the site's simple name. The target simple
   name is:
   - the last dotted segment for `EXTERNAL_SYMBOL:<dotted>`;
   - otherwise the last segment of the target's qualified name; a class
     target matches a constructor call by class name.
3. **Graph outcome:**

| Outcome | Condition |
|---|---|
| `G_resolved` | exactly one matching edge, to an in-repository node, with `confidence` 1.0 |
| `G_global` | exactly one matching edge, to an in-repository node, with `confidence` 0.5 (unique-global, ADR-032 layer 4) |
| `G_external` | exactly one matching edge, to an `EXTERNAL_SYMBOL` node |
| `G_none` | the caller is indexed but no edge matches |
| `G_multi` | more than one edge matches (reported, not sampled) |
| `G_caller_missing` | see step 1 |

Sites with simple name `None` (some S7 forms) can only be `G_none` or
`G_caller_missing` under this rule. They are reported as a separate row.

### 6.1 Line convention (fixed before any corpus is read)

The harness PR includes a test that runs the repository's own
`GraphAssembler` on a synthetic fixture written for the test. It establishes
whether `call_sites` line numbers are 1-based like `ast.lineno`, and how
multi-line calls are numbered. The resulting rule is fixed in harness code.
This is not a corpus measurement.

## 7. Measurements

### 7.1 M1: route-node completeness

**Reference (option B, primary).** An independent author (Codex) writes a
**static route enumeration** for each repository from the pinned source
alone. The author does not see graph exports, route nodes or any output of our
extractor. **No repository code is executed.** Option A (the framework's
runtime route table) is not used without separate owner authorization.

Each reference route records:
- the method;
- the full public path;
- the handler canonical ID (`path#qualname`);
- the service;
- the derivation: every prefix contribution, with `file:line`;
- the declaration style: decorator on a router, decorator on the app,
  `add_api_route`, class-based or controller, or other;
- a confidence label (§7.4).

**Option C (fallback).**
- Applies when routes the author labels `uncertain` exceed 10% of a
  repository's reference.
- The author deep-audits a fixed random sample of `min(30, uncertain count)`
  of them, still from source only, with the seed per §8.
- The audit upgrades each sampled route's confidence or marks it
  **NOT_EVALUABLE** (`route_reference_uncertain`).
- Unsampled uncertain routes are NOT_EVALUABLE.

**Service scope.**
- In a repository with several deployable services (compose services, or
  separate application packages), the reference service is the one whose
  build context contains the handler file.
- Scope is **correct** when the reference services map one-to-one onto graph
  service identifiers.
- In a single-application repository, scope is recorded as `n/a`.

**Path normalization for matching.**
- A trailing `/` is removed, except for `/`.
- Path-parameter names are replaced by `{}`. A match that also has identical
  parameter names is reported as well.

**Classification of each reference route** against graph route nodes
(`route:<service>:<METHOD>:<path>`) and their `HANDLED_BY` targets:

| Class | Condition |
|---|---|
| `exact` | the method and normalized full path match, and `HANDLED_BY` targets the reference handler |
| `prefix_missing` | same method and handler; the graph path is a proper suffix of the public path |
| `path_mismatch` | same method and handler; another path, not a suffix |
| `handler_mismatch` | the method and full path match, but the handler differs |
| `absent` | no route node with this method has this handler or this path |
| `ambiguous_scope` | matching route nodes exist under more than one graph service |

Graph route nodes that match no reference route are counted and listed as
`extra`.

**Breakdowns:**
- number of prefix contributions: 0, 1, ≥ 2;
- declaration style;
- service.

**Denominator:** reference routes labelled `certain` or `probable`, after any
option-C upgrades.

### 7.2 M2: call-site representation

**Census table.** For every repository, give counts of every graph outcome
(§6) by stratum (§5.3), plus the excluded and NOT_EVALUABLE counts. This
needs no audit.

**Blind audit for true targets.** For a sample of call sites (§8), the
auditor (Codex) determines from the source **what each call actually
targets**. The auditor is **not shown the graph outcome**, and M2 and M3
samples are shuffled into one sheet. The auditor sees only:
- the file, line, column and enclosing function;
- the call expression;
- the pinned source.

For each site, the auditor records:
- **true class:**

  | Class | Meaning |
  |---|---|
  | `T_internal` | an in-repository definition. The auditor gives its canonical ID; a constructor call gives the class |
  | `T_external` | stdlib, builtin, third-party package or framework |
  | `T_dynamic` | an internal target that cannot be determined statically: several runtime possibilities, reflection, or configuration-selected |
  | `T_ambiguous` | two or more named in-repository candidates, listed |
  | `T_unverifiable` | cannot be established from the pinned source |

- **resolution category,** for `T_internal`, `T_dynamic` and `T_ambiguous`:
  `module_qualified_import`, `instance_attribute`, `dependency_injection`,
  `constructor`, `callback_or_background_task`, `other_dynamic_dispatch`,
  `other`. The first matching category is used, in that order;
- **a confidence label** (§7.4).

**Derived M2 classes** for sampled `G_external` and `G_none` sites:

| Graph | True | M2 class | Defect? |
|---|---|---|---|
| `G_external` | `T_internal` | **internal represented as external** | yes: coverage |
| `G_none` | `T_internal` | **internal not represented** | yes: coverage |
| `G_external` or `G_none` | `T_external` | legitimately external | no |
| `G_external` or `G_none` | `T_dynamic` | statically unresolvable | no: a limit, reported separately |
| any | `T_ambiguous` | ambiguous | no: reported separately |

`G_caller_missing` sites are reported as their own coverage finding: the
caller is not indexed, as with C7-1's nested function. They are not sampled.

**Estimates.**
- For each stratum h (syntactic stratum × graph outcome), the population
  count N_h is known and n_h is audited.
- The class share is p̂_h, with a 95% Wilson interval.
- The estimated total is Σ N_h · p̂_h. Its 95% interval comes from 2,000
  stratified bootstrap resamples with the seed from §8.
- Estimates are reported per resolution category.

### 7.3 M3: resolved-edge correctness

- **Population:** call sites with outcome `G_resolved` or `G_global`.
- **Sample:** per §8, shuffled into the same blind audit sheet.
- **Comparison:** the harness compares the graph target with the auditor's
  `T_internal` target.

| Outcome | Condition |
|---|---|
| `correct` | the targets are identical |
| `equivalent` | the graph targets the class and the auditor names its `__init__`, or the reverse. Reported separately; counted as correct for precision |
| `mismatch` | anything else, including an auditor class other than `T_internal` |
| excluded | `T_unverifiable` (excluded from the denominator) |

**Adjudication of mismatches.** This is a second, non-blind review of each
mismatch by the auditor, with the graph target shown. Each mismatch is
labelled:
- `wrong_target`: the graph is wrong;
- `wrong_scope_or_override`: the graph names a base or override where the
  call binds elsewhere;
- `auditor_error`: the graph is right; the result is then reclassified
  `correct`, and the count is reported;
- `not_a_call`.

Disagreements the auditor cannot settle go to the owner. Every reversal is
recorded.

- **Precision** = (correct + equivalent) / (sampled − unverifiable), with a
  95% Wilson interval, per repository and per `confidence` (1.0 vs 0.5).
- **Correctness gate (frozen):** if the upper bound of the 95% interval falls
  below 0.90 in any repository and confidence stratum, the first-fix
  recommendation (§10) must address correctness in that path before any
  change that adds edges.

### 7.4 Confidence labels (M1 reference and the M2/M3 audit)

| Label | Rule |
|---|---|
| `certain` | determined by literals in the pinned source, with the lines cited; no runtime value involved |
| `probable` | needs a configuration default or assignments followed across at most 2 files; exactly one plausible answer |
| `uncertain` | depends on environment or runtime values, dynamic registration, reflection or monkeypatching, or has two or more plausible answers |

- Headline figures use `certain` + `probable`.
- `certain`-only figures are reported alongside, as a sensitivity check.
- `uncertain` items are counted and reported, never silently dropped.

### 7.5 NOT_EVALUABLE (reported separately, with reasons)

- `parse_failure`: the file does not parse (§5.1).
- `route_reference_uncertain`: see §7.1.
- `generation_not_pinned`: the generation is not ready, incremental, or not
  at the recorded commit. The repository is not measured.
- `target_outside_source`: the true target lies outside the pinned source
  tree and is not a resolvable external package.
- `T_unverifiable`: see §7.2.
- `language_out_of_scope`: non-Python files. This protocol measures Python
  only; other languages are counted by file.

## 8. Sample sizes and seeds (frozen)

**Per repository:**
- **M2:** 120 call sites drawn from `G_external` ∪ `G_none`, stratified by
  syntactic stratum × graph outcome.
  - Allocation is proportional to N_h, with at least 10 per non-empty
    stratum, or all of a stratum when N_h < 10.
  - The remainder goes by largest remainder.
  - If the strata cannot all reach their minimum within 120, the minimums
    win and the total grows. The final n is recorded.
- **M3:** 80 call sites drawn from `G_resolved` ∪ `G_global`, stratified by
  confidence × syntactic stratum, with at least 8 per non-empty stratum and
  otherwise the same rules.
- **Option C:** `min(30, uncertain)` routes (§7.1).

**Seeds.**
- Each stratum's population is sorted by
  `(relative_path, lineno, col_offset, simple_name)`.
- The draw is `random.Random(seed).sample(population, n_h)`, with
  `seed = int(sha256(f"{protocol_sha256}:{repo_id}:{measurement}:{stratum}").hexdigest()[:16], 16)`.
- The bootstrap seed uses `measurement = "bootstrap"`.
- The audit-sheet shuffle seed uses `measurement = "sheet"`.

**Interval precision these sizes give.** These figures are design
expectations, not results:
- M3 at p = 0.95 with n = 80: a Wilson half-width of about ±5 points;
- M2 at p = 0.5 with n = 10: about ±27 points per small stratum.

Stratum-level estimates in small strata are therefore coarse, and the report
must say so.

## 9. Procedure and integrity

Each step posts its artifact hashes on #373 before the next step begins.

| Step | Action | By | Gate |
|---|---|---|---|
| 0 | Protocol merged and frozen; merge SHA and file sha256 posted | owner | — |
| 1 | Selection of N1 and N2 (§4); snapshot and record hashes posted | Codex | owner review |
| 2 | Harness PR: read-only diagnostic with tests, including the §6.1 line-convention test. Generic code only, no repository-specific rules. Merged before any corpus is read | Claude | CI, owner merge |
| 3 | N1 and N2 ingested through pinned forks, and the generations verified read-only (§3). Self and `mealie` are re-verified unchanged | owner (ingestion), Claude (verification) | generation freeze posted |
| 4 | M1 static route references for all four repositories, written from source only, without graph access; committed under `DOCS/evaluations/373-references/`, hashes posted | Codex | before step 5 |
| 5 | Census and graph matching; strata, populations and samples drawn; blind audit sheets generated. The frame record's hash is posted | Claude (harness) | — |
| 6 | Blind audit of the sheets; labels committed, hash posted | Codex | before step 7 |
| 7 | Scoring: M1 comparison, M2 estimates, M3 comparison, then non-blind adjudication of M3 mismatches (Codex) | Claude, Codex | adjudication hashes posted |
| 8 | Results report under `DOCS/test_results/`, with raw records under `_raw/` indexed in `raw-index.json` | Claude | owner review |

**Every raw record carries:**
- the protocol commit and sha256;
- the harness file hashes;
- the repository ID, URL, pinned commit and tree hash;
- the generation ID and state, before and after;
- the service `/version` output;
- the extractor identity (§3);
- the graph-export sha256;
- the reference and label artifact hashes;
- all seeds.

Records are written once and never overwritten.

**Every call is read-only:** generation, graph export, node lookup and
`/version`. There is no ingestion, embedding, generation or SQL within the
measurement.

## 10. Analysis and the first-fix recommendation

- Results are reported **per repository**. There is no pooled accuracy
  figure across repositories.
- **Route defects (M1)** are the per-repository share of
  `prefix_missing` + `path_mismatch` + `handler_mismatch` + `absent` +
  `ambiguous_scope`, broken down by composition depth and declaration style.
- **Call defects (M2)** are the per-repository estimated count and share of
  in-scope internal call sites (`T_internal`) lost as external or not
  represented, per resolution category, with intervals.
  `G_caller_missing` is reported beside them.
- **Correctness (M3)** is precision per repository and confidence stratum,
  with the §7.3 gate.

**The first fix is chosen by these criteria, applied in order and stated in
the report:**
1. **The correctness gate (§7.3).** If it fails, correctness comes first.
2. **Gating.** A defect that prevents entry, as route defects do for
   route-grounded entry, ranks ahead of a defect of similar size that
   reduces reach after entry.
3. **Size.** Rank by the median across repositories of each category's share
   of internal call sites, reported with each repository's value. A category
   that is large in only one repository is flagged as possibly
   repository-specific.
4. **Risk.** Prefer the fix whose resolution can be made exact without
   guessing (ADR-032's "never silently guess").

The recommendation is not implemented under this protocol.

**Contextual evidence, not a graph measurement.** The #359 primary-case A0
result, in which today's `/v1/rag` path delivered documentation and supported
0/12 core relationships, is restated in the report. Entry and authority belong
to #371. The report must not claim that a graph fix would improve production
retrieval.

## 11. Gates for any later extractor change (outside this protocol)

1. An ADR extending ADR-032 for the chosen resolution change, with an explicit
   false-resolution policy: leave a call unresolved rather than guess.
2. Generic fixtures, not derived from `mealie`, N1 or N2.
3. The reuse identity accounts for extractor behaviour (#313), or
   `force_full_rebuild` is used and recorded.
4. Re-measurement under this protocol version, including M3 precision, so that
   added edges are shown to be correct.
5. Any generalization claim is tested on a **new, independently sealed
   held-out repository**.

## 12. Boundaries

- Read-only. No extractor, retrieval, traversal, ranking, budget or
  configuration change, and no re-ingestion of self or `mealie`.
- No execution of repository code (option A) without separate owner
  authorization.
- Ingesting N1 and N2 is the owner's action, after the step 1 review.
- Out of scope:
  - query planning and the choice of entry mechanism;
  - the cross-service architecture-fact layer (#203);
  - graph scaling (#206);
  - non-Python languages.

## 13. Known limitations of this design

- **The reference is authored by one independent party.** Static
  enumeration can miss dynamically registered routes; those are labelled
  `uncertain`, not guessed.
- **The census uses `ast`, the extractor mainly uses tree-sitter.** Where
  they disagree about what counts as a call site, the difference shows up as
  `G_none`. The audit then decides whether a real call was lost.
- **Matching relies on line numbers and simple names.** Two calls with the
  same simple name on one line in one caller cannot be told apart. Both match
  the same edge, and this is reported as `G_multi` when more than one edge
  matches.
- **Only FastAPI routes are measured in M1,** which is what the route
  extractor supports (#221). Other frameworks would be uniformly `absent`, and
  that would say nothing about composition.
- **Four repositories, two of them already studied.** Category rankings are
  indicative, not population estimates.
