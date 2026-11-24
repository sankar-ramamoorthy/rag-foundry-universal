# Foundry product frontend first release

**Status:** Proposed for owner review, November 23, 2026

**Tracking:** Phase 6, [#402](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/402)
and [#404](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/404)

See [ADR-057](../../DOCS/adr/ADR-057-react-typescript-product-frontend.md) for
the accepted architecture and the [API assessment](../../DOCS/notes/20261123-frontend-api-assessment.md)
for contract readiness.

## User journeys and acceptance

| Journey | Observable acceptance criteria |
| --- | --- |
| Orient | A user can select an indexed repository and see readiness, the indexed generation and the commit when known. An unavailable generation prevents questions and source reads. An overview displays its reported limits. |
| Locate | A path, basename or glob returns matching files. Ambiguous matches remain individually selectable and pagination preserves the original scope. A supported Python file can display verified definitions and their spans. Unsupported definition coverage is visible. |
| Explain | Ask is the proposed default and uses standard Foundry RAG. A submitted question produces an answer or a recoverable error. Show indexed generation and returned evidence with every answer. |
| Verify | Selecting evidence with a valid range opens the same revision and highlights the returned lines alongside the answer. Evidence without a usable range remains visible with a reason. Consulted passages carry that label. Explicit support for a specific claim is shown only when the backend supplies that association. |
| Investigate | Proposed companion Explain mode. It shares repository selection and the viewer, with a distinct run record and explicit user selection. A completed or partial run shows findings, admitted evidence, open gaps and the termination reason. An unavailable service displays its status and leaves Ask available. |

Ask and the shared viewer are the first deliverable. Investigate is a second
increment within this proposal, gated on the peri-agent contract and product
review. The owner can review both without committing to launching them together.
The initial UI uses one repository and generation per view and non-streaming
answers. Mode, repository and generation changes preserve the identity of prior
results and prevent late responses from populating the current view. A stale
generation offers explicit refresh and rerun. The UI never opens an old citation
against a newer generation.

The first release focuses on reading already indexed code. Repository mutation,
graph explorer, semantic symbol lookup, document workflows, streaming and the
deferred #208 enterprise features are outside its scope.

## Product contract

Publish a versioned OpenAPI artifact covering the browser-facing routes and
error responses. Each question request includes repository and expected
generation. Each run result identifies its mode, run ID and scoped evidence.
Repository ID and generation are required for highlightable source. Commit is
nullable. Ranges are inclusive and one-based. A source request returns the
effective range, source text and digest. Missing ranges and coverage limits are
explicit. Ask and Investigate may have distinct result types while sharing the
source reference and evidence scope types.

The backend rejects stale generation and out-of-scope evidence before returning
results. The browser renders code as text, sanitizes answer Markdown, and treats
artifact paths and citation identifiers as data. Integration with the peri-agent
uses the Foundry product API and a published service contract.
