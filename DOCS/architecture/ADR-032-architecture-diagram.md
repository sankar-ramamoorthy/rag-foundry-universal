                    ┌─────────────────────────┐
                    │   Layer 1: Extraction   │
                    │   (PythonASTExtractor)  │
                    └─────────────┬──────────┘
                                  │ emits
                                  ▼
                    ┌─────────────────────────┐
                    │  Artifacts (Unified)    │
                    │ ┌───────────────┐       │
                    │ │ MODULE        │       │
                    │ │ CLASS         │       │
                    │ │ FUNCTION/METHOD │     │
                    │ │ IMPORT        │       │
                    │ │ CALL          │       │
                    │ └───────────────┘       │
                    └─────────────┬──────────┘
                                  │ input
                                  ▼
                    ┌─────────────────────────┐
                    │ Layer 2: Symbol Tables  │
                    │ (File-local & Global)   │
                    └─────────────┬──────────┘
                                  │ used for
                                  ▼
                    ┌─────────────────────────┐
                    │ Layer 3: Resolution     │
                    │  - CALL → Function      │
                    │  - IMPORT → Symbol      │
                    │  - MODULE/CLASS/FUNC    │
                    │    DEFINES relationships│
                    │  - EXTERNAL markers     │
                    └─────────────┬──────────┘
                                  │ produces
                                  ▼
                    ┌─────────────────────────┐
                    │ Repo Graph (Semantic)   │
                    │                         │
                    │ MODULE ──DEFINES──> CLASS
                    │ MODULE ──DEFINES──> FUNC
                    │ CLASS  ──DEFINES──> METHOD
                    │ FUNC   ──CALLS───> FUNC/EXTERNAL
                    │ ...                     │
                    └─────────────────────────┘
