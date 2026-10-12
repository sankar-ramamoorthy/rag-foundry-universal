---
title: "Issue #254: research checkpoint and deliberate deferral"
date: 2026-10-12
type: decision-note
status: deferred
tags: [issue-254, prioritization, behavioral-completeness]
related:
  - "[Completed investigations](/DOCS/test_results/2026-10-12-issue-254-separated-investigations.md)"
  - "[Document baseline protocol](/DOCS/evaluations/2026-10-12-document-rag-baseline.md)"
  - "[Current status](/DOCS/status.md)"
---

# Research checkpoint and deliberate deferral

At the user's direction, the current #254 experimental sequence is completed
research and further implementation/evaluation is **deferred by prioritization**.
The issue's acceptance gate remains failed and open. This is not completion
of the issue or an external technical blocker. No remote issue state is changed
by this local decision record.

Preserve the unmerged/undeployed runtime candidate, diagnostic scripts, frozen
questions, source snapshots, score records and failing regression gates. Stop
iterating on the present automatic AST selector and answer contract. Do not
deploy a partial fix or relax acceptance. C1 remains an independent historical
grounding defect; the same-generation historical seed discrepancy is also
unresolved. #243's held-out repositories/evaluation remain untouched.

Repository orientation and repository behavior explanation have separate quality
requirements even when they share infrastructure. The frozen development
overview result is 8/8. End-to-end attributed code behavior remains unproven.
The manual 4024-byte oracle proves five transition witnesses can fit; it does
not cover every dependency, including constructor system-memory initialization.
The offline selector assumes full-source access and loses branch relationships;
the tested answer contract yields no scored grounding improvement. No evidence
establishes that another model alone resolves these failures.

Architectural requirements to carry forward:

- Evidence completeness covers transitions, branches and state dependencies,
  including relations between selected passages, rather than symbol/statement
  counts alone. Source access must be demonstrated for the actual retrieval path.
- Code citations preserve actual expressions and the responsible components;
  format compliance and canonical IDs do not establish correctness.
- Correctness, attribution, quotation accuracy and evidence availability are
  measured separately; every applicable acceptance obligation must pass.

Resume with a broader frozen **development** behavior suite spanning method
sizes, branch/loop patterns, state initialization and multiple repositories.
Freeze evidence expectations and scoring before answers, distinguish retrieval
from generation/dependency failures, and reserve new held-out corpora for a
later #243 run. Resume requires an explicit prioritization decision; another
R1-specific heuristic is not the default next step.

The immediate focus is a bounded D0 document-RAG baseline. Read-only agent/MCP
interfaces and scalability remain later priorities, without opening a new
architecture implementation in this checkpoint.
