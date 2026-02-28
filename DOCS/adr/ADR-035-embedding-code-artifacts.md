# ADR-035: Embedding Code Artifacts

## Status
Proposed / Accepted

## Context
To support structured RAG queries, code artifacts need vector embeddings for retrieval.

## Decision
- Use the existing `IngestionPipeline` to generate embeddings for code artifacts.  
- Artifacts will be chunked as needed (function, class, module level).  
- Each chunk will be stored in `vectors` table linked to `document_nodes.document_id`.  
- Embedding provider configurable via `EMBEDDING_PROVIDER`.  
- Reuse existing pipeline where possible to maintain consistency with document ingestion.

## Alternatives Considered
1. Do not embed code artifacts  
   - Pros: Simpler  
   - Cons: Retrieval limited, cannot use vector-based RAG
2. Custom embedding pipeline  
   - Pros: Highly tailored  
   - Cons: Duplicates existing functionality, higher maintenance

## Consequences
- Supports vector-based code retrieval and summarization  
- Integrates with existing vector store (`HttpVectorStore`) and embeddings service
