erDiagram
    INGESTION_REQUESTS ||--o{ DOCUMENT_NODE : produces
    DOCUMENT_NODE ||--o{ DOCUMENT_RELATION : has
    DOCUMENT_NODE ||--o{ VECTORS : contains

    INGESTION_REQUESTS {
        uuid ingestion_id PK
        string source_type
        json ingestion_metadata
        string status
        timestamp created_at
        timestamp started_at
        timestamp finished_at
    }

    DOCUMENT_NODE {
        uuid document_id PK
        string title
        text summary
        vector summary_embedding
        string doc_type
        json source_metadata
        uuid ingestion_id FK
    }

    DOCUMENT_RELATION {
        uuid id PK
        uuid from_document_id FK
        uuid to_document_id FK
        string relation_type
    }

    VECTORS {
        int id PK
        vector vector
        text chunk_id
        int chunk_index
        string chunk_strategy
        text chunk_text
        json source_metadata
        uuid ingestion_id FK
        text provider
        uuid document_id FK
    }
