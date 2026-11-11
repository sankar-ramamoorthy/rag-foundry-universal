---
title: "Proposal — Minimal documentation conventions (taxonomy, authority, placement, navigation)"
date: 2026-11-10
type: proposal
status: accepted
tracking_issue: 332
tags: [proposal, documentation, governance, okf, sdd]
related:
  - "[Documentation standard (OKF)](/DOCS/standards/okf-documentation.md)"
  - "[Knowledge-base conventions review](/DOCS/notes/20261110-knowledge-base-conventions-review.md)"
  - "[Documentation index](/DOCS/index.md)"
---

# Proposal — Minimal documentation conventions

Tracked by issue #332. **Accepted by the owner on 2026-11-10**, with the
recommended resolutions below. Binding through the
[amended OKF standard](/DOCS/standards/okf-documentation.md), which carries the
accepted conventions. It adds to the
standard; it does not replace it. Findings are in the
[review note](/DOCS/notes/20261110-knowledge-base-conventions-review.md).

## Principles

- **Preserve existing documents and conventions.** No migration, no renames, no
  new framework. The rules apply to new and substantially edited documents, as
  the standard already says.
- **Authority comes from type + status + explicit relationships, never from
  directory alone.** An investigation under `audit/` is still an investigation;
  an accepted ADR outranks a proposed design wherever either is linked from.
- **Cite, don't restate** (constitution Principle VII applies to every row below).

## 1. Standardized document types and their authority

New documents use one of these `type` values. Existing values stay valid (the
spec permits unknown types), and mapping them is optional when a file is edited.

| `type` | Establishes | Authority |
|---|---|---|
| `standard` | How documentation or process is done | Binding once `accepted` |
| `adr` | An architectural decision | Authoritative for the decided fact when `accepted`; weaker states are not |
| `spec` | Required behavior of a feature (Spec Kit) | Authoritative for that feature's requirements; defers to ADRs on technical facts |
| `proposal` | A change under discussion | None until accepted |
| `investigation` | Evidence from testing a specific hypothesis, toward a decision | Evidence only; never decides |
| `audit` | A point-in-time assessment of a broader system or area | Evidence only |
| `evaluation` | Pre-registered protocols, manifests and fixtures | Binding on the experiment once `frozen` |
| `test-result` | Observed outcomes of a run | Evidence only, tied to the run's stated commit |
| `release-record` | What was deployed, from which commit | Record of fact |
| `status` | Current project state (`DOCS/status.md` only) | The single current-state document |
| `note` | Working notes, handoffs, decision notes | None; promote to ADR or spec if it decides something |

`test-results` is treated as an alias of `test-result`; do not use it in new files.

**Status vocabulary.** The `status` key stays a convention, but new documents use
one value from: `proposed`, `accepted`, `frozen`, `complete`, `superseded`,
`obsolete`. Qualifiers go in a separate `summary` or `notes` key rather than a
compound status (for example `status: complete` plus a sentence on the failed
gate).

## 2. Placement (existing directories only)

| Directory | Holds |
|---|---|
| `DOCS/adr/` | `adr` |
| `specs/NNN-name/` | `spec` and its Spec Kit artifacts |
| `DOCS/proposals/` | `proposal` |
| `DOCS/audit/` | `audit`, and `investigation` that concerns the codebase architecture or an audit finding |
| `DOCS/evaluations/` | `evaluation` (defined before a run) |
| `DOCS/test_results/` | `test-result` (what a run produced) |
| `DOCS/notes/` | `note`, and investigations that are not tied to an audit |
| `DOCS/releases/`, `DOCS/deployment/` | `release-record`, operational guides |
| `DOCS/standards/` | `standard` |

Filenames for new notes use `YYYY-MM-DD-slug.md`; the `YYYYMMDD-` form already in
`notes/` is left as is.

## 3. Navigation and what must be linked

- **`DOCS/index.md`** is the root route: it links each category index and the
  current items a newcomer needs (current spec, accepted ADRs, `status.md`). It
  does not list every document and should not embed result narratives.
- **Category indexes** (`DOCS/audit/00-Audit-Overview.md` and, if created, an
  equivalent for `specs/` and `test_results/`) list their principal members.
  Not every document needs an index entry. The requirement is **predictable
  discoverability**: every new document is reachable from a parent spec,
  investigation, issue, ADR or a category index, through its `related` links.
- **`DOCS/status.md`** links the current spec for any in-progress feature and any
  accepted-but-unimplemented ADR.
- **`DOCS/log.md`** gets an entry when a document changes how the knowledge base
  is organized or governed, or when an ADR, spec or audit is added or accepted.
  It is not for routine edits.
- **Relationships.** Every new `investigation`, `test-result` and `proposal`
  names in `related` the issue, spec or ADR it informs; every `spec` links its
  tracking issue and the ADRs it relies on. `specs/` files stay outside the
  frontmatter requirement; the spec directory's `spec.md` header cites its issue.

## 4. From investigation to approved implementation

1. **Investigation / audit** records evidence and a proposed direction. It
   cannot authorize work.
2. **Issue** is opened for the proposed change (constitution Principle VI),
   citing the roadmap phase as plain text.
3. **Decision.** A change that alters architecture, identity, persistence or
   embedding behavior gets an ADR (`proposed` → `accepted`). A new feature or
   behavior gets a `spec` under `specs/`, which cites the ADRs.
4. **Owner acceptance** is recorded in the ADR or spec status. This proposal
   adds no approval states beyond the existing constitution and Spec Kit
   workflow (issue, spec, branch, PR); an accepted spec or ADR is not by itself
   authorization to implement unless it says so.
5. **Implementation** follows the spec's plan and tasks, on a branch and PR that
   cite the issue; `status.md` is updated when the work ships.
6. **Evidence** from the run goes to `test_results/` and links back to the spec
   or ADR it verifies.

## Open questions: accepted resolutions

Recommended in review on 2026-11-10 and accepted with the proposal.

1. **`spec.md` frontmatter:** no. Keep Spec Kit headers and treat `specs/NNN-*/spec.md`
   as type `spec` by location, to avoid altering established Spec Kit conventions
   for metadata consistency.
2. **Controlled `status` vocabulary:** accept for new documents only; no historical
   cleanup.
3. **`investigation` as a separate type:** yes, distinct from `audit` (a specific
   hypothesis versus a broader system or area). Retain the eleven types for now;
   what matters is that a future agent can tell requirements, decisions,
   investigations and observed evidence apart without guessing from the directory.

Keep the accepted conventions short enough to apply without repeating them in
prompts.

## After acceptance

Amend the OKF standard with the accepted sections, then consider a lightweight
validator (frontmatter `type`, link targets, category-index membership) as a
separate issue, enforcing only what the standard then states.
