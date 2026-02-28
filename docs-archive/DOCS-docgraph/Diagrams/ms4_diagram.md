# MS4: Relationship-Aware Retrieval Flow

This diagram illustrates the flow for **relationship-aware retrieval** in Milestone 4 (MS4) and shows key fields in the `RetrievalPlan`.

```mermaid
flowchart TD
    subgraph MS4 [MS4 Retrieval Pipeline]
        A[RetrievalPlan\n• seed_document_ids\n• expanded_document_ids\n• expansion_metadata\n• constraints] --> B[Relationship Expansion Planner]
        B --> C[RAG Orchestrator / Execution Service]
        C --> D[Document Retrieval from DB / Vector Store]
        D --> E[Rank & Score Documents]
        E --> F[LLM / Downstream Consumer]
    end

    classDef data fill:#f9f,stroke:#333,stroke-width:1px;
    classDef logic fill:#bbf,stroke:#333,stroke-width:1px;
    classDef external fill:#bfb,stroke:#333,stroke-width:1px;

    class A data;
    class B logic;
    class C logic;
    class D external;
    class E logic;
    class F external;

    %% Clickable notes (optional)
    click A "DOCS/MS4_Design.md#MS4-IS1-Define-RetrievalPlan-Domain-Model" "Open RetrievalPlan design"
    click B "DOCS/MS4_Design.md#MS4-IS2-Relationship-Expansion-Planner" "Open Expansion Planner design"
    click C "DOCS/MS4_Design.md#MS4-IS3-Orchestrator-Execution" "Open Orchestrator design"
