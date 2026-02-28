---

### 1️⃣ **RetrievalPlan is purely declarative / data-only**

* It does **not** execute queries, traverse relationships, or score results.
* Its purpose is to be an **inspectable plan**: what to retrieve, from where, and under what constraints.
* It lives entirely in the **ingestion_service domain** (or potentially a shared `core/retrieval` package).

---

### 2️⃣ **RAG Orchestrator (or similar orchestrating service)**

* This is the component that actually **executes retrieval**.

* Responsibilities:

  1. Accept a `RetrievalPlan` instance.
  2. Pull seed documents from the DB or vector store.
  3. Expand the plan using relationships and constraints if needed.
  4. Score or rank results.
  5. Return final documents (e.g., to a LLM or downstream pipeline).

* Advantages of this split:

  * **Separation of concerns**: `RetrievalPlan` = intent; orchestrator = execution.
  * **Testability**: you can unit-test plans in isolation without touching DB or embedding providers.
  * **Extensibility**: later, the orchestrator can implement different expansion strategies without touching the data model.

---

### 3️⃣ **Where this fits in MS4**

* MS4-IS1 (RetrievalPlan) ✅: purely data object.
* MS4-IS2 (Relationship Expansion Planner) ✅: consumes `RetrievalPlan`, updates `expanded_document_ids` and `expansion_metadata` according to rules.
* MS4-IS3 (Orchestrator / Execution) ⬅ this is where the RAG orchestrator comes in.

  * It will pull documents, expand via plan, and eventually feed LLM or other consumers.

---

The **orchestrator service is the actual executor**, while `RetrievalPlan` is just the plan handed to it.

🧠 Design notes (important for MS4 → MS5)

These are intentional and worth keeping:

1️⃣ Sets, not lists

Enforces uniqueness naturally
Makes expansion idempotent
Prevents accidental duplicates during planning

2️⃣ Separate ExpansionMetadata

Avoids dict-of-dicts entropy
Makes future typing + validation trivial
Clean boundary for richer explanations later

3️⃣ Constraints as a first-class object

Future-proof:
depth > 1
bidirectional traversal
relation filters
Keeps RetrievalPlan stable as behavior evolves

🔒 Behavioral guarantees (MS4 contract)
At this point in the system:
RetrievalPlan can describe behavior that does not yet exist.