# ADR-034: Repository Ingestion Input Strategy

## Status
Proposed / Accepted

## Context
Ingestion must support developer workflows where repositories may exist locally or remotely. Users may want to ingest both cloned repos and Git URLs.

## Decision
- Accept **both Git URLs and local paths** for ingestion.  
- Logic:
  1. If local path exists, use it directly.  
  2. Else, clone the repository from the Git URL to a temporary directory.  
- After processing, optionally clean up cloned repositories.
- The ingestion request will store `repo_id` for tracking.

## Alternatives Considered
1. Accept Git URLs only  
   - Pros: Simple  
   - Cons: Cannot ingest pre-existing local repos
2. Accept local path only  
   - Pros: Simple, no network cloning  
   - Cons: Cannot ingest remote repositories

## Consequences
- Flexible ingestion workflow  
- Requires background worker to handle cloning and ingestion asynchronously
