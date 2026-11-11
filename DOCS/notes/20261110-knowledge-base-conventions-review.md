---
title: "Knowledge-base conventions review (2026-11-10)"
date: 2026-11-10
type: working-note
status: complete
tags: [documentation, governance, okf, sdd]
related:
  - "[Documentation standard (OKF)](/DOCS/standards/okf-documentation.md)"
  - "[Documentation index](/DOCS/index.md)"
  - "[Convention proposal](/DOCS/proposals/2026-11-10-documentation-conventions.md)"
---

# Knowledge-base conventions review (2026-11-10)

Tracked by issue #332. A read-only review of `AGENTS.md`, `CLAUDE.md`, the OKF
standard, `DOCS/index.md`, `DOCS/log.md`, the constitution and the `specs/`
hierarchy, measured by a script over the Markdown files under `DOCS/` and
`specs/`. Nothing was changed. The counts below are as of 2026-11-10 on `main`.

## Findings

1. **Format rules exist; taxonomy rules do not.** The standard requires only
   `type`, and says nothing on which types exist, where documents go, or what
   authority each carries. There are 43 `type` values (`test-result` and
   `test-results` coexist) and about 60 free-text `status` values. `audit/`,
   `notes/`, `test_results/`, `evaluations/` and `proposals/` overlap, which is
   why the CI-01 investigation ended up under `audit/`: the rule was missing.
2. **Authority is partly stated, not fully.** Constitution Principle VII makes
   ADRs authoritative over specs and audits for technical facts, and `status.md`
   is the single current-state document. Nothing states how investigations, test
   results, proposals and specs relate to those, or how a finding becomes an
   issue, spec, ADR or implementation.
3. **The index is not a reliable discovery route.** Specs 006-008 and the three
   2026-11-10 audits are not linked from `DOCS/index.md`; the audits are linked
   only from `00-Audit-Overview.md`. This is a navigation-hierarchy problem, not a
   case for listing every document in the root index.
4. **Compliance with the rules that do exist is good.** Every ADR, audit,
   evaluation, release, research and standards document has frontmatter with
   `type`; recent commits add no new `[[wikilinks]]`; `status.md` stays a single
   living file; `AGENTS.md` points to `CLAUDE.md` without duplicating it.
5. **`specs/` is outside the frontmatter convention** (1 of 56 files has any).
   This is technically compliant, since the standard's scope is `DOCS/`.

Unverified: whether the wikilink count includes code snippets, and whether the
index coverage gaps are covered by intermediate parent documents.

## Agreed approach

Rules first, then validation. A validator enforces conventions, so the
conventions must be decided before anything is automated. Steps:

1. Define document types and their authority.
2. Define placement using existing directories.
3. Clarify index responsibilities (root index, category indexes, status).
4. Clarify how Spec Kit artifacts relate to the knowledge base.
5. Add lightweight validation of only the agreed conventions (separate follow-up).

Constraints: no migration of historical documents, no ADR renames, no new
documentation framework. Document authority is not inferred from directory
location alone; it comes from type, status and explicit relationships. This work
is separate from the CI-01 investigation and is not a prerequisite for
engineering work. The draft is in the
[convention proposal](/DOCS/proposals/2026-11-10-documentation-conventions.md).

## Kept separate

Independent maintenance defects found in the same review are not part of #332:
7 broken links in 3 files (two distinct missing targets, one of which is the
illustrative `./other.md` in the standard), the 2026-11-10 documents missing from
`DOCS/log.md`, and the `index.md` "Current release" line, which needs checking
against the release records. They are handled as their own change.
