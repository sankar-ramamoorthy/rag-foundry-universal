## DOCS/architecture/ADR-032-layered-resolution-example.md

---

# ADR-032 — Layered Resolution Example Flow

**Purpose:** Illustrate how a CALL artifact moves through extraction, symbol tables, resolution, and into the semantic repo graph.

---

## Example Scenario

We have the following Python snippet in `src/core/extractors/python_extractor.py`:

```python
class PythonASTExtractor(ast.NodeVisitor):
    def extract(self, source_code):
        tree = ast.parse(source_code)
        annotate_parents(tree)
        return tree
```

We want to track the call:

```python
ast.parse(source_code)
```

through the **layered resolution model**.

---

## Step 1 — Extraction (Layer 1)

The extractor emits artifacts:

```
MODULE: src/core/extractors/python_extractor.py
CLASS: PythonASTExtractor
METHOD: PythonASTExtractor.extract
CALL: ast.parse
CALL.parent_id = PythonASTExtractor.extract
```

> Each artifact has a **canonical ID** (ADR-031) and metadata (line numbers, args, etc.).

---

## Step 2 — Symbol Table Construction (Layer 2)

**File-local symbol table** for `python_extractor.py`:

| Name               | Canonical ID                       |
| ------------------ | ---------------------------------- |
| PythonASTExtractor | src/...#PythonASTExtractor         |
| extract            | src/...#PythonASTExtractor.extract |
| annotate_parents   | src/...#annotate_parents           |
| ast                | stdlib module (from import)        |

**Global symbol index**:

| Name               | Canonical ID                       |
| ------------------ | ---------------------------------- |
| PythonASTExtractor | src/...#PythonASTExtractor         |
| extract            | src/...#PythonASTExtractor.extract |
| annotate_parents   | src/...#annotate_parents           |
| ast.parse          | EXTERNAL (stdlib)                  |

---

## Step 3 — Resolution (Layer 3)

For `CALL: ast.parse`:

1. Check enclosing function: `PythonASTExtractor.extract` — no local definition of `ast`.
2. Check file imports: `import ast` → resolves to **stdlib**.
3. Global index lookup: not found → mark **EXTERNAL**.

**Resolved CALL Artifact:**

```python
{
  'artifact_type': 'CALL',
  'id': 'src/...#call:ast.parse',
  'name': 'ast.parse',
  'parent_id': 'src/...#PythonASTExtractor.extract',
  'resolution': 'EXTERNAL'
}
```

---

## Step 4 — Relationship Graph Construction

The semantic repo graph now includes:

```
MODULE src/core/extractors/python_extractor.py
    DEFINES CLASS PythonASTExtractor
CLASS PythonASTExtractor
    DEFINES METHOD extract
METHOD extract
    CALLS ast.parse (EXTERNAL)
```

ASCII Diagram:

```
MODULE ──DEFINES──> CLASS
CLASS  ──DEFINES──> METHOD
METHOD ──CALLS───> EXTERNAL (ast.parse)
```

---

## Step 5 — Notes

* All relationships are **deterministic** using canonical IDs.
* `parent_id` ensures **Function → Function** mapping.
* EXTERNAL calls are clearly marked.
* Same flow applies to user-defined functions, imports, and nested classes once scope expands.

---

**Outcome:** Engineers can trace any call or definition step-by-step, from raw extraction to semantic graph.

---

## Mini Example — Internal Function Call Resolution

Python snippet in `src/core/codebase/repo_graph_builder.py`:

```python
def build_graph(repo_path):
    files = list_repo_files(repo_path)
    return files
```

And in the same file:

```python
def list_repo_files(path):
    # returns list of files
    ...
```

---

### Step 1 — Extraction (Layer 1)

Artifacts emitted:

```
MODULE: src/core/codebase/repo_graph_builder.py
FUNCTION: build_graph
FUNCTION: list_repo_files
CALL: list_repo_files
CALL.parent_id = build_graph
```

---

### Step 2 — Symbol Table (Layer 2)

File-local table:

| Name            | Canonical ID            |
| --------------- | ----------------------- |
| build_graph     | src/...#build_graph     |
| list_repo_files | src/...#list_repo_files |

Global index:

| Name            | Canonical ID            |
| --------------- | ----------------------- |
| build_graph     | src/...#build_graph     |
| list_repo_files | src/...#list_repo_files |

---

### Step 3 — Resolution (Layer 3)

* `CALL: list_repo_files` → found in **file symbol table**.
* Resolution is **internal**:

```python
{
  'artifact_type': 'CALL',
  'id': 'src/...#call:list_repo_files',
  'name': 'list_repo_files',
  'parent_id': 'src/...#build_graph',
  'resolution': 'src/...#list_repo_files'
}
```

---

### Step 4 — Relationship Graph

```
MODULE repo_graph_builder.py
    DEFINES FUNCTION build_graph
    DEFINES FUNCTION list_repo_files
FUNCTION build_graph
    CALLS FUNCTION list_repo_files
```

ASCII Diagram:

```
MODULE ──DEFINES──> build_graph
MODULE ──DEFINES──> list_repo_files
build_graph ──CALLS──> list_repo_files
```

---

✅ Notes:

* Internal calls are resolved to canonical IDs, not strings.
* This demonstrates **deterministic internal resolution** versus the EXTERNAL example.
* Same principles scale across classes, methods, and multiple files.

---

