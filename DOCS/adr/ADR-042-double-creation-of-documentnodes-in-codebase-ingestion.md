## DOCS\adr\ADR-042-double-creation-of-documentnodes-in-codebase-ingestion.md

A detailed **ADR** for the **double-creation bug** in the codebase ingestion pipeline. This ADR documents the issue, provides proposed solutions, reasons for rejecting some of them, and outlines future considerations for handling similar issues.

---

## **ADR-042: Codebase Ingestion - Double Creation of DocumentNodes**

### **Status**

Accepted

### **Date**

2026-02-16

### **Decision Owner**

Code Intelligence Architecture

---

## **1. Context**

The **codebase ingestion pipeline** is responsible for ingesting and processing code artifacts, embedding their text, and persisting the results. However, a **critical bug** has been identified where **DocumentNodes are being created twice for each code entity** during the ingestion process. This leads to **data duplication** and **incorrect vector-store associations**.

### **Problem Overview**

In the current codebase ingestion flow (`codebase_ingest.py`), the following steps are occurring:

1. **First Creation**: `CodebaseGraphPersistence.upsert_nodes()` creates a `DocumentNode` with the canonical ID based on the code entity's path and symbol. This is the correct and intended creation of the `DocumentNode`.

2. **Second Creation**: The `IngestionPipeline.run()` method is invoked for each node, which internally calls `create_document_node()`, resulting in the creation of a **second `DocumentNode`** with a new UUID and source set to `"file_document_{ingestion_id}"`. This duplicate node is unnecessary.

As a result, **duplicate `DocumentNode` entries** are being inserted into the database, leading to confusion and inconsistencies, particularly in how vector embeddings are linked to the `DocumentNode`.

---

## **2. Architectural Options Considered**

### **Option A — Skip DocumentNode Creation in the Pipeline for Code Entities (Recommended)**

#### **Approach**

* Skip the creation of a `DocumentNode` in the `IngestionPipeline.run()` method if the code entity has already been persisted in the `CodebaseGraphPersistence.upsert_nodes()` step.
* This can be achieved by checking if the node already exists, or by using the **canonical ID** from the graph node as the `document_id` in the pipeline.

#### **Flow**

```python
# In codebase_ingest.py, before pipeline.run():
if text.strip():
    # Skip pipeline DocumentNode creation for code (already done)
    chunks = pipeline._chunk(text, "code", provider)
    embeddings = pipeline._embed(chunks)
    
    # Use canonical_id from graph node as document_id
    pipeline._persist(chunks, embeddings, str(ingestion_id), node["canonical_id"])
```

#### **Why Chosen**

* **Simplicity**: This solution directly addresses the issue by avoiding duplicate node creation.
* **Efficiency**: Prevents unnecessary work in the pipeline and eliminates data duplication.
* **Alignment with Current Architecture**: The nodes are already created and stored by `upsert_nodes()`, so re-creating them in the pipeline is redundant.

---

### **Option B — Modify CodebaseGraphPersistence to Handle Vectors**

#### **Approach**

* Modify `CodebaseGraphPersistence.upsert_nodes()` to handle both node creation **and vector persistence** in one operation. This would eliminate the need for the second step in the pipeline to embed vectors and persist them.

#### **Flow**

```python
# Extend CodebaseGraphPersistence to also persist vectors
persistence.upsert_nodes_and_vectors(repo_id, nodes)  # One call does both
```

#### **Why Rejected (For Now)**

* **Complexity**: This introduces additional complexity into the `upsert_nodes()` method, which would then need to handle vector embedding as well.
* **Separation of Concerns**: The embedding logic is distinct from node persistence, and combining them might cause issues in the future, particularly if the embedding strategy changes.
* **Future Flexibility**: The separation of responsibilities (node creation vs. vector embedding) keeps the architecture flexible for future changes in the pipeline.

---

### **Option C — Pass Existing Document ID to the Pipeline**

#### **Approach**

* After the `CodebaseGraphPersistence.upsert_nodes()` operation, pass the **existing `document_id`** (the canonical ID) to the pipeline. This would prevent the pipeline from creating a new `DocumentNode` during the ingestion process.

#### **Flow**

```python
# After upsert_nodes(), pass canonical_id to pipeline
pipeline.run_with_existing_node(
    text=text, 
    ingestion_id=str(ingestion_id), 
    source_type="code",
    document_id=node["canonical_id"]  # Skip create_document_node()
)
```

#### **Why Rejected (For Now)**

* **Increased Complexity**: This option introduces more complexity by requiring changes to how the pipeline handles existing nodes and interacts with the `document_id`.
* **Overhead**: It’s essentially solving the same problem as Option A but in a more indirect manner. The `document_id` still needs to be tracked, and the issue of double creation remains in the pipeline flow.

---

## **3. Decision**

After evaluating the options, **Option A (Skip DocumentNode Creation in the Pipeline for Code)** is selected. This approach is **simple**, **direct**, and **efficient**, solving the immediate issue without adding unnecessary complexity to the architecture.

### **Deferred:**

* **Option B** (Modify CodebaseGraphPersistence to handle vectors) and **Option C** (Pass existing `document_id` to the pipeline) are deferred for the following reasons:

  * **Option B** introduces additional complexity in the persistence layer and might violate the separation of concerns between node persistence and vector handling.
  * **Option C** is an indirect solution that introduces unnecessary complexity without providing significant benefits over Option A.

Both of these options may be reconsidered in the future if **advanced handling of vectors** or **fine-tuned control over node creation** becomes necessary.

---

## **4. Rationale**

### **4.1 Current System Maturity**

The ingestion system is in the stabilization phase, and introducing unnecessary complexity would hinder progress. The goal is to ensure that the system runs **reliably** and **efficiently** without introducing over-engineering.

### **4.2 Immediate Objective**

The immediate objective is to fix the **double creation of `DocumentNode`** entries without changing the overall structure of the system. **Option A** allows us to achieve this while maintaining a clean and simple architecture.

### **4.3 Risk Management**

By avoiding more complex solutions, we mitigate the risk of introducing bugs or **over-engineering**. The simple fix is optimal for **Phase 1**, and any additional changes can be implemented once the system is stable.

---

## **5. Implementation Requirements**

### **5.1 Code Changes**

In `codebase_ingest.py`, the following changes need to be made:

1. **Skip the creation of `DocumentNode`** inside the pipeline if it has already been created by `upsert_nodes()`.
2. Use the **canonical ID** from the graph node as the `document_id` for embedding and vector persistence.

### **5.2 Testing**

* Ensure that no duplicate `DocumentNode` entries are created in the database.
* Verify that the embeddings are correctly linked to the original nodes, not the duplicates.

---

## **6. Future Conditions for Reevaluating Other Options**

### **When Option B or Option C Could Be Reconsidered**

* If **vector handling** becomes a more integral part of the codebase graph persistence process.
* If **advanced vector control** or **fine-grained semantic search** requires more direct manipulation of vectors and nodes during the ingestion process.

---

## **7. Guardrails**

To preserve flexibility and avoid premature complexity:

* **DocumentNode creation** will remain separated from the embedding pipeline for Phase 1.
* **Text storage and embedding** logic will remain modular and independent of the graph persistence layer.
* Any future changes to the node creation flow will be carefully considered to ensure they do not introduce unnecessary coupling or complexity.

---

## **8. Long-Term Target Architecture**

```
API Layer
    ↓
Application Services
    ↓
Code Artifact Graph (Domain Layer)
    ↓
[Future] Chunk Assembly Layer
    ↓
Embedding Pipeline
    ↓
Vector Store
```

---

## **9. Consequences**

### **Positive**

* **Faster resolution** of the immediate bug with minimal disruption to the architecture.
* **Simple solution** that avoids over-engineering the system.
* **No data duplication** and proper linking of vectors to `DocumentNode`.

### **Negative**

* **Limited immediate flexibility** for more granular vector control and handling (deferred for future phases).

---

## **10. Strategic Position**

The phased approach allows for:

* **Phase 1**: Implement a simple solution that eliminates the double creation of `DocumentNode` entries.
* **Phase 2**: Evaluate vector management and potential improvements based on real-world usage.
* **Phase 3**: Consider more advanced solutions if needed, such as **embedding and node management optimizations**.

This ensures that the system remains **stable** while also providing room for **future enhancements**.

---

### **Final Positioning**

This ADR formalizes the decision to fix the **double creation bug** in the codebase ingestion pipeline by **skipping node creation** in the pipeline for code entities that have already been persisted. More complex solutions will be deferred until future needs arise.

---
currrent state

## Side-by-Side Ingestion Flow Comparison

```
DOCUMENTS (ingest.py)                    | CODEBASE (codebase_ingest.py)  
──────────────────────────────────────────┼─────────────────────────────────
POST /ingest/file                        | POST /ingest-repo               
file_bytes + metadata                    | git_url OR local_path           
source_type="file"                       | source_type="repo"             
                                         |                                 
┌─────────────────┐                      | ┌─────────────────┐            
│ 1 file          │                      | │ 1 repo          │            
│                 │                      | │                 │            
│ • PDF           │                      | │ • clone git     │            
│ • Text/Image    │                      │ │ • local path    │            
└─────────┬───────┘                      └──────┬──────────┘            
          │                                   │                        
          ▼                                   ▼                        
┌─────────────────┐                      ┌─────────────────┐            
│ Extract text    │                      │ RepoGraphBuilder│            
│                 │                      │ .build()        │            
│ PDF →           │                      └──────┬──────────┘            
│ • PDFExtractor  │                              │                      
│ • GraphBuilder  │                              ▼                      
│ • ChunkAssembler│                      ┌─────────────────┐            
│                 │                      │ nodes =         │            
│ TXT/IMG →       │                      │ all_entities()  │            
│ • OCR/TXT decode│                      └──────┬──────────┘            
└─────────┬───────┘                              │                      
          │                                       ▼                      
          ▼                               ┌─────────────────┐            
┌─────────────────┐                      │ CodebaseGraph   │            
│ 1x chunks/text  │◄───────┐              │ Persistence     │            
└─────────┬───────┘       │              │ .upsert_nodes() │            
          ▼               │              │                 │            
┌─────────────────┐       │              │ • canonical_id  │            
│ IngestionPipeline│◄──────┼──────────────┤ • repo_id       │            
│                 │       │              │ • relative_path │            
│ • run(text=)    │       │              │ • text/symbol   │            
│ • run(chunks=)  │       │              └──────┬──────────┘            
└───────┬────────┘       │                          │                    
         │               │                          ▼                    
         ▼               │                 ┌─────────────────┐            
┌─────────────────┐      │                 │ Pipeline.run()  │            
│ DocumentNode    │◄──────┼──────────────► │ PER NODE        │            
│ (via CRUD)      │      │                 │ text=node.text  │            
│                 │      │                 └──────┬──────────┘            
│ • 1 per ingest  │      │                            │                    
│ • source=       │      │                            ▼                    
│   "file_doc_*"  │      │                   ┌─────────────────┐          
└───────┬────────┘      │                   │ DocumentNode    │          
         │               │                   │ (via CRUD)      │          
         ▼               │                   │                 │          
┌─────────────────┐      │                   │ • 1 per code    │          
│ chunk → embed   │◄──────┼──────────────► │   entity        │          
│ → vector_store  │      │                   │ • doc_type="code"│         
└─────────────────┘      │                   └──────┬──────────┘          
         │                │                            │                    
         ▼                │                            ▼                    
┌─────────────────┐       │                   ┌─────────────────┐          
│ mark_completed  │       │                   │ chunk → embed   │          
│ POST summarize  │       │                   │ → vector_store  │          
└─────────────────┘       │                   └──────┬──────────┘          
                           │                            │                    
                           └────────────────────────────┘                    
                                        │                                  
                                        ▼                                  
                               ┌─────────────────┐                         
                               │ mark_completed │                         
                               │ (no summarize) │                         
                               └─────────────────┘                         
```

## Key Flow Differences

```
│ DOCUMENTS                                    CODEBASE                          │
├──────────────────────────────────────────────┼────────────────────────────────┤
│ 1 DocumentNode per file                      │ N DocumentNodes per repo        │
│                                              │ (one per code entity)           │
├──────────────────────────────────────────────┼────────────────────────────────┤
│ source="file_document_{ingestion_id}"        │ canonical_id=path[#symbol]      │
│                                              │ repo_id = build_repo_id(repo_url)       │
├──────────────────────────────────────────────┼────────────────────────────────┤
│ run() OR run_with_chunks()                   │ run() per code node             │
│ (1 pipeline call)                            │ (N pipeline calls)              │
├──────────────────────────────────────────────┼────────────────────────────────┤
│ PDF graph → chunks only                      │ Repo graph → nodes → DB upsert  │
│ (transient graph)                            │ + relationships (future)        │
├──────────────────────────────────────────────┼────────────────────────────────┤
│ Triggers /v1/summarize/{ingestion_id}        │ No summary trigger yet          │
└──────────────────────────────────────────────┘────────────────────────────────┘
```
**Yes, the codebase flow creates DocumentNodes TWICE per code entity.** This is a **critical bug**.

## The Double-Creation Problem

```
Codebase Flow (codebase_ingest.py):
┌─────────────────────────────────────────────────────────────┐
│ 1. CodebaseGraphPersistence.upsert_nodes(nodes)             │
│    ↓                                                        │
│    Creates/Updates DocumentNode via direct SQLAlchemy       │
│    (repo_id = build_repo_id(repo_url), canonical_id=path#symbol)    │  ← FIRST DocumentNode
│                                                             │
│ 2. for each node: pipeline.run(text=node["text"])           │
│    ↓                                                        │
│    IngestionPipeline.run():                                 │
│       create_document_node() via CRUD                       │
│       (document_id=uuid4(), source="file_document_*")       │  ← SECOND DocumentNode
└─────────────────────────────────────────────────────────────┘
```

## What happens:

1. **`CodebaseGraphPersistence.upsert_nodes()`** → **DocumentNode #1**
   - `repo_id = build_repo_id(repo_url)`
   - `canonical_id=build_canonical_id(relative_path, symbol_path)`
   - `text=node["text"]`
   - **Purpose**: Code graph persistence with deterministic identity

2. **`pipeline.run()` (called N times)** → **DocumentNode #2** *(duplicate)*
   - `document_id=uuid4()` *(different UUID)*
   - `source=f"file_document_{ingestion_id}"`
   - `doc_type="code"`
   - `repo_id = build_repo_id(repo_url)` *(same namespace)*
   - **Purpose**: Vector store linking (but creates duplicate!)

## Result: Duplicate DocumentNodes per code entity

```
Repo with 100 Python functions → 200 DocumentNodes in DB!
- 100 from CodebaseGraphPersistence (correct, canonical)
- 100 from IngestionPipeline.run() (duplicates, wrong source)
```

## Fix Options

### Option 1: Skip DocumentNode creation in pipeline for code (Recommended)
```python
# In codebase_ingest.py, before pipeline.run():
if text.strip():
    # Skip pipeline DocumentNode creation for code (already done)
    chunks = pipeline._chunk(text, "code", provider)
    embeddings = pipeline._embed(chunks)
    # Use canonical_id from graph node as document_id
    pipeline._persist(chunks, embeddings, str(ingestion_id), node["canonical_id"])
```

### Option 2: Make CodebaseGraphPersistence handle vectors
```python
# Extend CodebaseGraphPersistence to also persist vectors
persistence.upsert_nodes_and_vectors(repo_id, nodes)  # One call does both
```

### Option 3: Pass existing document_id to pipeline
```python
# After upsert_nodes(), pass canonical_id to pipeline
pipeline.run_with_existing_node(
    text=text, 
    ingestion_id=str(ingestion_id), 
    source_type="code",
    document_id=node["canonical_id"]  # Skip create_document_node()
)
```



Here is how the flow diagram would look after implementing the fix (based on **Option A: Skip DocumentNode Creation in the Pipeline for Code**).

#### **Expected Flow Diagram: After Fix**

```
CODEBASE (codebase_ingest.py)  
──────────────────────────────────────────────────────────────
POST /ingest-repo (same as before)
git_url OR local_path             
source_type="repo"             
                                       
          │                                 
          ▼                                 
┌─────────────────┐                       ┌─────────────────┐
│ RepoGraphBuilder│                       │ CodebaseGraph   │
│ .build()        │                       │ Persistence     │
└──────┬──────────┘                       │ .upsert_nodes() │
          │                               └──────┬──────────┘
          ▼                                      │
┌─────────────────┐                              ▼  
│ nodes =         │                       ┌─────────────────┐
│ all_entities()  │                       │ CodebaseGraph   │
└──────┬──────────┘                       │ Persistence     │
          │                              │ → Canonical ID  │
          ▼                              │ → repo_id       │
┌─────────────────┐                       │ → metadata/text │
│ DocumentNode    │                       │ → Relationships │
│ (via upsert)    │                       └─────────────────┘
└──────┬──────────┘                              │ 
          │                                      ▼ 
          ▼                                ┌─────────────────┐
┌─────────────────┐                         │ Embedding Pipeline │
│ skip Document   │──────────────────────►│ Embedding Chunks  │
│ Node creation   │                         │ (No new node creation) │
│ for code (skip) │                         └──────┬──────────┘
└─────────────────┘                              │ 
          │                                      ▼
          ▼                                ┌─────────────────┐
┌─────────────────┐                         │ Vector Store    │
│ Chunks and      │                         │ (Persisted)     │
│ Embeddings      │                         └─────────────────┘
└─────────────────┘  
          │
          ▼
┌─────────────────┐
│ Mark Completed │
│ (POST /summarize)│
└─────────────────┘
```

#### **Explanation of Changes:**

1. **Skip `DocumentNode` creation for code in the pipeline**:

   * The flow now bypasses the creation of a second `DocumentNode` for code artifacts.
   * Instead, after the node is created in `upsert_nodes()`, the **existing node** is used for the embedding process.
2. **Embedding Process**:

   * Chunks of code are passed through the embedding pipeline, which uses the **existing `DocumentNode`**'s canonical ID to persist embeddings and vectors directly.
3. **No New Nodes Created**:

   * This avoids the creation of duplicate `DocumentNodes`, ensuring that each code entity is represented by a **single node** with its corresponding embeddings.
4. **Final Steps**:

   * Once embeddings are stored, the process proceeds to mark the task as completed.

---

