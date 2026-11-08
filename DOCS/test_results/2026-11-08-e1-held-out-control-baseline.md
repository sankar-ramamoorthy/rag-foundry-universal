---
title: "E1 held-out control baseline: the unchanged runtime on the 12 frozen cases"
date: 2026-11-08
type: evaluation-report
status: control-baseline-recorded-no-candidate-no-verdict
tags: [held-out, control, baseline, evidence-delivery, adr-054, pre-registration]
related:
  - "[Issue #321](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/321)"
  - "[E1 goal #294](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/294)"
  - "[Control harness #317 / PR #320](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/317)"
  - "[Pre-registration](/DOCS/evaluations/code-evidence-held-out/preregistration-named-symbol-first.md)"
  - "[Held-out corpus pin](/DOCS/evaluations/code-evidence-held-out/held-out-corpus-pin.json)"
  - "[Execution contract](/DOCS/evaluations/code-evidence-e1/execution-contract.json)"
  - "[Statement-level contract](/DOCS/evaluations/code-evidence-e1/statement-level-contract.md)"
  - "[GO-rate addendum](/DOCS/evaluations/code-evidence-e1/statement-level-contract-addendum-go-rate.md)"
  - "[Independent verification report](/DOCS/test_results/code-evidence-held-out/e1-control-evidence-verification.md)"
---

# E1 held-out control baseline

Roadmap phase: Phase 6, workstream E. Tracked by #321 under goal #294.

**This report records a baseline. It is not an E1 GO/NO-GO result and it does not evaluate
P1-P4.** No candidate exists, has been authorized or has been run.

## What was run
On 2026-11-08 the Linux operator ran `scripts/held_out_control.py run` (PR #320, commit
`2eabadd237301578df0815030639dfeed89a8867`) twice over the 12 frozen cases: 24 executions,
all completed. The harness replays the cases through the **unchanged local orchestrator** against
the **remote HTTP services** and the three pinned corpus generations. Settings: top_k 20,
max_chunks_per_doc 5, 4096-byte cap, rerank off, overview flags off, model `ollama/Qwen3:4b`.

## Evidence chain and its limits
- **Raw captures** (24 case captures, `held-out-control-summary.json`, `capture-events.jsonl`; 26
  files, about 32 MB) are on the Linux host under
  `DOCS/test_results/_raw/code-evidence-held-out/` (git-ignored). They are **not** in this
  checkout and are **not yet listed in `raw-index.json`**; the author of this report did not read
  them.
- **Independent verification:** a disposable Linux agent read all 26 files with standard-library
  code (it did not import the harness) and recomputed every hash and measurement. Its report is
  preserved unmodified at
  [e1-control-evidence-verification.md](/DOCS/test_results/code-evidence-held-out/e1-control-evidence-verification.md)
  (SHA-256 `ef4ea80476698685fc94bd9b0c5837375d32af075d7f86c2ebed718cd5bfcbf8`; original at
  `/media/sankar/llm/rag/rag-agent/shared/e1-control-evidence-verification.md` on the Linux host).
- Every figure below is therefore **reported by that verification**, not re-derived here.
  Consistency checks done here: the counts add up (7 + 3 + 2 = 12; named 6/8 + natural 1/4 = 7),
  and the named/natural split matches the pre-registration (named = H1, H2, H3, P1, P2, P3, W2,
  W3).

## Results by case
Rank is zero-based in the pre-budget chunk list (not vector rank). *Delivered* means at least one
chunk labeled with the primary function's canonical id is in the final context. The hash and
outcome are identical in both runs.

| Case | Query | In pool | Rank | Delivered | Bytes | Final-context SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | named | no | - | no | 4023 | `facaf4d82d4163d65ba052c89ef2d5229b512c070844ad290fff4a971d8bff6c` |
| H2 | named | yes | 9 | yes | 4045 | `e5654ad3b6552ae0b792954629f47abed2f980b2108ecacc50da8c424a2258e4` |
| H3 | named | yes | 0 | yes | 4087 | `7b7bf66842c69908ae38f7bc854cb6b26b7cf94b610bea6cbe84b63678c80e79` |
| H4 | natural | yes | 21 | no | 4058 | `890900dfad84aba246c183f3e4eed1cb4d18e28d44d0b5c8b3bef21652ff3e19` |
| P1 | named | yes | 3 | yes | 4085 | `0ec279a9f81f897fc3532c1b68b3423a97c5188bc2a6bd934ba7e6c13e412cd5` |
| P2 | named | yes | 0 | yes | 4045 | `80f25285a192788d987f7a5592a6944d2f1e3a7f99d7ac16dd0f4996467d1f63` |
| P3 | named | yes | 0 | yes | 3998 | `411a38512bd0fedf008c5095fe0061547a2072e92132e1c4d07f733293c62239` |
| P4 | natural | no | - | no | 4094 | `9c448b4e8dd8fa63c7c8dcaef9c37d73a475e24d5fb847895c8f05edb69b231c` |
| W1 | natural | yes | 32 | no | 4016 | `657d906964eafe0632cc9f2b76f8853f5874157ad41dc628bf904578f0b31a6d` |
| W2 | named | yes | 10 | no | 3972 | `500ce766e85513b40e96aacc79780f3e79cf5c6534e8bd2215d22974f77f89ec` |
| W3 | named | yes | 0 | yes | 4040 | `c9c01fe47147bce61f96f30452398de446e50e3f8d12aa416059019405e93e98` |
| W4 | natural | yes | 9 | yes | 4076 | `06caaa9ad765adff915640f4ce89ae88aa217b6882f7e0f73c0eb3d09e71d89a` |

## Measurements
| Measure | Result |
| --- | --- |
| Executions completed | 24 / 24 (no incomplete-capture files) |
| Final-context hash reproduced across runs | 12 / 12 |
| Primary in pre-budget pool | 10 / 12 |
| Primary delivered in final context | 7 / 12 |
| Named cases: in pool / delivered | 7 / 8 and 6 / 8 |
| Natural cases: in pool / delivered | 3 / 4 and 1 / 4 |
| Discovery misses (not in pool) | H1 (named), P4 (natural) |
| Pool-to-context delivery losses | H4 (rank 21), W1 (rank 32), W2 (rank 10) |
| Final-context size | 3972-4094 bytes, all within the 4096 cap |
| Event log | 1,806 lines parse; 891 HTTP completions all status 200; starts and completions balance |

Pre-registration Run discipline 1 (control first, replayed twice, hashes must reproduce) is
**satisfied for the captured final contexts**. Hash reproduction does not establish answer
reproduction or correctness (S8 was not assessed).

W2 is the only named case whose primary is in the pool but not delivered. These observations are
not candidate outcomes and are not grounds for tuning the mechanism (Run discipline 3).

## Discovery versus delivery, and what is not shown
"Not in pool" means absent from the captured pre-budget list; it does not prove absence at every
earlier retrieval stage. The delivery losses are relative to the observed pool. These
measurements alone do not isolate document selection, adapter ordering or byte allocation as the
cause.

## Primary delivery is not the delivery gate
The table measures one thing: whether a chunk of the primary function reached the final context.
It is **not** the frozen delivery gate (GO-rate addendum section 2), which requires S3 (every frozen
operation and dependency expression present), S4 faithfulness, S5 structure sufficiency and S6
budget.
- **S3:** not scored for any control case. Seven primary deliveries are not seven gate passes, and
  five absent primaries are not a count of control gate failures.
- **S4 / S5:** not assessed.
- **S6:** byte compliance (all contexts at most 4096 bytes) is verified. That is the only gate
  criterion this baseline addresses.
- **wins >= 5:** reachable only if the control fails at least 5 cases at the delivery gate. That
  number is unknown until S3 is scored; primary survival cannot substitute.

## Identity: local orchestrator versus deployed services
Three SHAs are involved and they differ by design:
- **Local orchestrator** (the code that did the retrieval and context assembly):
  `2eabadd237301578df0815030639dfeed89a8867`, tracked changes false, recorded in every capture.
  This attests tracked-file cleanliness only (untracked files are not covered).
- **Remote services on ports 8001-8004:** every capture records the same self-reported
  `/version` value `82b263f8e06b106867aceb5a988ae598de101db1`. Self-reported, not independently
  attested, and not equal to the local SHA.
- **Ingestion-time runtime SHA** for the corpora: unverified in the corpus pin.

The captures state their own scope: a local unchanged-runtime replay with remote read-only HTTP
services, **not the original UI or production wire path** (see
[agent execution and verification](/DOCS/deployment/agent-execution-and-verification.md)).

## Generation identity
All captures have identical before/after generation objects (ready, non-incremental) matching the
[corpus pin](/DOCS/evaluations/code-evidence-held-out/held-out-corpus-pin.json), and every chunk's
ingestion id matches. No generation drift was observed; matching snapshots are not continuous proof
against transient mutation.

| Repository | Generation (ingestion id) | Captured source commit |
| --- | --- | --- |
| pypa/hatch | `c142f7d1-f473-4731-a33e-b0e7431e7b8d` | `740565ac2929597cb9def8d46338cbef6493fc8d` |
| pdfminer/pdfminer.six | `85085698-8251-4471-9bd2-4101f8af471e` | `a18de2a9c479b4c847538500017b449ddaec177e` |
| pallets/werkzeug | `046c6d19-baff-4f1e-912c-2734e9797914` | `585fb463d91ea384ae35e4d13ecc9294d0c911f2` |

Werkzeug uses the predeclared snapshot exception (upstream pin `b73dce5a...`, recorded shared
tree `93f10217a04d9b5b3367d57227d3fec46c7990b8`); the mapping is verified, not a fresh clone.

## Instrumentation caveats
- The synchronous observer adds a 10 s connect / 120 s read timeout when none is set. No timeout
  occurred, but it could change failure behavior.
- The observer logs starts and successful completions only; there are no dedicated exception or
  case-completed events. Complete captures and after-generation records corroborate completion.
- Request/context agreement shows what the local caller submitted, not wire-level proof of what the
  model consumed. The generation-model digest and the deployed prompt hash are not independently
  established. The compact run-settings object does not attest the expanded-document caps; those
  come from the execution contract.

## Pre-registered predictions: status
| Prediction | Status |
| --- | --- |
| P1 named, in pool => candidate delivers | Not evaluated; needs candidate results. Control baseline: 6 of 7 such cases deliver (W2 does not). |
| P2 not-named contexts identical to control | Not evaluated; needs candidate results. Control hashes for H4, P4, W1, W4 are recorded above. |
| P3 no regression | Not evaluated; needs candidate results. Control delivers 7 primaries. |
| P4 candidate alone does not reach GO | Not evaluated; needs candidate results and S3 scoring. |

## Unresolved evidence gaps
1. **Complete S3/S4/S5 scoring** of the control (and later the candidate) is outstanding; how it is
   performed must be decided before any candidate result is read against the GO thresholds.
2. **Raw captures are not hashed in `raw-index.json`** and live only on the Linux host. Recording
   them needs a copy of the 32 MB directory and `scripts/raw_index.py update`.
3. **This report relies on the independent verification** rather than a second read of the raw files.
4. **Candidate implementation authorization** is separate and not given here; the mechanism and its
   parameters must be frozen and hashed first, with a single candidate run and no tuning
   (pre-registration Run discipline 2-3).
5. The statement-level experiment additionally requires the governed ADR-055 path, generation
   fencing and R1-R7 checks (verification report, last section).
