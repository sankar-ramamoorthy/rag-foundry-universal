# Ordinary RAG Custom evidence capacity

[Phase 6 implementation issue #394](https://github.com/sankar-ramamoorthy/rag-foundry-universal/issues/394)

## Request and delivery contract

Custom requests specify a positive maximum in UTF-8 evidence bytes. The
orchestrator ranks and renders whole passages once and applies the deployment
evidence ceiling. The LLM service handles capacity for each eligible Ollama
candidate, including fallback. Inputs include the Foundry instructions,
question, passage labels and separators, model template and output reserve.
Auto continues to request 4,096 bytes.

| Acceptance case | Observable result |
| --- | --- |
| Qwen3:4b, Custom 8,192, sufficient active window, no manual profile | Ordinary RAG returns an answer. Captured passages fit the verified prompt and match the displayed sources. |
| Smaller active window or fallback | Recompute fit from the original ordered passages. Report the serving model, actual delivered bytes, final passage manifest and omitted chunk IDs. |
| Cold model or changed runner | Verify its current allocation before relying on it. A cached model identity alone cannot authorize generation. |
| Unverifiable fit | Skip the candidate or fail explicitly. The UI explains what the user can try. |
| Missing or mismatched evidence receipt | The orchestrator returns an error before publishing the answer or citations. |

The first release covers ordinary repository RAG. Repository Overview has
additional policy evidence and keeps its existing selection path.
