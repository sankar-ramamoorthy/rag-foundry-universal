---
title: "RepoProbe pilot: walker-7 (contamination-free evidence-survival check)"
date: 2026-09-15
type: test-result
status: complete
issue: "#141"
tags:
  - rag
  - evaluation
  - retrieval
  - repoprobe
  - external-benchmark
  - contamination-free
related:
  - "[WP-S8 rerank evidence-survival run](/DOCS/test_results/2026-09-15-wp-s8-rerank-evidence-survival-run.md)"
  - "[Issue #141](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/141)"
  - "[RepoProbe](https://github.com/Tencent-Hunyuan/RepoProbe)"
---

# RepoProbe pilot: walker-7 (contamination-free evidence-survival check)

Follow-up to `DOCS/test_results/2026-09-15-wp-s8-rerank-evidence-survival-run.md`, which found the
`rag-foundry-universal` side of our own frozen evidence-survival set self-contaminated (issue #141) —
6 of 7 candidates had zero real-source chunks reach final context, because the question text lives
verbatim inside our own ingested corpus. [RepoProbe](https://github.com/Tencent-Hunyuan/RepoProbe)
(ASE 2026) was identified as a structural fix: 500 questions across 50 real GitHub repos, each pinned
to an exact commit, drawn from real GitHub Discussions and graded by a checklist — none of it derived
from or stored in our own corpus, so the contamination failure mode this issue documents cannot occur.

This is a first, single-question pilot to check whether the harness (ingest -> `/v1/rag` -> grade
against RepoProbe's checklist) works at all, before committing to a larger run.

## Repo and pinning caveat

- Repo: [`abenz1267/walker`](https://github.com/abenz1267/walker) (Rust, GTK4 application launcher),
  RepoProbe repo entry pinned to commit `1395d9205253c7038698e1dcca9c4d1d7dfd567b`.
- **Ingested via the Gradio page at current `master` (`26b9f3fb-e4e6-43ce-b674-a2f1d8195d31`,
  repo_id `0de056b3-46af-5839-83d9-1fb938b77d96`), not the pinned commit** — our ingestion pipeline
  (both `/v1/ingest-repo` and the Gradio form) only accepts `git_url` and always clones the current
  default branch; there is no ref/commit-pinning field today. This is an open gap (see "What this
  pilot recommends" below).
- Chose `walker` specifically because it was the lowest-drift Rust/Python/TS/JS repo in RepoProbe's
  50 (52 commits ahead of its pin, vs. FieldStation42's 182) — small enough that individual questions
  could be manually verified drift-safe rather than accepting the gap blindly.
- Before running, verified directly against current HEAD (not assumed) that walker-7's specific graded
  facts survived those 52 commits: `src/config.rs:88` still has `pub theme: Option<String>` as a
  per-module override field, which is exactly what the checklist grades.

## Question: walker-7 ("Emoji Size")

> Is there a way to increase the size of emojis? I checked the config and css, but I can't see an
> obvious way to do this.

**Expected answer (RepoProbe):** increasing emoji size requires setting a custom `theme` for the
module in question — each module can have its own theme (`theme` property), since emojis render via
that module's theme/font settings.

**Checklist (10 pts):** 4 — theme-based solution identified; 3 — module-specific theming concept
explained; 2 — correct `theme` property/implementation guidance; 1 — clear, no hallucinations.

## Result: 0/10 in both conditions, but two different failure modes

Ran via `/v1/rag`, `top_k=5`, `repo_id=0de056b3-46af-5839-83d9-1fb938b77d96`, `rerank=false` and
`rerank=true`. **Confirmed first, not assumed:** `src/config.rs` and `src/theme/mod.rs` (where the
answer lives) both exist in the ingested graph
(`GET /v1/graph/repos/{repo_id}/nodes?canonical_ids=src/config.rs,src/theme/mod.rs` returns both).
This rules out an ingestion/graph-completeness gap — the failure is retrieval, not coverage.

Neither condition's `final_context_manifest` contained `src/config.rs` or `src/theme/mod.rs` at all.
Both conditions' final context was limited to `src/main.rs` and `src/preview/mod.rs`.

| Condition | Model behavior | Score |
|---|---|---|
| `rerank=false` | Fabricated a plausible-but-wrong GTK4/CSS answer (`.preview-text-view { font-size: 24px }`, `text_view.add_css_class(...)`) — grounded in the *wrong* retrieved file (`preview/mod.rs`), not in the real mechanism. Fails the checklist's own "no hallucinations" clause. | **0/10** |
| `rerank=true` | Correctly stated the retrieved context contained no emoji-sizing information and declined to answer rather than invent one. | **0/10** (no theme/module content), but no hallucination |

## Why this is still a useful result

- **This is a genuine, uncontaminated seed-retrieval miss** (WP-T1e's Category A) — the first one this
  project has been able to observe cleanly, since every `rag-foundry-universal`-side attempt at this is
  confounded by issue #141. `hybrid_retrieve` never surfaced `src/config.rs` or `src/theme/mod.rs` for
  this query wording, in either rerank condition, despite both existing in the graph.
  the harness works: ingest → query → check `final_context_manifest` against a known target → grade
  against an external checklist, all without touching our own corpus.
- **The rerank on/off difference is a real, if secondary, signal**: reranking didn't fix the miss, but
  it changed *how* the model failed — honest refusal instead of confident fabrication. Consistent with
  what `2026-09-15-wp-s8-rerank-evidence-survival-run.md` observed on the contaminated RF corpus
  (reranking narrows the pool it's given; it doesn't invent evidence that was never retrieved).
- Per this project's decision principle (`DOCS/evaluations/2026-09-07-evidence-survival-question-set.md`),
  one question is not enough to act on. A second RepoProbe walker question was planned as the next step
  to check whether this is a one-off query-wording miss or a repeating pattern.

## Second question: walker-4 ("go back" function for custom menus) — miss repeats

`walker-6` (the originally planned second question) turned out not to be source-answerable at all
(next section) — vetted `walker-4` in its place using the same drift/grounding discipline as
`walker-7`: confirmed directly against current HEAD that `src/keybinds.rs` contains both `ClearReload`
(enum variant, line 30-31) and the `menus:parent` action string (line 524), the two real mechanisms
the expected answer cites, before running it.

> Would it be possible to add a bind that goes back to the previous menu in walker/elephant custom
> menus? Use case: a main menu with entries that open submenus.

**Expected answer:** already implemented — either set a `parent` on the menu, or switch provider via
a `provider:<provider>` action (e.g. `{ action = "set:omarchy", bind = "Escape", ... }` or
`{ action = "provider:calc", bind = "Escape", ... }`).

**Checklist (10 pts):** 2 — correctly says already implemented (not something to build); 4 — explains
both methods (parent / provider-switch); 3 — accurate code examples of both action formats; 1 — clear,
no hallucinations.

Ran the same way (`top_k=5`, `rerank=false`/`true`). This time `src/keybinds.rs#setup_binds` *did*
reach `final_context_manifest` in both conditions — a different, more specific failure than walker-7's
total miss:

| Condition | Model behavior | Score |
|---|---|---|
| `rerank=false` | Did not use the retrieved `keybinds.rs` content at all. Fabricated an entire custom-implementation plan from scratch (a `history: Vec<String>` field, a new `Backspace` keybinding, `get_submenu()` helper) — invented Rust code presented as if it were real, and explicitly told the user "your menu system **must** have a way to identify submenus... If not, add a simple check," directly contradicting the checklist's core point that this is *already implemented*. | **0/10** |
| `rerank=true` | Used real retrieved code this time (no invented structs) but attributed the wrong mechanism — pointed at `ACTION_SELECT_PREVIOUS`/`parse_bind` (an unrelated result-selection keybind also present in `setup_binds`) rather than `menus:parent`/`provider:<provider>`. Correctly said the feature is already implemented (partial credit on the first checklist item), but explained the wrong method with no correct code example of either real action format. | **~2/10** (partial credit for "already implemented," everything else wrong) |

The failure mode here is *not* the same as walker-7's — `keybinds.rs` was correctly identified as
relevant, but the specific chunk/content that reached context was the wrong part of the same file
(or file-level context wasn't granular enough to distinguish the real mechanism from an unrelated
keybind in the same function). Both conditions failed to deliver the real answer; only the *way* they
failed differed (fabrication vs. wrong-but-real-code misattribution), same pattern as walker-7's
fabrication-vs-honest-refusal split.

**This is the second independent, source-verified, uncontaminated RepoProbe question where the real
answer-bearing content did not reach the model in a usable form, in either rerank condition** — per
this project's decision principle (recur on ≥2 independent questions before acting), that's the
threshold. Filed as issue #156 (see below). Note the two misses are at different retrieval sub-stages
(walker-7: complete seed miss, nothing relevant retrieved; walker-4: right artifact retrieved, wrong
sub-content reached context) — recorded as such, not collapsed into one mechanism, since the fix (if
any) would differ.

## walker-6 was skipped, not run — not source-answerable at all

Before running the planned second question (`walker-6`, a Bitwarden CLI clipboard plugin), checked
whether its answer is even derivable from the ingested repo. It is not, for two independent reasons:

1. **Wrong repo.** `walker` (this repo, the frontend/UI) and
   [`elephant`](https://github.com/abenz1267/elephant) (a separate repo, the provider backend) are
   split projects — confirmed via `walker`'s own README, which lists "Bitwarden/1Password" under
   "The following Elephant providers are implemented by default." `elephant` was never ingested.
2. **Never merged.** Even setting aside the repo split, walker-6's actual checklist target (a
   `config.toml` plugin block plus two bash scripts, `bitwarden_src.sh`/`bitwarden_cmd.sh`) is a
   community member's DIY workaround posted directly in the GitHub Discussion — a repo-wide code
   search for `bitwarden_src` returns zero results in `walker`. It was never committed to either repo.

Running walker-6 against this single-repo ingestion would produce a guaranteed 0/10 that reflects
corpus scope, not retrieval or generation quality — not a fair or informative test. Not run.

Also worth recording: this same repo-split problem rules out several other `walker` questions on
inspection (`walker-2`/clipboard `max_entries`, `walker-3`/files `min_score` — both explicitly answered
by pointing at `elephant`'s own config file). RepoProbe's own taxonomy doesn't distinguish
single-repo-answerable questions from ones requiring a linked companion repo; that distinction has to
be checked per-question before use here, the same discipline applied to walker-7's drift check.

## What this pilot recommends

- The harness works end-to-end: external, pinned, checklist-graded questions against our own live
  `/v1/rag` produce real, uncontaminated evidence-survival signal — validates the direction from
  `DOCS/test_results/2026-09-15-wp-s8-rerank-evidence-survival-run.md`'s recommendation.
- **Before scaling this up:** `/v1/ingest-repo` (API and Gradio form) needs a ref/commit-pinning
  field. This pilot worked around the gap by manually vetting one low-drift question against current
  HEAD; that doesn't scale to RepoProbe's 500 questions across 50 repos.
- **Before picking more questions from any RepoProbe repo:** check whether the repo has a companion
  project (like `elephant`) that answers in-scope-looking questions the primary repo can't. Not
  assumed to be visible from `repos_info.json` alone.
- Two confirmed, independent, source-verified misses (walker-7, walker-4) meet this project's
  decision-principle threshold. Filed as [issue #156](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/156).
  Given the two misses are at different sub-stages (seed vs. chunk-selection-within-artifact), the
  issue is scoped as an investigation, not a specific fix — same discipline as issue #141.

## Related

- Issue #141 (open) — this pilot's motivation; the contamination pattern that blocks the
  `rag-foundry-universal`-side evaluation this was meant to route around.
- `DOCS/test_results/2026-09-15-wp-s8-rerank-evidence-survival-run.md` — the run that first surfaced
  the need for a contamination-free evaluation surface.
