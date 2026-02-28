## DOCS\architecture\repo_graph_structure_expanded_detail.md
# Repo Graph: DEFINES + CALLs



Repo (root)
├── **init**.py (MODULE)
│   defines: [HeadlessIngestor, helper_function]
│   parent_id: None
│   ├── HeadlessIngestor (CLASS)
│   │   defines: [**init**, run]
│   │   parent_id: **init**.py
│   │   ├── **init** (METHOD)
│   │   │   defines: []
│   │   │   parent_id: HeadlessIngestor
│   │   │   calls:
│   │   │     - setup_logger → utils.py#Logger.log (confidence 1.0)
│   │   └── run (METHOD)
│   │       defines: []
│   │       parent_id: HeadlessIngestor
│   │       calls:
│   │         - helper_function → **init**.py#helper_function (confidence 1.0)
│   │         - external_api_call → EXTERNAL (confidence 0.0)
│   └── helper_function (FUNCTION)
│       defines: []
│       parent_id: **init**.py
│       calls:
│         - log → utils.py#Logger.log (confidence 1.0)
├── utils.py (MODULE)
│   defines: [parse_input, Logger]
│   parent_id: None
│   ├── parse_input (FUNCTION)
│   │   defines: []
│   │   parent_id: utils.py
│   │   calls:
│   │     - external_library_func → EXTERNAL (confidence 0.0)
│   └── Logger (CLASS)
│       defines: [log, warn]
│       parent_id: utils.py
│       ├── log (METHOD)
│       │   defines: []
│       │   parent_id: Logger
│       └── warn (METHOD)
│           defines: []
│           parent_id: Logger
│           calls:
│             - log → utils.py#Logger.log (confidence 1.0)
└── services/
├── ingestion.py (MODULE)
│   defines: [IngestorService]
│   parent_id: None
│   └── IngestorService (CLASS)
│       defines: [start, stop]
│       parent_id: ingestion.py
│       ├── start (METHOD)
│       │   defines: []
│       │   parent_id: IngestorService
│       │   calls:
│       │     - transform_data → services/transform.py#Transformer.transform (confidence 1.0)
│       └── stop (METHOD)
│           defines: []
│           parent_id: IngestorService
│           calls:
│             - cleanup → EXTERNAL (confidence 0.0)
└── transform.py (MODULE)
defines: [Transformer]
parent_id: None
└── Transformer (CLASS)
defines: [transform]
parent_id: transform.py
└── transform (METHOD)
defines: []
parent_id: Transformer
calls:
- parse_input → utils.py#parse_input (confidence 1.0)
- external_service_call → EXTERNAL (confidence 0.0)



---

### Key Points

1. **CALLs are shown per function/method**, with:
   - `→` pointing to the `resolution` canonical ID.
   - Confidence shown in parentheses.  
2. **EXTERNAL calls** are unresolved, with `confidence 0.0`.  
3. This hierarchy complements the `defines` tree and **clearly shows the relationships** in your repo.  
4. Modules do not have `parent_id` and methods/functions always have `parent_id` pointing to their container.  

---


