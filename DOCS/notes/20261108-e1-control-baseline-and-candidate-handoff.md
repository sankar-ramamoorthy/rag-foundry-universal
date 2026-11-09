---
title: "E1 handoff: control baseline recorded, candidate spec frozen, what to do next"
date: 2026-11-08
type: working-note
status: current
tags: [e1, held-out, handoff, control-baseline, named-symbol-first]
related:
  - "[Issue #325](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/325)"
  - "[Goal #294](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/294)"
  - "[Control baseline report](/DOCS/test_results/2026-11-08-e1-held-out-control-baseline.md)"
  - "[Mechanism spec (frozen)](/DOCS/evaluations/code-evidence-held-out/mechanism-spec-named-symbol-first.md)"
  - "[Pre-registration (frozen)](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)"
  - "[Corpus certification work record](/DOCS/notes/20261108-e1-held-out-corpus-certification-and-decorator-fix.md)"
---

# E1 handoff (2026-11-08)

Written so that anyone resuming E1 (a person, Claude Code or Codex) can do so from the
repository alone. Roadmap phase: Phase 6, workstream E. Goal: #294.

## Where E1 stands
| Step | State | Evidence |
| --- | --- | --- |
| Three held-out corpora certified and pinned (17/17 frozen function hashes) | done | PR #316, [pin](/DOCS/evaluations/code-evidence-held-out/held-out-corpus-pin.json) |
| Pre-registration (P1-P4) | frozen | PR #304 |
| Control harness `scripts/held_out_control.py` | merged `2eabadd` | #317, PR #320 |
| Frozen control: 12 cases run twice (24 executions) | done 2026-11-08 | 12/12 final-context hashes reproduced |
| Independent verification of the raw captures | done | [report](/DOCS/test_results/code-evidence-held-out/e1-control-evidence-verification.md), recorded by PR #322 |
| Control baseline report | merged `60d72a2` | [report](/DOCS/test_results/2026-11-08-e1-held-out-control-baseline.md), #321 closed |
| Named-symbol-first mechanism specification | frozen, merged `f9c5816` | PR #324, [spec](/DOCS/evaluations/code-evidence-held-out/mechanism-spec-named-symbol-first.md) |
| Named-symbol-first candidate | **not implemented, not run** | #323 open |
| Full S3/S4/S5 scoring of the control | **not done** | see below |

## Control result in one paragraph
Primary function in the pre-budget pool: 10/12. Delivered to the final context: 7/12.
Discovery misses: H1, P4. Pool-to-context delivery losses: H4, W1, W2. Named cases 6/8
delivered, natural cases 1/4. Only primary-function presence was measured; it is not the
frozen delivery gate (S3 operation/dependency coverage, S4, S5, S6). All figures are the
independent verifier's; the raw captures are on the Linux operator host (26 files, about 32 MB)
under `DOCS/test_results/_raw/code-evidence-held-out/` (git-ignored) and are **not** in
`raw-index.json`. The local orchestrator ran at `2eabadd`; the remote services self-report
`82b263f8e06b106867aceb5a988ae598de101db1` (a different SHA, by design; see the baseline report).

## Decision taken: two separate experiments (Interpretation A, owner-approved)
The frozen statement-level contract (#276), its GO-rate addendum and the held-out set were built
for **statement-level delivery** (Option B). Named-symbol-first (#275) is a chunk-ordering
mechanism the contract explicitly leaves out (statement-level contract lines 23, 71, 265). Under
the literal wording a chunk-ordering candidate cannot reach GO: the addendum excludes
`chunk_fallback` delivery from k and wins, S4 requires delivered lines to equal pinned node text
(stored chunks are not source-faithful), and S5 has nothing to check. The addendum can only be
superseded by a document committed before the manifest froze, so it cannot be amended for these
cases.

Therefore:
- Named-symbol-first is judged on the preregistered **P1-P3** only. **P4** stays recorded but is
  structurally uninformative about the statement-level GO gate.
- Chunk-ordering results get **no eligibility toward statement-level k or wins**; S4/S5 are not
  reinterpreted; the GO criteria are not changed after seeing control results.
- No S3 scoring addendum is authorized. Control S3 scoring, if done, is descriptive only, uses
  the baseline `coverage()` rule, and sets no threshold.
- Statement-level delivery (Option B) is a later, separate experiment. Because the control
  outcomes have been seen, whether these 12 cases remain eligible held-out data for it is an open
  **owner decision**; its design must not be tuned against them while still calling them untouched.

## Binding rules for the next step (#323)
- Implement exactly the frozen spec: a stable partition of the already-capped chunk list, placed
  after the unbounded `assemble_context(..., 2**63)` call and before `prioritize_exact_sources`;
  `.py` labels only; name-only matching with the preregistered whole-identifier-token rule; all
  same-name symbols promoted; no length or stop-word filter (a false promotion refutes P2 and is
  reported, never filtered); flag default off; diagnostic `retrieval_plan["named_symbol_first"]`
  that nothing reads.
- The invariant "the partition is the order the allocator sees" holds only while exact-source
  preservation is disabled (no `claim_type`, claim selection false); tests pin this.
- Verify with synthetic fixtures and the F1-F3 development pools only. **No replay of the
  candidate over the 12 held-out pools**, no new control run, no candidate execution during
  implementation.
- The spec is **not blinded**: its author had seen the frozen manifest and the control outcomes.
  Keep that disclosure.
- After the implementation PR is merged, **exactly one** candidate execution of the 12 cases, only
  on separate explicit owner approval. No retries, partial reruns or fixes in place. A change to
  the mechanism after a held-out result makes the cases development data.

## Next steps, in order
1. Implement #323 on a branch (issue, branch, PR; tests alongside; no AI attribution lines in
   commits or PR bodies, per repo convention).
2. Owner reviews and merges. The candidate then needs its own harness mode (the control harness
   is `scripts/held_out_control.py`) writing `held-out-candidate-*` captures with no overwrite and
   recording the candidate commit and spec hash, plus a production-independent preflight.
3. Owner authorizes the single candidate run; the Linux operator runs it.
4. Report P1-P4 (all outcomes, including refutations) in a decision note under `DOCS/test_results/`.

## Open gaps and risks
- Raw control captures are not hashed in `raw-index.json` (needs the 32 MB directory copied and
  `scripts/raw_index.py update`).
- S3/S4/S5 scoring of the control is not done; whether five control gate failures exist (needed
  for "wins >= 5" ever to be reachable) is unknown.
- Held-out eligibility for the statement-level experiment is undecided.
- Ingestion-time embedder digest and runtime SHA for the pinned corpora are not independently
  recorded (corpus pin). #313 and #314 remain open design issues from the Hatch fixes.
- The runbook command for the control (`ingestion-runbook.md`, step 3) omits the required
  `--execute-frozen-questions` flag; the harness refuses safely without it. Fix when next editing
  that file (frozen artifacts are not touched by this note).

## Operating boundaries (unchanged)
Production deployment, re-ingestion and the release procedure are operator-owned
([agent execution and verification](/DOCS/deployment/agent-execution-and-verification.md)).
Agents run offline tests and read-only checks only; held-out questions run only on the Linux
operator host after explicit approval.
