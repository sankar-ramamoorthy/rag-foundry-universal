# Documentation Log

Reverse-chronological record of documentation-standard-relevant changes
across `DOCS/` — new ADRs, policy adoptions, and structural migrations.
Routine content edits are tracked by `git log`, not here; this file is
for changes that affect how the knowledge base itself is organized or
governed.

## 2026-09-12

Promoted `DOCS/releases/` from a template-only folder to an explicit production
release-record bucket in `DOCS/index.md`. The first successful audited Docker
Compose production release is
[prod-2026-09-12](/DOCS/releases/2026-09-12-prod-release.md); the failed
`827c9cdc` promotion remains linked as part of the release audit trail.

## 2026-08-30

Adopted OKF v0.2 as the standing documentation standard. Added
`DOCS/standards/okf-documentation.md`; `CLAUDE.md` and `DOCS/index.md`
now point to it. New knowledge-bearing docs must comply going forward;
legacy docs migrate opportunistically on substantial edit, not in bulk.
See [issue #75](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/75) /
[PR #76](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/76).

## 2026-08-27

Retrofitted `DOCS/adr/` and added `DOCS/index.md` using the frontmatter
+ `[[wikilink]]` pattern `DOCS/audit/` had already independently
established, generalizing it into the repo's first cross-directory
documentation convention. See
[PR #63](https://github.com/sankar-ramamoorthy/rag-foundry-universal/pull/63).
