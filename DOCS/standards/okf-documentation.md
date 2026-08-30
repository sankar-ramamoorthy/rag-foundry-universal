---
title: "Documentation Standard — OKF v0.2"
date: 2026-08-30
type: standard
status: accepted
tags: [standards, documentation, okf]
related:
  - "[Lean instruction routing proposal](/DOCS/proposals/lean-instruction-routing-layer.md)"
  - "[Documentation Index](/DOCS/index.md)"
---

# Documentation Standard — OKF v0.2

## Compliance target

"OKF-compliant" in this repo means conformant with
[Open Knowledge Format v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md),
not an informal "frontmatter + links" style. That spec is deliberately
permissive — it defines a directory of Markdown files with YAML
frontmatter, no mandatory central toolchain, and very few actual
requirements. This document states which of those requirements are
spec-mandated versus conventions this repo has adopted on top.

## Required vs. repo-adopted frontmatter

The spec requires exactly one frontmatter key:

- **`type`** — a short string identifying the kind of concept. Per
  spec, "a concept carrying just `type` is fully conformant"; consumers
  must not reject a bundle for unknown `type` values or unknown
  additional keys. Types already in use here: `adr`, `audit-index`,
  `doc-index`, `proposal`, `standard`. New types are fine to introduce
  as needed.

Everything else below is a **repo convention**, not a spec requirement,
kept because it's useful here and explicitly permitted by the spec's
"consumers MUST NOT reject a bundle because of... unknown additional
frontmatter keys" rule:

- `title` — human-readable name.
- `status` — e.g. `proposed` / `accepted` / `complete` / `superseded`;
  check a document's own `status` before trusting it, don't assume
  numeric/date order implies currency.
- `tags` — free-form categorization.
- `related` / `supersedes` — links to other concepts (see linking rule
  below).
- `source` / provenance fields — where a document's claims came from
  (code, incident, runbook, design decision), used inconsistently today
  and worth strengthening over time, but not spec- or policy-required.

## Linking rule

Use standard Markdown links, per spec:

- **Absolute, bundle-relative (recommended):** `[text](/DOCS/adr/ADR-030-unified-artifact-graph.md)`
  — stable if the file moves within its own subdirectory.
- **Relative:** `[text](./other.md)` — also permitted.

Do **not** introduce new `[[wikilink]]` cross-references. Existing
`[[wikilinks]]` in `DOCS/adr/`, `DOCS/audit/`, and `DOCS/index.md`
predate this rule (from PR #63's retrofit) and are not spec-conformant
link syntax — a spec-aware tool that builds a graph from Markdown links
won't recognize them as edges. They are migrated to spec-form links
opportunistically, as part of substantially editing the file they
appear in, not in a bulk pass.

## Reserved filenames

The spec reserves two filenames at any level of the hierarchy, which
"MUST NOT be used for concept documents":

- **`index.md`** — directory listing / map-of-content. Already in use
  (`DOCS/index.md`, `DOCS/audit/00-Audit-Overview.md`).
- **`log.md`** — chronological history of updates. In use at
  [`DOCS/log.md`](/DOCS/log.md): a reverse-chronological record of
  documentation-standard-relevant changes (new ADRs, policy adoptions,
  structural migrations) — not a substitute for `git log`, and not
  meant to capture routine content edits.

## Scope

- New knowledge-bearing documents under `DOCS/` must be OKF-compliant
  as defined above (at minimum, a `type` frontmatter key; spec-form
  links for any cross-references).
- Substantially-edited legacy documents are brought into compliance as
  part of that edit (frontmatter and link syntax).
- No bulk migration of existing docs is planned or required.

## Validation (deferred)

There is no automated check yet for required frontmatter, link syntax,
or reserved-filename misuse. Adding one (for example, running an
OKF-aware CLI's `check`/`graph` commands in CI, or an equivalent local
script) is tracked as separate future work and is not a prerequisite
for this policy taking effect.
