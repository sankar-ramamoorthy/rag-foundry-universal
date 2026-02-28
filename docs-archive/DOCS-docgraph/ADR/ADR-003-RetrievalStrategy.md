# ADR-003: Retrieval Strategy for DocumentNodes

**Status:** Proposed  
**Milestone:** MS1  
**Issue:** MS1-IS4-ADR-003  
**Date:** 2026-01-31  

---

## Context

With the introduction of **DocumentNodes** (ADR-001) and **explicit relationships** (ADR-002), we need a **clear strategy for how queries will select and assemble context**.  

Currently:

- Retrieval is **chunk-first**, flat, and purely embedding-based.  
- Prompts can include **irrelevant or redundant chunks**, causing token sprawl.  
- Orchestrator cannot explain why a piece of content was included.

**Problem:**  
Without a retrieval plan:

1. Context will remain **unpredictable**.  
2. Larger context windows will not solve reasoning errors; they only hide them.  
3. Debugging and testability remain difficult.

---

## Decision

Introduce a **structured, bounded retrieval strategy** layered over DocumentNodes:

### Retrieval Steps

1. **Query embedding**  
   - Embed the user query into the same vector space as **document summaries**.

2. **Candidate DocumentNodes**  
   - Retrieve **top N documents** by similarity of their summary embeddings (e.g., N=5–10).

3. **Dominant Scope Selection**  
   - Apply simple heuristics to select a **primary document or tight cluster**:  
     - Same ingestion_id  
     - Same doc_type  
     - Highest cluster similarity  

4. **Relationship Expansion (bounded)**  
   - Expand **1 hop along allowed relationship types** (from ADR-002).  
   - Cap total documents included (e.g., 5–6).  
   - No recursion, no loops, no agent reasoning.

5. **Supporting Chunks**  
   - For the selected documents, retrieve:  
     - Summary  
     - Headings / section titles  
     - Relevant chunk embeddings (for evidence layer)  

6. **Assemble Prompt Context**  
   - Document summaries form the **conceptual layer**.  
   - Selected chunks form the **evidence layer**.  
   - Token usage becomes **predictable and auditable**.

---

## Consequences

**Pros:**

- Deterministic, auditable context assembly.  
- Fewer irrelevant chunks; token budget is predictable.  
- Enables **future GraphRAG-style retrieval** without changing agent logic.  
- Retrieval can be debugged and traced by **document_id**.

**Cons / Trade-offs:**

- Initial implementation requires **orchestrator changes** to handle primary document selection.  
- Boundaries may need tuning (top N, 1-hop expansion).  

---

## Next Steps

1. Document the **retrieval plan in code / comments** for Milestone 2.  
2. Keep the existing LLM call behavior unchanged for now.  
3. Update orchestrator when implementing MS2-IS2 / MS2-IS3.  

---

## References

- ADR-001: DocumentNode  
- ADR-002: Document Relationships  
- GraphRAG retrieval design notes
