---
title: "Cedar service-level table (synthetic fixture)"
date: 2026-10-12
type: evaluation-fixture
status: frozen
tags: [document-rag, synthetic, tables]
related:
  - "[Baseline protocol](/DOCS/evaluations/2026-10-12-document-rag-baseline.md)"
---

# Cedar service-level table — synthetic evaluation source

## Severity and coverage

| Service | Urgent threshold | Coverage | Standard target |
| --- | --- | --- | --- |
| Atlas | Outage longer than 10 minutes | 24 hours daily | 8 hours |
| Beacon | Outage longer than 20 minutes | Weekdays 09:00–17:00 UTC | 16 hours |
| Cobalt | Outage longer than 30 minutes | 24 hours daily | 24 hours |

## Interpretation

An outage equal to the threshold is standard; only a longer outage is urgent.
Coverage is a staffing window, not the escalation deadline. Standard target
means time to first mitigation, not approval to close a case. All durations in
the table are elapsed time. No automatic exclusion of weekends is specified.
