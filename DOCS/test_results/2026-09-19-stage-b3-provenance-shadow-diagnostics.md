---
title: "Stage B3: provenance shadow diagnostics -- live verification and findings"
date: 2026-09-19
type: test-results
status: complete
tags: [phase-6, provenance, issue-199, stage-b3]
related:
  - "[ADR-053](/DOCS/adr/ADR-053-source-authority-provenance-model.md)"
  - "[Spec 008](/specs/008-source-authority-provenance/spec.md)"
  - "[Status](/DOCS/status.md)"
---

# Stage B3: provenance shadow diagnostics

## Scope and constraint

Per explicit owner direction: B3 is a **diagnostic/shadow pass only**.
No universal provenance score, no broad hard filtering, no change to
ranking/selection/prompt/generation behavior. Any rule must be
query-purpose-aware and deterministic. The goal of this pass is to
record where provenance-aware diagnostics would help (and would not
wrongly suppress useful evidence) using the real, currently-ingested
corpus (`shared/`, `repo_id=3ab62236-f1c3-50d8-ba49-0e434a34c0c3`,
local docker-compose stack) -- not to activate any policy.

`provenance_diagnostics.py` is a pure function
(`diagnose_manifest(claim_type, manifest)`) consulted only when a
caller explicitly supplies an optional `claim_type` on `POST /v1/rag`;
omitted (the default), it runs zero code and changes nothing.

## Verification: zero contamination (the core claim)

Same query, same repo, same `top_k`, run twice -- once without
`claim_type`, once with `claim_type=implemented_behavior`:

| | without `claim_type` | with `claim_type` |
|---|---|---|
| `final_context_manifest` canonical_ids (order preserved) | `[ChunkerFactory, ChunkerFactory, ChunkerFactory, ChunkerFactory.choose_strategy, ChunkerFactory.choose_strategy, ChunkerFactory.get_chunker]` | **identical** |
| `retrieval_plan.provenance_diagnostics` key present | No | Yes (6 findings, all `concerns: []`) |

`final_context_manifest` was byte-identical between the two calls
(`==` on the parsed JSON lists). The LLM-generated `answer` text
differed between the two calls, as expected from ordinary generation
sampling variance -- not from `claim_type`, since the context string
sent to `/generate` was built from the identical manifest in both
cases.

An invalid `claim_type` (`"nonsense"`) is rejected with HTTP 422 by
Pydantic's `Literal` validation before reaching any retrieval code.

## Clean case: real implementation, no concerns

`claim_type=implemented_behavior` against the `ChunkerFactory` query
above: every one of the 6 manifest entries reads role=`implementation`,
subject=`selected_repository`, and all 6 diagnostic findings have
`concerns: []` -- confirmed against the actual persisted `document_nodes`
rows, not just the pure unit tests.

## Finding: a real classifier gap, surfaced by shadow mode exactly as intended

Querying `claim_type=repository_overview` against `"What does this
codebase do?"` returned, among the top matches,
`smoke_repo/README.md#smoke_repo_live_smoke_test_fixture` --
content from `shared/smoke_repo/`, a directory whose own name and
contents (`dogs.py`, `kennel.py`, an `Animal`/`Dog`/`Kennel` toy demo)
mark it as a live-smoke-test fixture, unrelated to what this codebase
actually does. This is exactly the "embedded subject substituted for
the real repository" failure mode ADR-053/#199 exists to catch.

**The diagnostic did not flag it.** Its persisted provenance reads
`role=unknown_mixed`, `subject=selected_repository` -- not
`example_fixture`/`embedded_subject` -- because the Stage B1 classifier's
fixture rule (`provenance_classifier.py::_FIXTURE_PATH_RE`) only matches
a `fixtures/`/`examples/` path segment, and `smoke_repo/` matches
neither. Checked directly against `document_nodes`: **zero** rows in
this corpus classify as `example_fixture`/`embedded_subject` at all,
confirmed by `select role, subject, count(*) ... group by role, subject`.

This is a genuine, measured finding, not a synthetic worry: the current
Stage B1 rule set has a real blind spot for fixture content that isn't
under a conventionally-named directory. Because this ran in shadow
mode, the gap cost nothing -- no evidence was suppressed, no answer
changed, no false confidence was introduced. It is exactly the kind of
signal this stage exists to surface before any of it becomes a policy
Stage C could rely on.

**Fixed as a separate, deliberate follow-up** (not bundled into this
pass): `provenance_classifier.py`'s `_FIXTURE_PATH_RE` now also matches
`smoke_repo`/`smoke_tests` directory segments (`CLASSIFIER_VERSION`
bumped `role-subject-v1` -> `role-subject-v2`), scoped to exactly the
observed gap -- not broadened to unobserved patterns like `demo`/
`sample`/`mock`. Re-verified live after re-ingesting `shared/`:
`smoke_repo/`'s 15 nodes now classify `role=example_fixture`,
`subject=embedded_subject` (0 before the fix), the other 252 nodes'
classification is unchanged, and the same `repository_overview` query
that previously showed `concerns: []` for `smoke_repo/README.md` now
correctly reports `["embedded_subject_in_overview"]`. 2 new classifier
unit tests. See `ingestion_service/tests/codebase/test_provenance_classifier.py`.

## What this does and does not establish

**Established**: the shadow-diagnostic mechanism works correctly
end-to-end against real ingested data and a real HTTP call path
(request → retrieval → manifest → diagnostics → response), provably
without affecting selection, and it already found one real classifier
gap worth a human decision.

**Not established**: this pass used a single, small, non-fixture-rich
local corpus (`shared/`, 267 nodes classified as `implementation`/
`unknown_mixed` only). A broader pass against the full self-repo corpus
(already ingested in production, `repo_id=f7641840-...`, 8881 nodes,
which does contain `tests/fixtures/`, `docs-archive/`, and `DOCS/adr/`
content matching every rule) would give a much richer sample of
true-positive/true-negative cases across all four claim types. That
pass has not been run yet -- recommended as the next step once this PR
is deployed, mirroring how Stage A5's local pass was followed by a
fuller production pass in this same session.

## Recommendation

Keep this fully opt-in (no default-on switch exists to flip). The
`smoke_repo` classifier gap has since been fixed and re-verified live
(see above) -- `role-subject-v2`. Stage C (authority-aware sufficiency)
should not be started from this alone; it needs the fuller-corpus pass
this document explicitly
does not claim to have completed.
