---
title: "CI-01 investigation: generation-bound graph snapshots"
date: 2026-11-10
type: investigation
status: proposed
source_commit: 1a8fd58721417a452f5951d393875119e6d22a7f
scope: "Repository graph export, cache identity, and structural consumers"
authority: "Investigation and proposed contract clarification; implementation requires owner authorization under an issue and milestone"
verification_status: "Source review, 14 existing offline tests, and four synthetic probes; no live PostgreSQL or HTTP concurrency reproduction"
tags: [audit, investigation, code-intelligence, generation, snapshot, sdd]
related:
  - "[November 10 architecture audit](/DOCS/audit/2026-11-10-code-intelligence-architecture-audit.md)"
  - "[Independent review and response](/DOCS/audit/2026-11-10-code-intelligence-independent-review-and-response.md)"
  - "[Production correctness specification](/specs/005-production-correctness/spec.md)"
  - "[WP-R3 lifecycle specification](/specs/005-production-correctness/issues/lifecycle.md)"
  - "[WP-R5 freshness specification](/specs/005-production-correctness/issues/freshness.md)"
  - "[ADR-050: lifecycle consistency](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md)"
  - "[ADR-051: generation-aware cache](/DOCS/adr/ADR-051-generation-aware-graph-cache.md)"
  - "[Synthetic reproduction script](/DOCS/test_results/2026-11-10-ci01-synthetic-probe.py)"
---

# CI-01: Generation-bound graph snapshots

> [!abstract] Recommendation
> Clarify the existing WP-R3/WP-R5 specification, propose a narrow graph-export
> contract within `specs/005-production-correctness/contracts/`, and amend
> ADR-050/051 through review. The existing intent already prohibits partial or
> mixed-generation evidence. This investigation exposes an unproven composition
> of those guarantees; it does not establish that the project failed to use SDD.

## 1. Question and decision boundary

Can a successful repository graph export and the cache entry derived from it
identify one completed generation from which every returned node and relationship
was read?

The investigation determines the specification work needed before implementation.
It does not change accepted ADRs, frozen experiment specifications, application
code, data, or deployment. CI-02/CI-04 remain independently investigable; CI-06 and
CI-03 are not prerequisites for resolving this graph contract.

The source baseline is `1a8fd58721417a452f5951d393875119e6d22a7f`.
No production services, held-out inputs, candidate execution or attempt markers
were accessed. The added probe is an investigation artifact, not a production fix.

## 2. What the existing specifications already require

| Existing authority | Requirement or decision | What remains insufficiently established |
| --- | --- | --- |
| [WP-R3 lifecycle](/specs/005-production-correctness/issues/lifecycle.md) and [ADR-050](/DOCS/adr/ADR-050-repository-lifecycle-consistency.md) | Determine the actual graph owner, gate on completed status, and expose rebuild unavailability rather than partial generations. | Owner selection, completion status, nodes and relationships need a common read-consistency boundary. |
| [WP-R5 freshness](/specs/005-production-correctness/issues/freshness.md) | Invalidate stale caches and avoid mixing generations within a request. | A separate generation lookup does not identify a later export's data. |
| [ADR-051](/DOCS/adr/ADR-051-generation-aware-graph-cache.md) | One query, one generation; cheap warm-cache checks; bounded cache; generation remains metadata rather than canonical identity. | The assertion that cold exports already establish data consistency needs stronger evidence; the export does not carry generation identity. |
| [Production correctness plan](/specs/005-production-correctness/plan.md) | Generation changes during queries cause retry/failure rather than silent combination. | Its wording differs from WP-R5/ADR-051's suggestion that an in-flight request finishes on A. Define this distinction at graph versus whole-request scope. |
| [Lineage endpoint contract](/specs/006-incremental-ingestion-lineage/contracts/repo-generation-lineage.md) | Enrich the generation lookup with revision and lineage. | Source commit and lineage do not certify a separately fetched graph snapshot. |

ADR-050 and ADR-051 are **accepted**. Their issue-spec pages still contain older
delivery wording such as proposed/merge-pending; those historical status lines do
not override the ADRs' recorded acceptance. A targeted clarification should preserve
history and link the follow-up rather than imply the original work never shipped.

The existing specification is not silent about consistency. Its desired outcome
is stronger than the current export/cache protocol proves. The appropriate SDD
response is to make the invariant observable and test its composition.

## 3. Reconstructed code path

1. [Cache lookup](/rag_orchestrator/src/retrieval/codebase_utils.py#L231) calls
   `get_repo_generation(repo_id)`, obtaining a separately resolved generation A.
2. A matching warm entry is returned. Otherwise the cache calls
   `load_graph_for_repo(repo_id)` without passing an expected generation.
3. [The loader](/rag_orchestrator/src/retrieval/codebase_queries.py#L330) reads
   nodes and relationships from the full export, but does not retain its status
   or generation identity. [FullGraphResponse](/ingestion_service/src/api/v1/graph.py#L36)
   exposes `generation_status`, but has no generation ID.
4. [The route](/ingestion_service/src/api/v1/graph.py#L149) invokes
   [the database helper](/ingestion_service/src/core/db_utils.py#L532).
   That helper resolves the completed owner in a separate session, then reads
   nodes and relationships in successive queries in another session.
5. Relationships are filtered by the returned nodes' document IDs. The writer's
   [upsert transaction](/ingestion_service/src/core/codebase/codebase_persistence.py#L193)
   preserves IDs of surviving canonical artifacts and replaces relationships.
   Stable IDs therefore do not fence relationships to the nodes' generation.
6. The cache inserts the loaded graph under the earlier A label, without checking
   the export's actual identity or status.

The writer transaction provides atomic publication of its changes. It does not
alone provide one snapshot across successive reader statements. The
[engine/session factory](/ingestion_service/src/core/database_session.py#L11)
does not explicitly request repeatable-read isolation. The deployed database's
effective isolation was not queried. Under statement-level snapshots, a commit
between the node and edge reads can expose different committed versions.

### Consumer protection and its limits

[Direct TRACE/IMPACT](/rag_orchestrator/src/api/v1/routes.py#L161) consume the bare
cached graph, with no equivalent outer generation fence or generation field in
their constructed responses. The cache's unavailable-to-empty behavior can lead
to a symbol-not-found response, which does not establish source absence.

[Evidence TRACE/IMPACT](/rag_orchestrator/src/core/evidence_service.py#L211)
compare the cache label to the initially resolved generation and verify the
generation afterward. [Ordinary RAG](/rag_orchestrator/src/core/service.py#L1096)
also verifies its selected generation. Those checks mitigate forward rebuild
races and must be preserved; this investigation does not demonstrate that these
workflows routinely return mixed evidence. They are not a substitute for an
accurately labeled, internally consistent graph export.

## 4. Reproductions and verification limits

Run the checked-in [synthetic probe](/DOCS/test_results/2026-11-10-ci01-synthetic-probe.py)
from the repository root:

```powershell
.\.venv\Scripts\python.exe DOCS/test_results/2026-11-10-ci01-synthetic-probe.py
```

The script selects unchanged function/class definitions from source using AST,
executes the actual cache, loader and database-helper bodies, and replaces only
their external seams with synthetic values. It avoids application startup and
all HTTP/database connections. Its query mocks supply rows; they do not execute
SQL filters, isolation or writer transactions.

| Probe | Controlled sequence | Observed result |
| --- | --- | --- |
| P1: identity mismatch | Cheap check returns A; subsequent export has a B-only node. | Returned label A, node `B-only`, cached label A. |
| P2: readiness discarded | Cheap check returns A; subsequent export says `building` with empty data. | Empty graph is returned and cached under A. |
| P3: modeled database interleaving | Owner A; node query returns A's x/y; next query supplies B's CALL edge on the same document IDs. | Helper returns A nodes with B-tagged edge metadata and `ready`. |
| P4: owner disappears before nodes | Owner A resolved; node query returns no rows after modeled replacement/deletion. | Helper reports an empty result as `ready`, without a new status check. |

P1/P2 reproduce cache/loader control-flow gaps. P3/P4 show what the database helper
accepts at its seams, not that PostgreSQL has been observed producing that schedule.
P3 models surviving node IDs; dropped edges whose endpoints disappear can also
look like reduced coverage, but that additional case was not executed here.

Existing offline tests were run from `rag_orchestrator/`:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_graph_cache_generation.py tests/test_repo_generation_lookup.py -q
```

**Result: 14 passed in 0.73s.** They validate sequential cache invalidation,
eviction, no-generation behavior and lookup degradation. Their passing result
coexists with P1/P2 because the mocked graph loader is assumed to match the preceding
lookup. Existing [generation endpoint integration tests](/ingestion_service/tests/api/test_repo_generation_integration.py)
and [lifecycle tests](/ingestion_service/tests/core/test_repo_lifecycle.py)
cover important stable-state transitions; they were read, not rerun here. They
do not establish this export/cache interleaving contract.

## 5. Proposed contract for review

The following is a candidate clarification, not an adopted contract:

**For every successful ready graph export, there exists one database snapshot S
and generation G such that the repository owner and completed status, all returned
node versions and all returned relationship versions were read consistently from
S; the response identifies G, and consumers never cache that response under a
different generation.**

- `ready` means ready at the identified read snapshot. A later rebuild does not
  retroactively corrupt an already materialized, correctly identified graph.
- The response should carry `repo_id`, a generation ID using the existing
  `ingestion_id` vocabulary, status, nodes and relationships. An ID must come
  from the same read boundary as the content, not an independent lookup.
- An optional expected-generation request should either return exactly that
  generation or reject the mismatch. Because storage retains only the current
  graph, it cannot promise retrieval of historical A after B replaces it.
- A missing/mismatched identity or non-ready export must not create a ready cache
  entry. Loading clients must validate the envelope before discarding metadata.
- Distinguish a legitimately empty ready snapshot, if supported by lifecycle
  semantics, from unavailable, unknown and changed state. Do not manufacture a
  ready empty graph when previously resolved rows vanish.
- Warm-cache reuse still uses the cheap check. A fully materialized A can be used
  as an A snapshot; whole-request policy may separately reject generation drift.
- Direct structural APIs should expose the snapshot identity and distinguish
  unavailable data from a symbol absent in a successfully analyzed graph.
- Preserve the RAG/evidence outer fences. Their graph/vector/passage composition
  remains a separate broader obligation; this graph-only correction cannot prove
  all evidence paths are generation-consistent by itself.

Suggested HTTP choices are 409 for an expected-generation conflict and a documented
retryable unavailable outcome for non-ready data. Exact status mapping, schema
nullability and behavior for older services require review. An identity-missing
legacy response cannot silently satisfy the stronger guarantee; service rollout
compatibility needs an explicit policy.

## 6. Alternatives and recommendation

| Alternative | Benefits | Costs and limits |
| --- | --- | --- |
| Single repeatable-read transaction spanning owner/status/nodes/edges, plus export envelope and client validation | Directly establishes one snapshot without retaining multiple graph generations. | Owner helpers must share the transaction; long full exports retain old row versions and consume connections. Confirm actual isolation and materialization boundaries. |
| One composed SQL statement producing a generation-bound graph result | One statement snapshot can bind all data. | More complex export/serialization query, potential large result aggregation and memory costs. |
| Reader/writer locking protocol plus envelope | Can serialize readers against mutation. | Every relevant writer/delete path must participate; may block long exports or ingestion. Existing writer locks alone do not protect readers. |
| Add a response generation label or compare lookup before/after loading only | Smaller surface change. | Does not alone establish consistent node/edge/status reads; external checks cannot repair already mislabeled content. |
| Multi-generation storage with staged activation | Historical reads and improved availability. | Much broader lifecycle/schema/cleanup work; ADR-050 explicitly excludes this requirement. |

Investigate the first alternative as the default candidate, with a bounded export
transaction and explicit expected-generation validation. This is a recommendation,
not an implementation selection. Compare it against a single-statement approach
using real query behavior. Avoid acquiring a repository-wide lock for an entire
query or LLM request as an incidental consistency fix.

## 7. Required acceptance evidence before claiming closure

| Scenario | Observable acceptance |
| --- | --- |
| Stable generation | Ready export identifies G and returns G's nodes and relationships; warm cache avoids full refetch. |
| Rebuild between lookup and export | Either consistently identified expected A, or an explicit conflict/unavailable response; never B cached as A. |
| Rebuild between owner resolution and node query | A coherent snapshot or explicit failure; no ready empty result caused solely by the race. |
| Rebuild between node and edge queries | A real PostgreSQL barrier-controlled test yields one generation's node and edge versions or failure. Use shared IDs and changed edge metadata. |
| Building, failed, deleted and unknown | No authoritative ready cache entry; consumers expose the documented status rather than treating unavailability as source absence. |
| Concurrent cold loads and force reload | Each successful entry's label matches its own payload; an older completion cannot bypass the next freshness check. Coalescing loads is optional performance work. |
| Direct TRACE/IMPACT and evidence/RAG consumers | Identity survives into the relevant result or fence, and mismatches do not produce supported-looking results. |
| Transport/legacy envelope failure | No unvalidated cache insertion; degradation or retry is explicit under the chosen compatibility policy. |

Use actual route/loader/cache composition with a local HTTP fixture for the
lookup/export race, plus real PostgreSQL transactions and deterministic barriers
for the database race. Do not rely only on sleeps or mocked isolation. Test rollback,
completion timing, and reader cleanup. Keep output limits and timeouts distinct
from CI-02 and CI-07; do not expand this fix into an unrelated scaling rewrite.

## 8. SDD disposition and next authorization boundary

1. **Clarify existing specs:** Add the observable snapshot invariant and race
   scenarios to the WP-R3/WP-R5 follow-up. Reconcile finish-on-A versus retry
   wording by distinguishing a materialized graph from a multi-service request.
2. **Propose a narrow contract:** Add `repository-graph-snapshot.md` under the
   existing production-correctness specification's `contracts/` directory. Define
   envelope, expected-generation semantics, unavailable outcomes, compatibility
   and consumer responsibilities. This proposed path is not created here.
3. **Amend existing ADRs through review:** ADR-050 should describe the reader's
   snapshot boundary; ADR-051 should require identity from the actual export and
   correct its unsupported sufficiency claim about a separate lookup. Preserve
   their history, accepted decisions and zero-downtime non-goal. A new ADR is
   warranted only if a materially different storage/publication design is chosen.
4. **Then authorize implementation:** Create an issue linked to #166/#168 and
   CI-01 under the owner-selected existing milestone, with acceptance criteria
   and an isolated branch/PR. Existing CI, PostgreSQL race tests and deployment
   evidence remain separate gates. No issue or milestone is created by this report.

The investigation supports targeted implementation once the contract and issue
are approved. It does not justify a graph-store replacement, canonical-ID change,
new planning methodology, or a general claim that all SDD guarantees failed.
