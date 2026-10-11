---
title: "Agent Execution Boundaries: Local, Deployed, and Deployment Ownership"
date: 2026-10-11
type: deployment-guide
status: accepted
tags: [deployment, agents, verification, provenance, windows]
related:
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
  - "[Documentation Index](/DOCS/index.md)"
  - "[Issue #254 pinned R1/R2 replay](/DOCS/test_results/2026-10-11-issue-254-pinned-replay.md)"
---

# Agent Execution Boundaries: Local, Deployed, and Deployment Ownership

This records the operating model for a coding agent (human or Claude Code)
working in this repository against a production deployment it does not
control. It does not restate the release procedure itself — see
[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)
for that.

## Four distinct activities

Treat these as separate, not interchangeable:

1. **Local development** — editing code in the working tree, running unit/
   integration tests against local or dockerized-local services.
2. **Deployed HTTP testing** — issuing requests from a local machine to the
   already-running production services over HTTP, without deploying
   anything. A local (including Windows) Python process can call Linux-
   hosted HTTP services directly; this needs no SSH or deployment access.
   See the [issue #254 pinned replay](/DOCS/test_results/2026-10-11-issue-254-pinned-replay.md)
   for a worked example of comparing a local replay against a live
   deployed control over HTTP.
3. **Production comparison** — reconciling a local result against a
   deployed result. Do not treat an undeployed local change as explaining
   deployed behavior, or a deployed symptom as proof of a local bug, until
   inputs on both sides are verified equivalent (see "Four SHAs" below).
4. **Deployment** — building, releasing, and rolling back the production
   stack itself.

## Deployment is operator-owned

**Only the repository owner performs production deployments.** This is a
durable rule, not contingent on current tooling.

- **Why:** production releases are deliberate, provenance-tracked actions
  (see the release guide's cadence rules) with real blast radius; a coding
  agent proposing or executing a release blurs the human decision point the
  release process is built around.
- **Current environment fact, not the basis of the rule:** coding agents in
  this repository currently have no SSH access to the production host. If
  that access were ever granted, the ownership rule would still hold —
  access is an implementation detail, the ownership boundary is not.
- **How to apply:** an agent may run `scripts/prod-refresh.sh --check`-style
  read-only verification only when explicitly asked, and never `--deploy`,
  `git checkout <sha>` on the production host, or any command that mutates
  the running release. Proposing a deploy and asking the operator to run it
  is fine; running it is not.

## Four SHAs that can differ

A single "the code" question can hide up to four distinct commits:

1. Local working-tree commit (what's checked out on the agent's machine).
2. `main` branch HEAD (what's merged, possibly not yet deployed).
3. Deployed orchestrator runtime commit (`git_sha` from each service's
   `/version` endpoint, or the OCI `org.opencontainers.image.revision`
   label on the running container).
4. Ingested repository *source* commit — the SHA of the code that was
   ingested into the graph/vector store, independent of which commit the
   *application* is running.

**Why this matters:** the #254 investigation showed a local diagnostic
build (`7522ea0`) reproducing against a differently-pinned deployed runtime
(`f344bd5`) and a specific ingested repository source SHA
(`f854303e6e44ff95d94792d24868442a28080ba2`) — three different SHAs, each
load-bearing for interpreting one result. Confusing any two of them (e.g.
assuming the deployed runtime matches `main` HEAD, or that re-running
locally against the same repo re-ingests the same source snapshot) produces
false equivalence claims.

**How to apply:** when comparing local and deployed behavior, record all
four SHAs explicitly before drawing conclusions, not just one.

## HTTP verification has boundaries

`/version` and `/health` identify what a service *reports*, not what is
actually running or configured:

- `/version` fields (`git_sha`, `build_date`, `release_version`) prove the
  application's self-reported commit, not independent image attestation —
  the production release guide already states this explicitly.
- Matching `git_sha` between local and deployed does **not** establish
  configuration or runtime parity. Embedding model digests, retrieval
  defaults, and other unexposed settings can still differ.
- **Treat any runtime configuration not exposed over HTTP as unknown**,
  not as equal to the local default, until confirmed. The #254 replay
  recorded local defaults and model digests but explicitly could not
  verify "equivalence to all deployed process settings" — that gap stayed
  an open, named unknown rather than an assumed match.

## Requesting operator-only information

When a genuinely unexposed setting is essential to resolving a
local/deployed discrepancy, ask the operator for that **specific,
non-secret value** (e.g. one env var's effective value, one Compose
override field) — not a full environment or `.env` dump. Exhaust available
HTTP evidence (`/version`, `/health`, replaying pinned requests against the
deployed endpoint) before asking.

## Non-goals

- This does not create a new deployment procedure — that stays in
  [Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md).
- This does not grant or request SSH/deployment access for agents; it
  documents the boundary assuming that access stays unavailable, and
  states that the boundary would not change if it became available.
- This is not an ADR — it clarifies an existing operating model, not a new
  architectural decision.
