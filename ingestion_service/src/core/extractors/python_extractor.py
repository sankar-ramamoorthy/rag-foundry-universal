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
- CALL (unresolved)

All artifacts include:
- canonical id
- name
- artifact_type
- metadata
- parent_id (except MODULE)

Hierarchical relationships are explicitly encoded using a scope stack.
"""

import ast
from typing import List, Dict, Optional


class PythonASTExtractor(ast.NodeVisitor):
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        self.module_name = relative_path.replace("/", ".").rstrip(".py")
        self.module_id = relative_path  # canonical module id
        self.artifacts: List[Dict] = []
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
            },
        }

        self.artifacts.append(artifact)

        # Enter function/method scope
        self.scope_stack.append(canonical_id)
        self.generic_visit(node)
        self.scope_stack.pop()

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
        try:
            if isinstance(node.func, ast.Attribute):
                func_name = f"{ast.unparse(node.func.value)}.{node.func.attr}"
            else:
                func_name = ast.unparse(node.func)
        except Exception:
            func_name = "<unknown>"

        self.artifacts.append({
            "artifact_type": "CALL",
            "id": f"{self.relative_path}#call:{func_name}",
            "name": func_name,
            "parent_id": self._current_parent_id(),
            "relative_path": self.relative_path,
            "metadata": {
                "lineno": node.lineno,
                "col_offset": node.col_offset,
            },
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
