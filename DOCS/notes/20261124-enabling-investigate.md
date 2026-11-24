---
title: "Enabling Investigate on a Foundry deployment"
date: 2026-11-24
type: note
status: current
tags: [frontend, investigate, deployment, phase-6]
related:
  - "[Issue #439](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/439)"
  - "[ADR-057](/DOCS/adr/ADR-057-react-typescript-product-frontend.md)"
  - "[Access enforcement review](/DOCS/notes/20261124-product-api-access-enforcement-review.md)"
  - "[Verification plan](/specs/016-product-frontend/verification-plan.md)"
---

# Enabling Investigate

Investigate is off by default. When it is off, `GET /v1/product/capabilities`
reports `"investigate": false` and the UI does not show the mode. Ask is
unaffected either way.

## Settings

All are environment variables on the **orchestrator**. None has a default
address, token, secret or model, and none is sent to the browser.

| Variable | Meaning |
| --- | --- |
| `INVESTIGATE_BACKEND` | `disabled` (default), `fixture` or `http`. |
| `INVESTIGATE_RUN_SECRET` | A long random string. It signs run IDs so a run can only be read back through the repository and generation it was started for. Required for any backend. Changing it makes open run IDs unreadable. |
| `INVESTIGATION_SERVICE_URL` | Address of the investigation service, reachable from the orchestrator only. `http` backend. |
| `INVESTIGATION_SERVICE_TOKEN` | Bearer token the service expects. `http` backend. |
| `INVESTIGATION_MODEL_ALIAS` | The model alias the service should use. The service requires one on every run, and choosing it is the operator's decision. `http` backend. |
| `INVESTIGATE_DEADLINE_SECONDS` | Per-call deadline to the service, default 120. |

With `http`, if any of the URL, token or alias is missing the mode stays off
and the orchestrator logs why.

## Trying the screens without the service

`INVESTIGATE_BACKEND=fixture` with a run secret serves clearly labeled
synthetic runs ("Synthetic fixture data"). It reads no repository and calls no
model.

## What to expect from the real service

These come from the service's published schema (0.3.0-draft), not from a run:

- **One active run at a time.** A second submission while one is running is
  shown as "Another investigation is running. Try again when it finishes."
- **A deployment may allow only a limited number of runs.** That is shown as
  "This deployment has no further investigation runs available."
- **`partial` and `none` are normal.** The UI shows the stop reason. A run that
  fails outright (no answer) is shown as an unavailable error with the
  service's short failure code.
- **The pin.** Foundry sends the generation the user was shown. If the
  repository is re-indexed first, the run ends `stale_generation` and the UI
  asks the user to refresh.
- **Recorded excerpts.** Each citation can show the text the investigation
  stored. It is not read from the repository now and may differ from the
  current source; the UI says so.

## What this does not do

Enabling the mode authorizes nothing. A real investigation contacts the
investigation service and its model host, which is a separate decision for the
owner each time it is wanted. The first-release audience is a single local
user ([access review](/DOCS/notes/20261124-product-api-access-enforcement-review.md));
turning Investigate on does not change that.

## Verification state

The adapter is tested against a mock transport that returns bodies shaped as the
service's schema describes, and a conformance test checks those shapes and the
request against the schema when `LAB_OPENAPI_PATH` points at a local copy. It
has not been run against the real service or any model.
