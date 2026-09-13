---
title: "Pattern: Three-Layer Model/Provider Configuration"
date: 2026-09-13
type: pattern
status: accepted
tags: [pattern, configuration, architecture, llm]
related:
  - "[LLM Provider Plan — LiteLLM & Model Switching](/DOCS/audit/06-LLM-Provider-LiteLLM-Plan.md)"
  - "[Documentation Standard — OKF v0.2](/DOCS/standards/okf-documentation.md)"
---

# Pattern: Three-Layer Model/Provider Configuration

Framework-agnostic. Not specific to LLMs, LiteLLM, or this repo — applies
to any system that picks a concrete backend (a model, a queue, a search
index, a payment processor) from among several pluggable providers.

## Problem

Config that mixes "what exists," "what's discoverable right now," and
"what's active right now" into one committed file eventually can't be
both source-controlled AND live-adjustable. Two symptoms show up:

1. Trying a newly available option (a new free-tier model, a new backend
   version) requires editing the committed file, opening a PR, merging,
   rebuilding, and redeploying — friction wildly disproportionate to the
   actual change ("use this other one instead").
2. The file's own intent drifts from its actual deployment reality. This
   repo's `llm_service/models.yaml` states in its own header comment that
   it was meant to allow "changes without an application deploy" — never
   actually true in production, because the production Compose override
   strips all application-source bind mounts for immutable-image
   deploys. The file could never be live-edited on the host it mattered
   most on.

## The three layers

1. **Provider config — deployment config.** Which provider/backend
   *families* exist, their endpoint/base URL, credential lookup (env var
   name, not the credential itself), timeout/retry capability. Changes
   rarely; a deploy is an acceptable cost when it does. Stays committed.

2. **Catalog — dynamic external state, advisory only.** For any provider
   that exposes a "what's available right now" listing, query it live,
   cache the result with a TTL, and degrade to the last-known-good
   result on a fetch failure rather than failing the caller. **Never a
   gate**: a consumer must always be able to use something the catalog
   has never heard of, no longer lists, or is temporarily unable to
   fetch — the catalog is for convenience, visibility, and filtering
   (e.g. surfacing only free-tier options), never validation. Only
   assert a derived fact (like "this is free") where the provider's own
   response actually gives that evidence — don't infer it from a naming
   convention or the absence of a field.

3. **Policy — runtime-persisted operator choice.** Which concrete option
   is active for each named role/slot right now. Persisted outside
   version control (a small file, a KV entry — never version control
   itself, and not necessarily a database if the owning service isn't
   allowed direct DB access), mutated by a minimal, narrowly-scoped admin
   action, and picked up by a **runtime refresh**: persist the change,
   invalidate any in-memory singleton/cache derived from it, rebuild
   lazily on next access. Call it that rather than "hot reload" — nothing
   is pushed or reloaded eagerly, and naming it precisely avoids implying
   machinery (a push channel, a live broadcast) that isn't there.

## Decision guide

- Fixed, small set of backends with no live "what's available" concept
  (e.g. exactly two payment processors, manually onboarded) → layers 1
  and 3 only; skip layer 2's TTL/cache machinery entirely.
- A catalog that never changes in practice → still fine to build layer 2
  for the free-tier/visibility win, but a long TTL (or none) is fine.
- No operator-adjustable "active choice" concept at all (every consumer
  always names its own backend explicitly, no default/slot concept) →
  layer 3 isn't needed; layers 1 and 2 alone still fix the "must edit a
  committed file to try something new" problem via passthrough.

## Implementation checklist

- **Resolution order**: alias/slot lookup → passthrough of an unlisted
  raw identifier → error. The passthrough is what actually kills the
  "must edit a file" friction — build and preserve it before anything
  else.
- **Catalog cache/degrade semantics**: TTL-cached, degrade to
  last-known-good on fetch failure, never raise from a catalog read.
  Skip the fetch entirely (don't attempt-and-fail) when a required
  credential is absent — cheaper and avoids guaranteed-failure calls on
  every TTL cycle.
- **Atomic writes**: policy persistence should write to a temp file in
  the same directory, then atomically rename over the target — a reader
  should never observe a torn write.
- **Concurrency**: a language-level lock (e.g. `threading.Lock`) only
  protects threads inside one process. If the service can ever run
  multiple worker processes, use a real cross-process mechanism (e.g. a
  filesystem advisory lock alongside the atomic rename) — and document
  the scope explicitly (single-host vs. distributed) rather than
  silently assuming single-process forever.
- **Auth minimalism**: gate the *mutation*, not the read. A read-only
  discovery/status endpoint can usually stay open; only the endpoint
  that changes persisted state needs auth, and it should fail closed
  (refuse writes) if no credential is configured, rather than silently
  accepting unauthenticated writes on a fresh deploy.
- **Validate writes against resolution, not the catalog**: a policy
  write should be validated by attempting to resolve/parse it the same
  way a normal request would, never by checking catalog membership — the
  catalog can be stale or incomplete and must never block a legitimate
  write.

## Anti-pattern

Don't reuse layer 1's own config file, mount, or storage location for
layer 3's runtime state. The moment deployment infrastructure treats
that file/mount as immutable (strips it from a hardened deploy, bakes it
into an image, etc.), layer 3 breaks silently — exactly what happened
here: `models.yaml`'s own comments describe live-editability that
production's Compose override had already made impossible. Give layer 3
its own dedicated, explicitly-provisioned storage location from the
start.

## Worked example (this repo)

`llm_service`'s model/provider configuration (WP-M6/WP-M7,
[[audit/06-LLM-Provider-LiteLLM-Plan]]):

- Layer 1: `llm_service/models.yaml`'s `endpoints:`/`providers:`
  sections, read by `llm_service/src/core/model_registry.py`.
- Layer 2: `llm_service/src/core/model_catalog.py` — per-provider
  fetchers, TTL cache, free-tier detection only where a provider's
  response actually carries pricing data.
- Layer 3: `llm_service/src/core/model_policy.py` (file-backed, atomic
  writes, cross-process file lock) + `llm_service/src/api/v1/admin.py`
  (shared-secret-gated write endpoints, fail-closed) +
  `ModelRegistry`'s policy-merge in `model_registry.py` + the runtime
  policy refresh via `reset_registry()`.
