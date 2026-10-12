---
title: "README accuracy and product documentation policy"
date: 2026-10-12
type: standard
status: accepted
tags: [documentation, readme, review, licensing]
related:
  - "[Product README](/README.md)"
  - "[Project status](/DOCS/status.md)"
  - "[Documentation standard](/DOCS/standards/okf-documentation.md)"
  - "[PR review checklist](/.github/pull_request_template.md)"
---

# README accuracy and product documentation policy

**The README describes the current product, not development status.** It is
the user-facing entry point for purpose, implemented capabilities, supported
inputs, current limitations, setup, APIs, and licensing.

Milestones, issue/PR progress, evaluation scores, pending work, and deployment
verification belong in the evolving [project status](/DOCS/status.md), with links
to detailed reports, roadmap entries and release records. The README links there
rather than duplicating those updates. Historical/design-intent documents are
not evidence of current behavior.

## Accuracy requirements

- Confirm product claims against the implementation that will be merged,
  configuration defaults, API contracts and relevant validation records. An
  unmerged experiment is not an available product capability.
- Distinguish supported functionality from demonstrated reliability. A parser,
  endpoint, source ID, passing unit test or requested output format does not by
  itself establish answer correctness, citation accuracy or generalization.
- Describe material limitations in product terms. Route implementation progress
  and planned fixes to status; do not present plans as current capabilities.
- Check setup commands, ports, environment variables, models, examples and local
  links against their current configuration and implementation. State when a
  command or deployed capability has not been exercised in the review.
- Project license declarations must agree with [LICENSE](/LICENSE): Apache
  License 2.0, using `Apache-2.0` for SPDX/OCI metadata. This does not relicense
  dependencies or replace their attribution/license requirements.

## PR review

For PRs changing public behavior, APIs, supported inputs, setup, defaults,
validation claims, licensing or README text, reviewers use the
[PR checklist](/.github/pull_request_template.md) to record the accuracy check.
Update the README when the product description changes, or explain why it
remains accurate. Update `DOCS/status.md` for progress or validation-state
changes, and cite the relevant implementation/configuration/evaluation evidence.

This is a review requirement, not an automated semantic correctness check.
Documentation-only edits require appropriate link/content verification; they do
not require architectural changes or unrelated runtime tests.
