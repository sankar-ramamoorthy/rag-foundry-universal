---
title: "#439 first contact with the real investigation service: the Haiku run was refused (authorization already used)"
date: 2026-11-26
type: test-results
status: current
summary: "The owner authorized one Haiku investigation through the deployed product API. Investigate was enabled and the submission reached the real service, which refused it because its single metered run had already been used. No investigation ran, so no findings, citations or model behavior were observed. What this does show: the adapter reaches the service, is authenticated, and turns the refusal into the plain message designed for it."
tags: [evaluation, results, investigate, issue-439, development-diagnostic]
related:
  - "[Issue #439](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/439)"
  - "[Enabling Investigate](/DOCS/notes/20261124-enabling-investigate.md)"
  - "[Linux dev host verification report](/DOCS/test_results/2026-11-25-440-linux-deployed-run.md)"
  - "[Raw capture index](/DOCS/test_results/raw-index.json)"
---

# #439 first contact with the real service

**Evidence class: development diagnostic (ADR-054). One call.** No host
addresses, tokens or model aliases are recorded; the alias, service address and
token are configured on the server and were not known to the person or agent
making the call.

## What was done

On 2026-11-26 the owner populated the Investigate settings on the Linux dev
host's orchestrator and authorized one real run with Haiku. From a Windows
machine over HTTP:

1. `GET /v1/product/capabilities` returned `{"ask": true, "investigate": true}`.
   The deployed build was `cf26ff2bd894cb7e5f542df673014726bd614b8e` (equal to
   `main` at the time; release `prod-2026-11-26-0943am-front`), so the settings
   had taken effect and the adapter was in the running build.
2. One `POST /v1/product/repos/{id}/investigations` for
   `fastapi-react-starter`, pinned to generation
   `03b5e352-1c36-490c-a41e-92e6874d6a6f` (commit `eaebfb16a675…`), with the
   question "Where is user login implemented in this repository, and how does it
   verify the password?". The script makes exactly one submission and never
   retries, because the hosted profile is metered.

## Result

The product API answered HTTP 503 with the stable error body:

```json
{"error": {"code": "unavailable",
           "message": "This deployment has no further investigation runs available.",
           "details": {}}}
```

That message is the adapter's wording for the service's `409
run_authorization_used` response (`investigation_http.py`). So the run was
**refused before it started**: the service's metered profile admits one run per
state volume and that run had already been used.

## What this shows and what it does not

- **Shown:** the deployed orchestrator reached the real investigation service;
  the bearer token was accepted (a rejected token would have produced the
  generic "service unavailable" message, not this one); and the adapter turned
  the service's refusal into the plain message and the product error body that
  were designed for it. This is the first contact between Foundry and the real
  service.
- **Not shown:** anything about an investigation. No run started, so there are
  no findings, citations, recorded excerpts, stop reason, cost, or model
  behavior to report. Whether the configured model alias is one the service
  accepts is also unknown: the refusal came first.
- **Not claimed:** that the Haiku run works, or that the adapter handles a
  completed run against the real service. Those paths are verified only against
  mock responses and the service's published schema.

## What would let the run proceed

This is the lab deployment's decision, not Foundry's: the service's state needs
a fresh authorization (or a different profile, for example the unmetered local
one), and a hosted Haiku run spends money. It goes through the owner. Foundry
did not retry and cannot change it.

## Status of #439

Open. The adapter and the Foundry-side contract are merged and tested; the real
run has not happened.
