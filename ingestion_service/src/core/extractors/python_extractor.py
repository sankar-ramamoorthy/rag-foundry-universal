# ingestion_service\src\core\extractors\python_extractor.py
"""
ingestion_service/src/core/extractors/python_extractor.py

PythonASTExtractor (WP-L1: adapted to emit the language-agnostic IR —
DOCS/audit/03-Multi-Language-Graph-Plan.md — instead of building graph
entities/edges itself; identity assignment and all resolution now live
once in GraphAssembler).

Extracts code symbols from Python source files:

- MODULE
- CLASS
- FUNCTION
- METHOD
- IMPORT

Call sites are NOT symbols (F-03 / WP-G3): they carry no identity, so
they are emitted as CallSite IR records and consumed by
GraphAssembler._resolve_calls to produce aggregated CALL edges.

Hierarchical relationships are expressed via `symbol_path`/
`parent_symbol_path` on each SymbolRecord/ImportRecord/CallSite —
maintained here with a scope stack of symbol_path strings (mirroring
the previous canonical-id scope stack one level down, since identity
assignment is no longer this class's job).
"""

import ast
import re
from typing import List, Optional

from src.core.codebase.ir import CallSite, ExtractionResult, ImportRecord, SymbolRecord

DEFAULT_DOC_TYPE = "python source"

# F-07: single-parse text extraction. These two helpers replicate
# ast.get_source_segment(padded=False) over pre-split lines, so each
# file's source is split once. Behavioral contract (verified by tests
# against ast.get_source_segment): lines split on \n / \r / \r\n only
# — NOT on form feed or other unicode breaks — and
# col_offset/end_col_offset are byte offsets into the UTF-8 encoded
# line.
_LINE_SPLIT = re.compile(r"[^\r\n]*(?:\r\n|[\r\n])?")


def _splitlines_no_ff(source: str) -> list[str]:
    lines = _LINE_SPLIT.findall(source)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _source_segment(lines: list[str], node) -> Optional[str]:
    try:
        if node.end_lineno is None or node.end_col_offset is None:
            return None
        lineno = node.lineno - 1
        end_lineno = node.end_lineno - 1
        col_offset = node.col_offset
        end_col_offset = node.end_col_offset
    except AttributeError:
        return None

    if end_lineno == lineno:
        return lines[lineno].encode()[col_offset:end_col_offset].decode()

    first = lines[lineno].encode()[col_offset:].decode()
    last = lines[end_lineno].encode()[:end_col_offset].decode()
    return "".join([first, *lines[lineno + 1:end_lineno], last])


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
        self.symbols: List[SymbolRecord] = []
        self.imports: List[ImportRecord] = []
        # F-03: call sites are evidence, not identity-bearing symbols.
        self.call_sites: List[CallSite] = []
        self.scope_stack: List[str] = []  # symbol_path strings, innermost last
        self._source_lines: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, source_code: str) -> ExtractionResult:
        tree = ast.parse(source_code)
        annotate_parents(tree)
        self._source_lines = _splitlines_no_ff(source_code)

        # Emit MODULE symbol
        self.symbols.append(SymbolRecord(
            kind="MODULE",
            name=self.module_name,
            symbol_path=None,
            parent_symbol_path=None,
            span=None,
            text=source_code,
            metadata={"doc_type": DEFAULT_DOC_TYPE},
        ))

        self.visit(tree)
        return ExtractionResult(
            symbols=self.symbols,
            imports=self.imports,
            calls=self.call_sites,
        )

    # ------------------------------------------------------------------
    # Scope Helpers
    # ------------------------------------------------------------------

    def _current_symbol_path(self) -> Optional[str]:
        return self.scope_stack[-1] if self.scope_stack else None

    # ------------------------------------------------------------------
    # Visitor methods
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef):
        parent_symbol_path = self._current_symbol_path()
        symbol_path = (
            f"{parent_symbol_path}.{node.name}" if parent_symbol_path
            else node.name
        )

        self.symbols.append(SymbolRecord(
            kind="CLASS",
            name=node.name,
            symbol_path=symbol_path,
            parent_symbol_path=parent_symbol_path,
            span=(node.lineno, getattr(node, "end_lineno", node.lineno)),
            text=_source_segment(self._source_lines, node) or "",
            metadata={
                "lineno": node.lineno,
                "col_offset": node.col_offset,
                "bases": [ast.unparse(base) for base in node.bases]
                if node.bases
                else [],
                "doc_type": DEFAULT_DOC_TYPE,
            },
        ))

        self.scope_stack.append(symbol_path)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        parent_class = self._get_parent_class(node)
        parent_symbol_path = self._current_symbol_path()

        if parent_class:
            symbol_path = f"{parent_class}.{node.name}"
            kind = "METHOD"
        else:
            symbol_path = node.name
            kind = "FUNCTION"

        self.symbols.append(SymbolRecord(
            kind=kind,
            name=node.name,
            symbol_path=symbol_path,
            parent_symbol_path=parent_symbol_path,
            span=(node.lineno, getattr(node, "end_lineno", node.lineno)),
            text=_source_segment(self._source_lines, node) or "",
            metadata={
                "lineno": node.lineno,
                "col_offset": node.col_offset,
                "args": [arg.arg for arg in node.args.args],
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "doc_type": DEFAULT_DOC_TYPE,
            },
        ))

        self.scope_stack.append(symbol_path)
        self.generic_visit(node)
        self.scope_stack.pop()

    # F-01: async defs must produce FUNCTION/METHOD symbols too —
    # without this alias every `async def` was invisible to the graph
    # and calls inside it were mis-attributed to the enclosing scope.
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import):
        parent_symbol_path = self._current_symbol_path()
        for alias in node.names:
            self.imports.append(ImportRecord(
                raw_module=alias.name,
                imported_name=None,
                alias=alias.asname,
                parent_symbol_path=parent_symbol_path,
                span=(node.lineno, node.lineno),
                metadata={
                    "col_offset": node.col_offset,
                    "doc_type": DEFAULT_DOC_TYPE,
                },
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        parent_symbol_path = self._current_symbol_path()
        module = node.module or ""
        for alias in node.names:
            self.imports.append(ImportRecord(
                raw_module=module,
                imported_name=alias.name,
                alias=alias.asname,
                parent_symbol_path=parent_symbol_path,
                span=(node.lineno, node.lineno),
                metadata={
                    # F-02: relative-import depth (`from . import x` → 1)
                    "level": node.level,
                    "col_offset": node.col_offset,
                    "doc_type": DEFAULT_DOC_TYPE,
                },
            ))

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

        self.call_sites.append(CallSite(
            callee_name=name,
            receiver=receiver,
            caller_symbol_path=self._current_symbol_path(),
            span=(node.lineno, node.lineno),
            metadata={"col_offset": node.col_offset},
        ))

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
