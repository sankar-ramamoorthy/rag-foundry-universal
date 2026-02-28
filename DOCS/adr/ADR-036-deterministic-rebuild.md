# ADR-036: Deterministic Rebuild Logic

## Status
Proposed / Accepted

## Context
Rebuilding a repository graph must be deterministic to avoid duplicate nodes, conflicting canonical IDs, and inconsistent embeddings.

## Decision
- Use canonical IDs from `identity.py` for all artifact nodes.  
- On rebuild:
  - Existing nodes with the same `repo_id` + `canonical_id` are **updated** instead of duplicated.  
  - Optional: Track file hash or modification timestamp to detect changes.  
- Relationships (`document_relationships`) are rebuilt based on canonical IDs.  
- Ensures idempotent ingestion and vector updates.

## Alternatives Considered
1. Rebuild blindly without checking existing nodes  
   - Pros: Simple  
   - Cons: Duplicates, inconsistent vector chunks
2. Use content hashes only  
   - Pros: Detects actual changes  
   - Cons: Adds complexity, canonical ID provides natural determinism

## Consequences
- Safe multi-pass ingestion  
- Idempotent database updates  
- Reliable link between artifacts, relationships, and embeddings
