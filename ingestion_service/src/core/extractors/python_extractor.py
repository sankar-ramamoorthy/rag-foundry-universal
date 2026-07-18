# ingestion_service\src\core\extractors\python_extractor.py
"""
ingestion_service/src/core/extractors/python_extractor.py

PythonASTExtractor

Extracts code artifacts from Python source files:

- MODULE
- CLASS
- FUNCTION
- METHOD
- IMPORT

All artifacts include:
- canonical id
- name
- artifact_type
- metadata
- parent_id (except MODULE)

Hierarchical relationships are explicitly encoded using a scope stack.

Call sites are NOT artifacts (F-03 / WP-G3): they carry no identity, so they
are collected in `self.call_sites` as evidence records
{name, receiver, parent_id, relative_path, lineno, col_offset} and consumed
by RepoGraphBuilder._resolve_calls to produce aggregated CALL edges.
"""

import ast
from typing import List, Dict, Optional


class PythonASTExtractor(ast.NodeVisitor):
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        # F-05: strip the ".py" suffix, not the character set {., p, y} —
        # rstrip(".py") corrupted names like "happy.py" → "ha".
        module_path = (
            relative_path[:-3]
            if relative_path.endswith(".py")
            else relative_path
        )
        self.module_name = module_path.replace("/", ".")
        self.module_id = relative_path  # canonical module id
        self.artifacts: List[Dict] = []
        # F-03: call sites are evidence, not identity-bearing artifacts.
        self.call_sites: List[Dict] = []
        self.scope_stack: List[str] = []  # maintains current lexical scope

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, source_code: str) -> List[Dict]:
        tree = ast.parse(source_code)
        annotate_parents(tree)

        # Emit MODULE artifact
        self.artifacts.append({
            "artifact_type": "MODULE",
            "id": self.module_id,
            "name": self.module_name,
            "relative_path": self.relative_path,
            "metadata": {},
        })

        # Visit tree
        self.visit(tree)
        return self.artifacts

    # ------------------------------------------------------------------
    # Scope Helpers
    # ------------------------------------------------------------------

    def _current_parent_id(self) -> Optional[str]:
        if self.scope_stack:
            return self.scope_stack[-1]
        return self.module_id

    # ------------------------------------------------------------------
    # Visitor methods
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef):
        canonical_id = f"{self.relative_path}#{node.name}"

        artifact = {
            "artifact_type": "CLASS",
            "id": canonical_id,
            "name": node.name,
            "parent_id": self._current_parent_id(),
            "metadata": {
                "lineno": node.lineno,
                "col_offset": node.col_offset,
                "bases": [ast.unparse(base) for base in node.bases] if node.bases else [],
            },
        }

        self.artifacts.append(artifact)

        # Enter class scope
        self.scope_stack.append(canonical_id)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        parent_class = self._get_parent_class(node)

        if parent_class:
            canonical_id = f"{self.relative_path}#{parent_class}.{node.name}"
            artifact_type = "METHOD"
        else:
            canonical_id = f"{self.relative_path}#{node.name}"
            artifact_type = "FUNCTION"

        artifact = {
            "artifact_type": artifact_type,
            "id": canonical_id,
            "name": node.name,
            "parent_id": self._current_parent_id(),
            "metadata": {
                "lineno": node.lineno,
                "col_offset": node.col_offset,
                "args": [arg.arg for arg in node.args.args],
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            },
        }

        self.artifacts.append(artifact)

        # Enter function/method scope
        self.scope_stack.append(canonical_id)
        self.generic_visit(node)
        self.scope_stack.pop()

    # F-01: async defs must produce FUNCTION/METHOD artifacts too —
    # without this alias every `async def` was invisible to the graph
    # and calls inside it were mis-attributed to the enclosing scope.
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.artifacts.append({
                "artifact_type": "IMPORT",
                "id": f"{self.relative_path}#import:{alias.name}",
                "name": alias.name,
                "parent_id": self._current_parent_id(),
                "relative_path": self.relative_path,
                "metadata": {
                    "asname": alias.asname,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                },
            })

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.artifacts.append({
                "artifact_type": "IMPORT",
                "id": f"{self.relative_path}#import:{module}.{alias.name}",
                "name": alias.name,
                "parent_id": self._current_parent_id(),
                "relative_path": self.relative_path,
                "metadata": {
                    "module": module,
                    "asname": alias.asname,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                },
            })

    def visit_Call(self, node: ast.Call):
        # F-03: record the call site with the receiver split from the
        # callee name (`self.add()` → name="add", receiver="self") instead
        # of a fused string, so resolution can use scope/import context.
        try:
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
                receiver = ast.unparse(node.func.value)
            elif isinstance(node.func, ast.Name):
                name = node.func.id
                receiver = None
            else:
                name = ast.unparse(node.func)
                receiver = None
        except Exception:
            name = "<unknown>"
            receiver = None

        self.call_sites.append({
            "name": name,
            "receiver": receiver,
            "parent_id": self._current_parent_id(),
            "relative_path": self.relative_path,
            "lineno": node.lineno,
            "col_offset": node.col_offset,
        })

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_parent_class(self, node: ast.AST) -> Optional[str]:
        current = getattr(node, "parent", None)
        while current:
            if isinstance(current, ast.ClassDef):
                return current.name
            current = getattr(current, "parent", None)
        return None


# ----------------------------------------------------------------------
# Utility: annotate parent links in AST
# ----------------------------------------------------------------------

def annotate_parents(tree: ast.AST):
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            setattr(child, "parent", node)
