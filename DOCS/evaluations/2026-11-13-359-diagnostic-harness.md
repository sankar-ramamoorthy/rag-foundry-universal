---
title: "#359 diagnostic harness: commands, sealing guards and fixed interpretations"
date: 2026-11-13
type: evaluation-tooling
status: current
summary: "The read-only harness that executes the frozen #359 protocol: separate preflight, E2E, ORACLE-ENTRY and scoring stages with hash checks, generic selection rules isolated from the ground truth (C3), and the readings of the frozen text fixed before any run. No run has been made."
tags: [evaluation, harness, code-intelligence, evidence-selection, overfitting, issue-359]
related:
  - "[Issue #359](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/359)"
  - "[#359 protocol (frozen at 45f34e1)](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md)"
  - "[Codex handoff](/DOCS/notes/20261113-359-codex-independent-evaluation-handoff.md)"
---

# #359 diagnostic harness

The harness executes the [frozen protocol](/DOCS/evaluations/2026-11-13-359-route-grounded-evidence-selection-protocol.md).
It does not change retrieval behaviour or the selection rules. **No evaluation
has been run with it.**

## Files

| File | Role |
|---|---|
| `scripts/evidence_selection_359_rules.py` | The generic rules only: Stage RI, arms G0–G3, passage units. No I/O. It must not import the ground truth or scoring (C3), and a test enforces this. |
| `scripts/evidence_selection_359_scoring.py` | Hash verification, support categories, sufficiency, selection and survival metrics, budget attribution, the labelled oracle bound, and the C3 term scan. |
| `scripts/evidence_selection_359.py` | Runner. Each stage is a separate command and writes a never-overwritten raw record whose sha256 is printed for #359. |
| `DOCS/evaluations/359-primary/` | The public primary case: the Step 0 question, the protocol author's oracle entry point (§7), and §4 transcribed as `expected-chains.json`. All 18 witnesses are checked at `9f039c4` by a test. |
| `tests/test_evidence_selection_359.py` | Unit tests, plus one test that runs the whole sealed pipeline against a fake read-only stack. |

## Stages and guards

| Command | Protocol step | Guards |
|---|---|---|
| `preflight` | §7.1 | Requires the ready generation. Records the service versions, the protocol hash (on `HEAD` it must equal the frozen file) and the code hashes, and runs a C3 scan. For the primary set it also checks every §4 witness in stored text, and a missing witness fails the preflight. |
| `run-e2e` | §7.2 | Reads `questions.json` only, and verifies it against the hash posted on #359. **Refuses to run while a sealed file sits in a non-primary set directory.** Requires a passing preflight. A0 runs only for the primary set (P4). |
| `run-oracle` | §7.3 | Verifies the frozen E2E record and the revealed oracle file by hash. Refuses an oracle file holding anything but entry points, and refuses if the rules changed since E2E (C9). Labels every output `ORACLE-ENTRY`. Checks that ES is identical whenever the RI handler equals the oracle handler. |
| `score` | §7.4 | Verifies the chains file, the E2E record and the oracle record by hash, and checks that the oracle record was made against that E2E record. Then: **P3** rechecks every witness in stored text and, with `--source-repo`, at its recorded lines in the pinned source. Re-runs **C3** with the revealed terms; a hit gives exit code 4. ORACLE-ENTRY scores stay out of `end_to_end_success`. |

The self-repository sets (`primary`, `C7`) are pinned in code to §3's repository
and generation `8cbedbb9`. Every HTTP call is a read: generation, graph export,
`/trace`, node lookup, `search-by-doc` and `/version`.

## Interpretations fixed before any run

The frozen text leaves the details below open. Each reading is fixed in code
now, before any run or sealed data exists, and is copied into every raw
record. Changing one creates a new protocol version (C2).

1. **Route mentions.** Every `METHOD /path` in the question is matched, and
   the union of matching route nodes must have exactly one member. A trailing
   `.` or `/` is stripped.
2. **`unresolved_route` vs `no_route_node`.** `unresolved_route` applies when
   a route node with the same method has a router-local path that is a proper
   suffix of the question path (5a.6); otherwise the code is `no_route_node`.
   Suffix candidates are recorded but never used as entry points.
3. **Handler.** No real `HANDLED_BY` target gives `handler_missing`; more than
   one gives `ambiguous_route`.
4. **Limits.** The entry handler is at depth 0. The 300-node cap includes it.
   Each node is visited once, at its first encounter in the arm's order.
5. **Ambiguous call site (5a.2).** Two or more real CALL targets of one caller
   that share a simple name and a call-site line. None of them is followed.
6. **G3 URL literals.**
   - String literals are single-line quoted strings, and each literal segment
     of an f-string counts separately, as in Python's AST.
     `f"{settings.URL}/v1/vectors/search"` therefore yields
     `/v1/vectors/search`.
   - A literal must equal a route node's path exactly.
   - Nodes carry no line numbers, so the matched handler is added after that
     function's CALL children.
   - **C5 disclosure:** without the f-string reading, G3 would never fire on
     the primary case's H13 gap.
7. **Structural route support (§4).** For a `route` relationship, a
   `HANDLED_BY` edge from its route node to the caller that the rule used
   counts as `graph_and_source`, with `basis: structural_handled_by`. Under
   E2E, Stage RI's edge counts; under ORACLE-ENTRY it does not exist.
8. **P3 (owner decision, 2026-11-13).** A witness missing from the caller's
   stored text is scored `source_valid_index_missing`. That category is not
   support and not a selector miss. Sufficiency stays strict: every core
   relationship must be supported.
9. **C3 scan.** Paths, IDs and other terms containing punctuation are searched
   anywhere in the module. Plain words are searched in string literals,
   comments and whole identifiers, but not in standard-type method names
   after a `.` (such as `.items()`). Overlaps with a fixed list of generic
   words are reported, never silently dropped.
10. **Passage text** is fetched with `search-by-doc` (k = 100) using the
    stored Step 0 vector (§3). Any node that returns 100 chunks is listed in
    `search_by_doc_full_pages` (P5).

## Observations, no change made

- §4 lists R4 (`/v1/repos`, supporting) at line 152. That line is in
  `resolve_repo_id_http`'s docstring; the request URL is at line 155. The
  regex matches both, so the score is unaffected. The frozen table is left as
  is.
- A0 runs the unchanged local orchestrator with stubbed embedding and
  generation. It needs the deployed services, so it is covered only by the
  harness's import path, not by a test.
