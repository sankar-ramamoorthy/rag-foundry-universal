# Foundry product frontend implementation plan

**Status:** Proposed for owner review, November 23, 2026

Implements the [first-release spec](spec.md) under
[ADR-057](../../DOCS/adr/ADR-057-react-typescript-product-frontend.md).
The [assessment](../../DOCS/notes/20261123-frontend-api-assessment.md)
maps current API coverage and dependencies.

## Sequence

1. **Freeze the product API.** Use the orchestrator as the browser-facing
   backend. Reuse Orient, Locate, file listing and source reads through typed
   responses. Add a sanitized repository picker and readiness lookup backed by
   ingestion. Define a generation-pinned Ask operation over existing standard
   RAG. If further schema changes would break callers, expose them through
   additive product routes. Existing API consumers retain their contracts.
   Use stable error codes for unavailable, stale, invalid range and resource
   limits. Publish the OpenAPI artifact and generate a TypeScript client from
   the product subset. Add contract fixtures before UI coding.
2. **Build Orient, Locate, Ask and Verify.** Put the React client in Foundry
   and provisionally build with Vite. Start with the repository picker,
   overview, path search, question panel and shared source viewer. Use the
   generated types and a lightweight client cache keyed by repository,
   generation and request parameters. Pin source reads to the cited generation,
   highlight only the returned interval, and offer a bounded window around
   the cited lines. Preserve range reasons and incomplete coverage in the UI.
3. **Integrate Investigate after its contract review.** Obtain the peri-agent
   schema through the owner. Define the Foundry request, service adapter and
   response contract before wiring the mode. Use server-configured service
   routing and deadlines. Return distinct run IDs, terminal outcomes and
   evidence references. Validate repository and generation on all returned
   references, and match source coordinates to the existing source-read
   contract. Expose the mode only where the integration is enabled. The
   browser has no direct peri-agent address.

   LAB's 0.2.0 draft reports implemented generation pinning (P1) and a
   documented malformed-run-ID response (P2). Foundry must send
   `expected_generation_id` on every Investigate submission and handle an
   asynchronous `stale_generation` result. A mismatch may report the
   observed generation as diagnostic metadata. Evidence and findings must
   remain scoped to the requested generation. Use the fixture profile for
   contract integration and the scripted live profile for its fixed
   question. Free-form questions (P3) are available only in the metered
   single-run profile. A reusable free-form profile and an integration check
   against a rebuilt service remain release dependencies. Model profile and
   run authorization are separate owner decisions.

   Keep the service token server-side. Bind run IDs to authorized callers
   and repositories and recheck access on status and citation requests.
   When a citation belongs to an older generation, show its recorded
   excerpt and generation and disable the source jump.
4. **Package and verify.** Use a dedicated multi-stage frontend image with a
   static web-server runtime. Configure a development proxy for the same browser
   paths used in production. Review a same-origin gateway or equivalent route
   mapping before production exposure. Require backend enforcement of caller
   access across listing, reads and both modes. Treat external exposure as
   pending until that enforcement and the routing arrangement are reviewed.
   Verify Gradio coexistence. The operator owns the production deployment.

## Test and review gates

- Contract tests assert schema parity, sanitized repo fields, generation
  mismatch rejection before and after work, inclusive intervals, unavailable
  source reasons and scope checks on agent responses.
- UI tests cover a complete repository-to-citation flow, ambiguous and empty
  search, no-range and stale citations, delayed responses after a context
  switch, and service timeout or unavailability. Use fixtures first.
- Before releasing either mode, exercise the accepted browser flows on a
  known indexed revision through the intended API boundary. Confirm that
  cited ranges resolve to the displayed stored source. Check that a generation
  change cannot silently change an open citation. For Investigate, verify a
  partial run and its explicit stop reason.
- Review the spec, mode sequencing, versioned HTTP contract, serving choice and
  acceptance checks before opening implementation issues or making product
  changes. Follow the project's CI merge gate and operator deployment procedure.

No database migration is anticipated for the frontend. Run records in the first
slice are response records rendered by the client. Durable conversation
storage and resumable runs require separate product decisions.
