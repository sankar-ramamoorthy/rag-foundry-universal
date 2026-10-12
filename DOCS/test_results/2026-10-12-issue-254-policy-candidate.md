---
title: "Issue #254: code-behavior policy candidate"
date: 2026-10-12
type: test-result
status: complete-with-answer-gate-failure
tags: [issue-254, repository-overview, policy, regression, candidate]
related:
  - "[Agent-loop completeness diagnosis](/DOCS/test_results/2026-10-12-issue-254-loop-evidence-completeness.md)"
  - "[Matched policy control comparison](/DOCS/test_results/2026-10-12-issue-254-overview-control-comparison.md)"
  - "[Dataset isolation](/DOCS/adr/ADR-054-evaluation-dataset-isolation-and-generalization.md)"
  - "[Current status](/DOCS/status.md)"
---

# Issue #254: code-behavior policy candidate

This local candidate corrects code-behavior classification and preserves
directly named current implementation evidence during overview claim selection.
It changes neither retrieval discovery nor its document, chunk, or context caps.
Production is unchanged. The matched comparison completed 30/30 requests:
the eight overview cases still pass, and the R1 implementation now survives
selection, but the R1 answer remains wrong. **The behavior gate fails.** This
is a verified selection correction in a local candidate, not a verified
end-to-end correctness fix or a candidate ready to advance to #243.

## Observable acceptance

- The original explicit-path R1 query is treated as current behavior and
  keeps current `Agent.run` evidence in final context and sources with
  claim selection enabled, with structured answers both off and on.
- The answer explains tool dispatch and result feedback rather than
  claiming the named implementation is absent.
- The eight overview questions keep their observed 8/8 acceptance.
- The original historical, fixture and implementation controls remain
  mandatory; report answer grounding separately from source access.
- The simpler `Agent.run` question must be scored for the actual agent
  loop, not treated as passing merely because it lists the right source.
- Current implementation expressly named by path or canonical fragment
  is not discarded by inventory/canonical claim selection. Archived,
  historical, and embedded-fixture evidence retains its authority checks.

## Candidate

Named code files or qualified symbols with a behavior request are classified
before incidental inventory or architecture terms. Thus a request to trace
code through a tool call is not replaced by a structural inventory question.
Historical/explicit-source requests retain their existing precedence.

Selection accepts the query and exempts directly named current code passages
from inventory/canonical-only exclusions. This safeguards explicitly requested
implementation even for a mixed question still classified as structure,
architecture, or purpose. It does not fetch extra passages, elevate archived
sources, or relax repository-subject checks. Unmentioned evidence retains the
existing selection rules. This is a bounded heuristic candidate, not a claim
that arbitrary natural-language intent classification is solved.

The classifier/selector tests use unrelated Python, TypeScript and Rust paths
and verify current behavior, mixed structure/architecture wording, current
implementation survival, and archive/fixture exclusion. Public HTTP tests
verify final-context/source survival, current-behavior focus, generation-path
selection, and no structural answer substitution with either structured flag.
Those contract tests verify mechanics, not model answer quality.

## Execution and provenance

The [raw local comparison](/DOCS/test_results/2026-10-12-issue-254-policy-candidate-comparison.json)
uses the same runner and 30-request matrix as the original control comparison.
All requests go to a local orchestrator at `127.0.0.1:8014`, using the deployed
ingestion/vector/LLM services read-only and the host's Ollama embedding endpoint.
The [local runtime record](/DOCS/test_results/2026-10-12-issue-254-policy-candidate-local-runtime.json)
records the candidate's source hashes and explicit effective local settings.
The local service loads no `.env` file and uses documented defaults with only
service/embedding URL overrides. Its `/version` fields are `unknown`/`dev`;
the dirty candidate is identified by recorded source hashes, not by falsely
claiming an unchanged commit contains these edits.

Local HEAD and locally available `origin/main` are
`24d956184d566753fe5ac80f57132191a4f7c3e1`. Deployed services report that same
commit, but run the original policy; no deployed/local configuration parity
is assumed. Both local arms run in one candidate process and compare against
the same generation. The unchanged Foundry pin is generation
`854e8484-7144-45c4-951b-ad8bc647c4bf`, source
`f344bd58ffde5d98f4993bc0a27192b50c8decc3`; the Python-agent pin is generation
`24f827d7-a33b-45f7-93f4-ff6e5eaf3856`, source
`f854303e6e44ff95d94792d24868442a28080ba2`.

These are development/regression results. Grounding of the simple method
question, incomplete cross-file evidence, and misleading reranker drop
diagnostics remain separate defects. The candidate is not deployed and
does not establish held-out generalization under #243.

## Matched results

The [completion audit](/DOCS/test_results/2026-10-12-issue-254-policy-candidate-audit.json)
verifies 30 unique contract requests, unchanged ready corpus/source pins,
effective control confirmation, stable runtime version responses, unchanged
candidate source hashes, reranking off, no fallback, and 4096-byte caps.
Generated answers report `ollama/Qwen3:4b`; structured answers bypass it.
All four R1 arms have identical seed and expanded canonical-ID lists.

| Frozen case | Local overview off | Local candidate | Judgment |
| --- | --- | --- | --- |
| Q1 | F | P | Off omits required inventory facets and generalizes service properties; candidate matches complete inventory and gaps. |
| Q2 | F | P | Off equates missing manifest with no package; candidate reports observed package markers and unknowns. |
| Q3 | F | P | Off misplaces service tests under root `tests` and generalizes manifests; candidate binds actual directories and service facts to the selected generation. |
| Q4 | F | P | Off gives a narrow ingestion diagram; candidate separates HTTP, datastore and dependency relationships with qualified scope. |
| Q5 | F | P | Candidate retains/cites canonical purpose and gives correct code/document RAG purpose. |
| Q5k20 | F | P | Same purpose/source result at `top_k=20`. |
| Q6 | P | P | Both retain/cite canonical purpose and describe read-only graph-aware RAG. |
| Q7 | F | P | Off substitutes an ingestion subsystem; candidate states supported languages and code/document scope. |
| C1 | P | F (grounding) | Candidate correctly explains historical fixture contamination but adds unsupported claims that ORIENT had properly indexed the correct current inventory during the incident. The pinned September 6 note discusses experiments and proposed structural artifacts, not that asserted ORIENT implementation state. |
| C2 | Source F | P | Candidate keeps the exact smoke-fixture README and correctly describes its test role. |
| C3 | Source F | P | Candidate keeps the exact `GraphAssembler.assemble` source and describes construction and resolution. |

Overview acceptance remains **8/8 versus 1/8**. Strict full-suite acceptance
remains **10/11 versus 2/11**; the original control C1 is still an answer
failure. The four candidate structured answers are byte-for-byte unchanged
from the earlier production comparison and have no validation errors.
Canonical purpose survival/source listing remains 4/4 versus 1/4; C1-C3 exact
source survival/listing remains 3/3 versus 1/3. These access measurements do
not substitute for the answer judgments in the table.

| Python-agent control | Final current evidence | Answer judgment |
| --- | --- | --- |
| R1 / normal | `Agent.run` survives and is cited/listed | The tool/result loop is correct; complete three-symbol trace remains unsupported. |
| R1 / overview off | `Agent.run` survives and is cited/listed | Explains tool execution and feedback using the ADR; full current cross-file trace remains incomplete. |
| R1 / claim only | `Agent.run` and exact `start_cli` survive and are listed | F: invents tool parsing from the prompt and direct return to CLI; omits result feedback to LLM. |
| R1 / candidate | `Agent.run` and exact `start_cli` survive and are listed | F: invents tool/argument extraction from the prompt and console-result handling; does not describe feedback to LLM. |
| R1_method / normal and off | Current method survives and is listed | F under the recorded loop obligation: gives correct docstring/signature and fallback details but no tool/model loop explanation. |
| R1_method / claim only and candidate | Same final manifests as normal/off | F: again associates `Agent.run` with the historical skill runner and omits the loop. |

Both claim-on R1 requests now report `current_behavior`, have no policy
exclusion for current `Agent.run`, retain three of its final passages, and
produce four current-code source identities instead of zero sources. The
exact `start_cli` method also survives. The exact `main` method survives
chunk-count limits but is excluded by the context-byte budget; a `main.py`
file passage survives. This is measured
evidence preservation, not proof that every relevant handoff is present.
The retained `Agent.run` passages cover input handling, repeated-call handling
and tool dispatch/logging, but do not include the complete provider-generation
and tool-result memory-update transitions visible in the pinned full source.
The answers invent those missing semantics instead of qualifying the gap.

**Attribution corrected by the subsequent
[completeness diagnosis](/DOCS/test_results/2026-10-12-issue-254-loop-evidence-completeness.md):**
this report originally called the exact `main` loss a chunk-count loss, but
the saved traces show context-budget loss in all four R1 arms. The new
observers confirm that boundary. They also verify that file-level passages
deliver the startup and CLI-to-agent handoffs even though exact method
passages are absent or incomplete; method-ID absence alone is not semantic
evidence absence. Critical provider/result-feedback passages are indexed
but outside the three-chunk fetch cut.

The audit also runs the original HEAD classifier/selector and the candidate
classifier/selector over the captured R1 manifest identities/provenance.
The original obligation is `current_structure` and removes all 10 entries;
the candidate obligation is `current_behavior` and retains all 10. This
isolates the selection delta without claiming deployed/local configuration
parity or treating that selector counterfactual as an HTTP answer evaluation.

## Gate and remaining work

The narrow software/evidence obligations pass: behavior focus, current-source
survival, archive/fixture boundaries and retained overview gains. The answer
obligations fail: R1 claim-on answers do not trace result feedback, C1 adds
unsupported history, and the simple method answer does not correctly explain
the loop. No pass is inferred from unit tests or source listing.

Keep this candidate unmerged and undeployed while these behavior gates fail.
No prompt, authority ranking, retrieval budget, chunk-fetch or diagnostic
label change was added to make the current case pass. #254 stays open;
the historical seed discrepancy is still separate and unassigned a cause.
The next bounded investigation should measure which provider/result-update
passages are fetched and survive, and distinguish missing evidence from
incorrect synthesis. #243's independent evaluation remains the next stage
after the mandatory regression gates, with its source/questions/authority
contract frozen before answers or further candidate tuning.

Local validation: **397 non-integration orchestrator tests passed**, including
the new selection and public HTTP contracts; one external integration test
was excluded. Ruff and Pyright passed for both changed runtime files and
their tests. The 30-request live comparison is the answer-behavior evidence;
its failed gate is not overridden by those local checks.
