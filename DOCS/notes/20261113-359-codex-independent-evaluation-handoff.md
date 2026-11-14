---
title: "#359 handoff to Codex: independent sealed ground truth for the C7 routes and the mealie held-out set"
date: 2026-11-13
type: working-note
status: current
tags: [handoff, evaluation, ground-truth, overfitting, codex, issue-359, issue-342]
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[#359 protocol (frozen)](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)"
  - "[ADR-054: evaluation dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[ADR-031: canonical identity model](/DOCS/adr/ADR-031-canonical-identity-model.md)"
  - "[Retrieval-side handoff](/DOCS/notes/20261112-code-intelligence-342-354-handoff.md)"
---

# #359 handoff to Codex: independent sealed ground truth

This note is addressed to **Codex** as the independent ground-truth author
named in protocol §9.1. It restates what the frozen protocol requires and adds
only file formats and logistics. **If this note and the protocol disagree, the
protocol wins**; report the disagreement on #359 rather than resolving it.
Roadmap: Phase 6.

## 1. The frozen protocol

| Item | Value |
|---|---|
| File | `DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md` |
| Merged commit on `main` | `45f34e1` (PR #360, squash) |
| Git blob | `1ce2a0520aad30b8f20a541bb95d6c217df49ac1` |
| sha256 (repository bytes, LF) | `ca1d1ed5f192910c78ad7a179fb75f3131a6f796f2b3d27244698212c5049535`, computed as `git show 45f34e1:<file> \| sha256sum` |

A Windows checkout with `core.autocrlf=true` has CRLF bytes and a different
hash, so always hash the `git show` output. The front matter still reads
`status: draft`; that is the literal text of the frozen version, which
"freezes on merge". It is left unedited so the hash stays valid.

## 2. What Codex produces

Two independent sets, each with **three files**:

| Set | Repository @ source commit | Minimum questions |
|---|---|---|
| **C7** (within-repo check) | `rag-foundry-universal` @ `9f039c43604b2e96a6f96351e00afa178c9c81f8` (the source of the frozen generation `8cbedbb9`; no service code has changed between it and `45f34e1`) | 3 |
| **H** (held-out, C10) | `mealie-recipes/mealie` @ `1624c22bf70988c7fe404ad586e2f9689f77748d` | 3 (protocol default: same procedure as §9.1) |

For each set:

1. **`questions.json`, public.** Routes and question text only. Claude may
   read this.
2. **`oracle-entry-points.json`, sealed.** One handler canonical ID per
   question, and nothing else.
3. **`expected-chains.json`, sealed.** The ground truth in the §4 format.

### 2.1 Working rules (protocol §9.1, §5a, ADR-054 §3)

- **Work from implementation source at the pinned commit.** Do not use the
  existing diagnostic reports (`DOCS/test_results/*342*`, `*345*`, `*354*`,
  the #358 report, or §4 of the protocol) as a source for chains.
- **Do not use this project's graph, `/trace`, eligibility script or
  retrieval output to choose routes or write chains.** Choose them from the
  source as a developer would. If our extractor produced no route node or no
  handler node for a route you chose, Stage RI or ORACLE-ENTRY reports that,
  and that report is a legitimate result, not something to avoid.
- **Do not look at any selection output** before posting your hashes. None
  exists yet.
- **Do not tune anything.** You are not asked to make the system pass. Pick
  routes because they are real entry points with non-trivial implementation
  chains (at least 3 repository functions reached), not because they look
  easy or hard for this system.

### 2.2 C7 route eligibility (`rag-foundry-universal`)

*Unstudied* (protocol §9.1) excludes `POST /v1/rag`, `POST /v1/vectors/search`
and every route already named in an earlier #342, #345, #354 or #359 document.
A scan of those documents on 2026-11-13 found these, which are excluded **with
any HTTP method**:

- `/v1/rag`
- `/v1/vectors/search`, `/v1/vectors/search-by-doc`, `/v1/vectors/retag`,
  `/v1/vectors` (batch)
- `/v1/repos` (list), `/v1/repos/{repo_id}` (including `DELETE`)
- `/v1/repos/{repo_id}/generation`, `/v1/repos/{repo_id}/evidence`,
  `/v1/repos/{repo_id}/trace`, `/v1/repos/{repo_id}/orient`
- `/v1/graph/repos/{repo_id}`
- `/v1/ingest-repo`

**Conservative addition:** every route whose handler lives in
`ingestion_service/src/api/v1/repos.py`, because #361 examined that file's
source. The owner may relax this on #359.

Any other HTTP route in the four services is eligible. Spread the three routes
over **at least two services** where the source allows it.

### 2.3 Question text

RI receives **only the question text**, never the `route` field. So that a
question names its entry point the way the primary case does, each question:

- names the route as `METHOD /path`, using the **full public path a client
  calls**, including any router prefix (for `mealie`, whatever the source
  shows a client actually calls; do not rewrite it to suit our extractor);
- asks for the execution path from that route to its implementation, in the
  same shape as the primary question:

  > Trace the execution path from POST /v1/rag through the orchestrator to
  > vector retrieval. Identify the actual Python functions and files involved,
  > explain the call sequence, and distinguish direct function calls from HTTP
  > service calls. Base the answer on implementation code rather than
  > documentation or historical reports.

  Replace the route and the "through … to …" clause with what is true for
  your route. Do not add function or file names to the question.

## 3. File formats

All files are UTF-8, LF line endings, with no trailing whitespace. Hashes are
`sha256sum` of the exact bytes.

**`questions.json`**

```json
{
  "set": "C7",
  "protocol": {"commit": "45f34e1", "sha256": "ca1d1ed5f192910c78ad7a179fb75f3131a6f796f2b3d27244698212c5049535"},
  "repository": "sankar-ramamoorthy/rag-foundry-universal",
  "source_commit": "9f039c43604b2e96a6f96351e00afa178c9c81f8",
  "author": "codex",
  "questions": [
    {"qid": "C7-1", "route": "GET /v1/example", "question": "Trace the execution path from GET /v1/example …"}
  ]
}
```

**`oracle-entry-points.json`** (sealed): `{"set": "C7", "entry_points": {"C7-1": "<path>#<Qualified.name>"}}`.
Canonical IDs follow ADR-031: a repository-relative path, `#`, then the
qualified symbol name (`Class.method` for methods). No other content is
allowed in this file.

**`expected-chains.json`** (sealed). One object per question, with one row per
expected relationship, matching the columns of protocol §4 plus the 5a
resolution class:

```json
{
  "set": "C7",
  "chains": {
    "C7-1": [
      {
        "id": "R1", "tier": "core",
        "caller": "<canonical ID>",
        "relationship": "plain-language description",
        "callee": "<canonical ID, or the external target (URL path, SQL, provider)>",
        "witness_regex": "<Python regex>",
        "lines": [62],
        "resolution_class": "route | static_direct | indirect_reference | dynamic_dispatch | cross_service_http | external_http | sql",
        "dispatch_candidates": ["<only for dynamic_dispatch>"],
        "configured_by": "<only for dynamic_dispatch: the relationship id that establishes the concrete target>"
      }
    ]
  }
}
```

Rules for the chains (from §4 and §5a):

- **Witness rule.** A relationship is supported only when `witness_regex`
  matches a delivered passage of the **caller**. Write the regex against the
  caller's own source. Prefer a regex that matches only code. If it also
  matches a docstring or comment in the same caller, list the code lines
  in `lines` and add a `"note"`.
- **Verify every witness** against the source at the pinned commit, and record
  the line numbers.
- **Tiers.** `core` covers the relationships the question demands. A PASS
  requires every core relationship (§6), so do not mark incidental calls as
  core. State the core and supporting counts per question.
- **Never resolve ambiguity by guessing** (5a). For abstract or overridden
  dispatch, record `dynamic_dispatch` with all candidates and the relationship
  that configures the real target.
- **Routes.** The entry route is a `route` relationship from the handler,
  with the decorator as its witness.

## 4. Sealing order (protocol §9.1; the owner confirms each step on #359)

| Step | Who | Action |
|---|---|---|
| 1 | Codex | Add `questions.json` for the set under `DOCS/evaluations/359-<set>/` (with a `.gitattributes` pinning LF) through a PR, and post its sha256 on #359. |
| 2 | Codex | Write `oracle-entry-points.json` and `expected-chains.json` **outside this repository** (see §5). Post **only** their two sha256 values on #359. |
| 3 | Claude | Runs Stage RI and ES under E2E with the frozen rules, and posts the outputs' sha256 on #359. |
| 4 | Codex | Reveals `oracle-entry-points.json` (posts the file, or adds it in a PR). Claude verifies the hash, runs ES under ORACLE-ENTRY, and posts those outputs' sha256. |
| 5 | Codex | Adds `expected-chains.json` to `DOCS/evaluations/359-<set>/`. Scoring verifies the hash and refuses to score on a mismatch. |

Any break in this order is reported, and the affected question is reclassified
as development data (§9.1, ADR-054 §6).

## 5. Keeping the sealed files sealed

Claude Code on the owner's Windows laptop can read any file under the user's
home directory, so a convention alone is weak isolation. Recommended, in
order of strength:

1. Keep the sealed files on a machine or account Claude Code does not run on.
2. Or add a `permissions.deny` rule for `Read` on the sealed directory in the
   owner's Claude Code settings before step 2, and remove it at step 4 or 5.

Do not put sealed files in this repository, in `DOCS/test_results/_raw/`, in a
branch, or in an issue comment before their reveal step.

## 6. Prerequisites before ingestion or execution

These are open and need the owner's decision or action. None of them changes
the frozen rules or scoring.

| # | Prerequisite | Blocks | Owner |
|---|---|---|---|
| P1 | **Self-repo generation stays `8cbedbb9`.** Do not re-ingest `rag-foundry-universal` until the C7 run is scored, or the run aborts (§3). | C7 run | owner |
| P2 | **Ingest `mealie` @ `1624c22` on the Linux host** and record the ready generation ID. That ID, the commit, the questions, expected evidence, scoring (this protocol), budgets and service SHAs make up the ADR-054 §5 freeze. | H run | owner |
| P3 | **Who checks sealed witnesses against stored text.** §7 step 1 aborts on a §4 witness missing from stored text, but for C7 and H Claude cannot see the witnesses before step 5. Proposed: Codex checks its own witnesses read-only against the ready generation's stored node text before posting hashes at step 2, and records the result inside `expected-chains.json`. The scoring step then repeats the check, and a missing witness voids that question rather than being edited. **Needs owner confirmation**, because the protocol only states this check for §4. | step 2 | owner |
| P4 | **A0 has no query vector for new questions.** A0 runs "with the stored query vector", which exists only for Step 0, and §10 forbids embedding calls. Options: (a) report A0 as *not run* for C7 and H (A0 is only a reference arm), or (b) authorize one embedding call per question. Recommended: (a). | A0 on C7/H | owner |
| P5 | **Passage-source vector.** §3 fixes the stored Step 0 vector as the `search-by-doc` ranking vector. Passages are used in `chunk_index` order, so this changes nothing unless a document has more than 100 chunks. It will be applied literally to C7 and H, and any such document will be reported. | none (note) | — |
| P6 | **Sealed-file isolation** as described in §5. | step 2 | owner + Codex |
| P7 | **The diagnostic harness does not exist yet.** It needs a selection module that does not import the ground truth, a scoring module, the C3 scan test, and raw-record writing with sha256. It goes in through its own PR **before** step 3 and must not change any retrieval behaviour. The C3 scan can include sealed terms only after their reveal; it is re-run then, and a hit invalidates the affected outputs. | step 3 | Claude, on approval |
| P8 | **Service SHAs.** The run records `git_sha` before and after (§3). The Linux stack must be serving `9f039c4` or later with no service-source change. `45f34e1` qualifies, because only docs and scripts changed. | runs | owner |

## 7. What is not authorized yet

- Running the diagnostic, on the self-repo or anywhere else.
- Any retrieval, ranking, query-planning, context-budget, generation or
  configuration change.
- Changing or tuning the selection rules. Changing the protocol creates a new
  version (C2, C9).
- Claude ingesting anything. The owner runs all ingestion.
