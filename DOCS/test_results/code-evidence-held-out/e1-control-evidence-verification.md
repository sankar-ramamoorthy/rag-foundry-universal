# E1 control evidence verification

Verified 2026-11-08. Both control runs reproduce all 12 final-context hashes. All 24 independently recomputed hashes agree with their capture summaries and the aggregate summary. No captured generation drift or incomplete execution was found. Candidate predictions remain unevaluated.

## Files and methodology

Read all 24 `/evidence/e1/held-out-control-run{1,2}-{H1–H4,P1–P4,W1–W4}.json` captures, `held-out-control-summary.json`, and every line of `capture-events.jsonl`. The directory contains exactly these 26 files, with each expected case once per run and no incomplete-run artifacts.

Read the frozen held-out manifest, named-symbol-first preregistration, certified `held-out-corpus-pin.json`, snapshot-tree clarification, E1 execution contract, prototype contract, statement-level contract and GO-rate addendum under `/workspace/DOCS/evaluations/`; also inspected the capture/observer implementations in `scripts/held_out_control.py` and `scripts/code_evidence_experiment.py`, repository guidance, and the corpus-certification note. Frozen manifest, preregistration, statement contract, addendum, stratification and clarification hashes match their sidecars; the development manifest checksum also matches. Held-out manifest SHA-256: `ef5727be08d1a569957760e9014b884d83c4e71a70e25e7ddf2e92c16f97cfc5`. All 17 embedded source texts hash to their manifest values.

Used independent standard-library inspection, without importing or executing the harness. For every capture, hashed actual `assembled_context` UTF-8 bytes without normalization; checked recorded SHA-256, byte length, aggregate summary, generation-request context, last asynchronous request context and response retrieval-plan byte count. Recomputed canonical-label primary presence in pre-budget/final chunks, first zero-based pool chunk rank and whole-identifier-token named classification from the frozen query. All recomputed measurement dictionaries agree with both summaries in both runs. Primary source-label presence was also checked directly in actual context text.

## Results by case

Values hold for both runs. Rank is zero-based in the pre-budget chunk list, not vector rank or document rank. Delivered means at least one primary-labeled chunk, not full evidence coverage. Every hash below was independently recomputed for both captures.

| Case | Query | In pool | Rank | Delivered | Bytes | SHA-256 (both runs) |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | Named | False | None | False | 4023 | `facaf4d82d4163d65ba052c89ef2d5229b512c070844ad290fff4a971d8bff6c` |
| H2 | Named | True | 9 | True | 4045 | `e5654ad3b6552ae0b792954629f47abed2f980b2108ecacc50da8c424a2258e4` |
| H3 | Named | True | 0 | True | 4087 | `7b7bf66842c69908ae38f7bc854cb6b26b7cf94b610bea6cbe84b63678c80e79` |
| H4 | Natural | True | 21 | False | 4058 | `890900dfad84aba246c183f3e4eed1cb4d18e28d44d0b5c8b3bef21652ff3e19` |
| P1 | Named | True | 3 | True | 4085 | `0ec279a9f81f897fc3532c1b68b3423a97c5188bc2a6bd934ba7e6c13e412cd5` |
| P2 | Named | True | 0 | True | 4045 | `80f25285a192788d987f7a5592a6944d2f1e3a7f99d7ac16dd0f4996467d1f63` |
| P3 | Named | True | 0 | True | 3998 | `411a38512bd0fedf008c5095fe0061547a2072e92132e1c4d07f733293c62239` |
| P4 | Natural | False | None | False | 4094 | `9c448b4e8dd8fa63c7c8dcaef9c37d73a475e24d5fb847895c8f05edb69b231c` |
| W1 | Natural | True | 32 | False | 4016 | `657d906964eafe0632cc9f2b76f8853f5874157ad41dc628bf904578f0b31a6d` |
| W2 | Named | True | 10 | False | 3972 | `500ce766e85513b40e96aacc79780f3e79cf5c6534e8bd2215d22974f77f89ec` |
| W3 | Named | True | 0 | True | 4040 | `c9c01fe47147bce61f96f30452398de446e50e3f8d12aa416059019405e93e98` |
| W4 | Natural | True | 9 | True | 4076 | `06caaa9ad765adff915640f4ce89ae88aa217b6882f7e0f73c0eb3d09e71d89a` |

## Reproducibility and identity

Run 1 and run 2 each have 12/12 matching recorded/recomputed hashes; cross-run agreement is 12/12. Captures consistently record local runtime `2eabadd237301578df0815030639dfeed89a8867`, tracked changes false; checkout HEAD matches. This attests tracked cleanliness only. All captures share settings: top_k 20, max_chunks_per_doc 5, rerank false, overview flags false, model `ollama/Qwen3:4b`, max_total_tokens 4096. That last field governs a byte cap here: actual final contexts span 3972–4094 UTF-8 bytes. Expanded-document/chunk and adapter caps are specified by the execution contract but not independently attested by the compact run-settings object.

All service-version objects are identical across captures: ports 8001–8004 self-report `82b263f8e06b106867aceb5a988ae598de101db1`. The local orchestrator SHA differs from that remote service SHA; the captures explicitly describe local unchanged-runtime replay with remote HTTP services, not the original UI or production wire path.

Every capture has identical before/after generation objects, ready and nonincremental. Repo IDs, ingestion IDs and recorded source commits match the certified pins; every pre-budget/final chunk metadata ingestion ID also matches.

| Repository | Generation | Captured source commit |
| --- | --- | --- |
| pypa/hatch | c142f7d1-f473-4731-a33e-b0e7431e7b8d | 740565ac2929597cb9def8d46338cbef6493fc8d |
| pdfminer/pdfminer.six | 85085698-8251-4471-9bd2-4101f8af471e | a18de2a9c479b4c847538500017b449ddaec177e |
| pallets/werkzeug | 046c6d19-baff-4f1e-912c-2734e9797914 | 585fb463d91ea384ae35e4d13ecc9294d0c911f2 |

Werkzeug uses the predeclared snapshot exception: upstream pin `b73dce5a2ce14f7c7fd645699d1d878de48d2948`, recorded shared tree `93f10217a04d9b5b3367d57227d3fec46c7990b8`. This review verifies the pin/clarification mapping, not a fresh clone. Certification records stored-function matches of 5/5, 6/6 and 6/6 respectively; no fresh database certification was performed.

## Discovery versus delivery

Primary is in pool in 10/12 cases and delivered in 7/12. H1 and P4 are pool discovery misses, which does not prove absence at every earlier retrieval stage. H4, W1 and W2 are delivery losses relative to the observed pool, at ranks 21, 32 and 10. These measurements alone do not isolate document selection, adapter ordering or byte allocation as the cause.

Named cases: 7/8 in pool, 6/8 delivered. Natural cases: 3/4 in pool, 1/4 delivered. W2 is the sole named case in pool but absent from final context. These observations are not candidate outcomes or permission to tune the mechanism.

## Instrumentation and limitations

All 1,806 event lines parse: 24 case starts, 840 asynchronous HTTP starts/completions and 51 synchronous starts/completions. All 891 recorded HTTP completions have status 200. Start/completion counts balance globally and within every case segment. No deadline errors, observer failures, exceptions, non-200 completions or unmatched starts are recorded. Complete captures, generation responses and after-generation identities corroborate completion.

The synchronous observer supplies a 10-second connect / 120-second read timeout when absent. No timeout was observed, but this changes possible failure behavior. The observer logs starts and successful completions, without dedicated exception or case-completed events; absence of error strings alone would not establish success. Balanced events do not prove every I/O path was observed: generation/version GETs use another path, and concurrent completion order need not follow start order.

Captured request/context agreement establishes what the local caller submitted, not independent wire attestation of model consumption. Service versions are self-reported. Exact generation-model digest and deployed prompt hash are not independently established here. The corpus pin explicitly records ingestion-time embedder digest as inferred from host state, and ingestion-time runtime SHA as unverified. Matching endpoint snapshots and chunk identities show no observed drift, not continuous proof against transient mutation. Context reproduction does not establish answer reproduction or correctness; S8 was not assessed. Historical certification text saying E1 had not run predates these later captures.

## Frozen criteria and prerequisites

The preregistered control-first/twice requirement is satisfied for captured final contexts. Predictions P1–P4 all concern candidate results and remain unevaluated: there are no candidate captures. Primary delivery is not complete S3 operation/dependency coverage, S4 faithfulness or S5 structure sufficiency. This report verifies S6 byte compliance but does not certify statement-mode passes, fallbacks or answer quality. Seven primary deliveries are not seven full delivery-gate passes; five absent primaries are not a complete count of control gate failures.

Before candidate implementation/run, obtain the separately required implementation authorization, freeze/hash the exact mechanism and parameters, preserve corpus generations/settings and the single candidate run/no-tuning discipline. Do not redesign from these results: doing so requires a new dated declaration and makes these cases development data for the change, requiring a new held-out set. Keep named-symbol ordering separate from statement delivery. A statement-level experiment also requires the governed ADR-055 node-text path, generation fencing, allowed-input boundary, R1–R7 checks, provenance and explicit fallbacks.

Before deciding candidate outcomes, score complete control and candidate operation/dependency evidence. The frozen addendum requires at least 10/12 delivery passes, five wins, at least 3/4 passes per repository and no regression or S4/S5/S6 violation. Establish at least five actual control gate failures to show five wins are possible; primary survival cannot substitute. GO permits designing a larger independent evaluation, not production adoption. No candidate GO/NO-GO verdict follows from these controls.

Only this requested report was written. No harness or held-out question was executed, and no source, frozen artifact, raw capture, service, database, production release, candidate, commit or PR was changed.
