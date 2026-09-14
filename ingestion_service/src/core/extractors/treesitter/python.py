# ingestion_service/src/core/extractors/treesitter/python.py
"""
PythonTreeSitterExtractor (WP-L5, DOCS/audit/03-Multi-Language-Graph-Plan.md
§3, issue #134): emits the same language-agnostic IR PythonASTExtractor
emits, for `.py` files, built ALONGSIDE it — not a replacement — so a
config-flag rollback (see repo_graph_builder.py's _PythonExtractorProxy)
can always fall back to the proven ast-based extractor.

Symbol kinds emitted: MODULE, CLASS, FUNCTION, METHOD — identical to
PythonASTExtractor's set; no new IR kinds needed.

Deliberate bug-for-bug parity with PythonASTExtractor (this is a parity
migration, not a rewrite — fixing these is a separate, later decision):
- METHOD symbol_path is built from the NEAREST enclosing class ancestor's
  BARE name, not its full dotted symbol_path — so a method of a nested
  class (`Outer.Inner.method`) gets symbol_path `Inner.method`, not
  `Outer.Inner.method`. This mirrors PythonASTExtractor._get_parent_class,
  which returns `current.name` (bare) rather than a scope-stack path.
  parent_symbol_path is unaffected and stays fully qualified (`Outer.Inner`).
- A function nested inside another function is classified FUNCTION (bare
  name) unless SOME ancestor, however far up, is a class — mirroring
  _get_parent_class's unbounded upward walk (it does not stop at the
  first enclosing function).
- `args` metadata lists only plain positional-or-keyword parameter names
  (excludes *args/**kwargs and, best-effort, keyword-only params after a
  bare `*`) to mirror `[arg.arg for arg in node.args.args]`. Positional-
  only parameters (before a `/`) are NOT excluded here, unlike real
  ast.arguments.posonlyargs semantics — a known v1 fidelity gap for that
  one exotic signature shape, mirroring the bases-expression-text gap
  below. No acceptance criterion requires exact posonly parity, and the
  A/B parity harness's fixture repo avoids that shape.
- CLASS `metadata["bases"]` is the raw source text of each non-keyword
  argument_list entry (e.g. `pkg.Base`), not a fully-normalized
  ast.unparse() render — matches for simple names/dotted paths, which is
  all the parity fixture and Rust/Java/TS extractors' own bases exercise.

Partial-extraction-on-syntax-error (acceptance criterion, and the one
deliberate NON-parity improvement over PythonASTExtractor): tree-sitter
parses error-tolerantly by construction — a syntax error produces an
ERROR node in the tree rather than raising, and every class/function
definition outside the broken region still parses normally and is
extracted. Unlike JavaExtractor._parse (which raises ValueError on
tree.root_node.has_error), this extractor never raises for a parse
error — it simply extracts what tree-sitter could recover. This is
NOT diffed against PythonASTExtractor's skip-the-whole-file behavior by
the parity harness (see tests/fixtures/python_repo_syntax_error/ and
test_python_parity_harness.py's docstring) — the two behaviors are
intentionally different, so there is nothing to diff.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from tree_sitter import Node

from src.core.codebase.ir import CallSite, ExtractionResult, ImportRecord, SymbolRecord
from src.core.extractors.treesitter.base import (
    language_for_path,
    parser_for_path,
    run_query,
)

_QUERY_DIR = Path(__file__).parent / "queries" / "python"
SYMBOLS_QUERY = (_QUERY_DIR / "symbols.scm").read_text(encoding="utf-8")
IMPORTS_QUERY = (_QUERY_DIR / "imports.scm").read_text(encoding="utf-8")
CALLS_QUERY = (_QUERY_DIR / "calls.scm").read_text(encoding="utf-8")

DEFAULT_DOC_TYPE = "python source"

_DEF_KINDS = ("class_definition", "function_definition")
_SPLAT_KINDS = ("list_splat_pattern", "dictionary_splat_pattern")
_PARAM_WITH_NAME_FIELD = (
    "default_parameter", "typed_parameter", "typed_default_parameter",
)


def _text(node: Optional[Node]) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _effective_end(node: Node):
    """(end_byte, end_point) for `node`, excluding any trailing same-line
    `comment` node(s). tree-sitter's grammar attaches a trailing comment
    as the LAST child of the innermost block it falls inside, extending
    that ancestor's (and therefore this node's) own end_byte/end_point to
    cover it — Python's `ast` has no comment nodes at all, so
    PythonASTExtractor's text/span never includes one. Recurses into the
    last non-comment child so a comment nested arbitrarily deep at the
    end of the node (e.g. after the last statement of a nested block) is
    excluded too, not just one at this node's own top level."""
    children = node.children
    idx = len(children) - 1
    while idx >= 0 and children[idx].type == "comment":
        idx -= 1
    if idx < 0:
        return node.end_byte, node.end_point
    return _effective_end(children[idx])


def _build_ancestry(
    root: Node,
) -> tuple[Dict[int, Optional[Node]], Dict[int, Optional[Node]]]:
    """One top-down traversal computing, for every node, its nearest
    enclosing def (class_definition or function_definition) and its
    nearest class_definition ancestor at any depth — the two facts
    PythonASTExtractor's scope_stack / _get_parent_class provide via
    upward AST-parent links.

    Deliberately walks DOWN via `.children` rather than using tree-sitter's
    `Node.parent` for upward lookups: repeated `.parent` walks on nodes
    obtained from QueryCursor.captures() were found to segfault (access
    violation) on real-world files with this repo's tree-sitter 0.26.0 /
    tree-sitter-python 0.25.0 pairing — a native binding issue, not a
    logic bug. `.children`/`.child_by_field_name` are unaffected and are
    used throughout this module instead."""
    enclosing_def: Dict[int, Optional[Node]] = {}
    nearest_class: Dict[int, Optional[Node]] = {}

    def walk(node: Node, def_top: Optional[Node], class_top: Optional[Node]) -> None:
        enclosing_def[node.id] = def_top
        nearest_class[node.id] = class_top

        if node.type == "decorated_definition":
            # PythonASTExtractor bug-for-bug quirk: ast.NodeVisitor's
            # generic_visit(FunctionDef/ClassDef) visits `decorator_list`
            # as one of that node's OWN fields, AFTER scope_stack has
            # already been pushed for it — so a call inside a decorator
            # expression (`@app.get(...)`) is attributed to the function
            # it decorates, not to the enclosing scope. tree-sitter's
            # grammar instead makes `decorator` a SIBLING of the
            # function/class it decorates (both children of
            # decorated_definition), so without this special case a
            # decorator's calls would get the outer scope instead.
            inner = node.child_by_field_name("definition")
            inner_is_def = inner is not None and inner.type in _DEF_KINDS
            inner_is_class = inner is not None and inner.type == "class_definition"
            decorator_def_top = inner if inner_is_def else def_top
            decorator_class_top = inner if inner_is_class else class_top
            for child in node.children:
                if child.type == "decorator":
                    walk(child, decorator_def_top, decorator_class_top)
                else:
                    walk(child, def_top, class_top)
            return

        next_def_top = node if node.type in _DEF_KINDS else def_top
        next_class_top = node if node.type == "class_definition" else class_top
        for child in node.children:
            walk(child, next_def_top, next_class_top)

    walk(root, None, None)
    return enclosing_def, nearest_class


def _param_identifier_name(child: Node) -> Optional[str]:
    """The identifier text for one `parameters` child that is known to
    carry a name (identifier, default_parameter, typed_parameter,
    typed_default_parameter) — NOT a splat/separator. `typed_parameter`
    carries no "name" field for its identifier — unlike
    default_parameter/typed_default_parameter, which do — so it must be
    found positionally (its first child) instead."""
    if child.type == "identifier":
        return _text(child)
    name_node = child.child_by_field_name("name")
    if name_node is None and child.named_children:
        name_node = child.named_children[0]
    return _text(name_node) if name_node is not None else None


def _param_unwrapped(child: Node) -> Node:
    """`*args: T`/`**kwargs: T` (typed) wrap the splat pattern INSIDE a
    typed_parameter — e.g. typed_parameter[dictionary_splat_pattern, ":",
    type] — so a splat check must look past that wrapper, or `**fields:
    Any` gets misread as a plain named "**fields" param."""
    if child.type in _PARAM_WITH_NAME_FIELD and child.named_children:
        return child.named_children[0]
    return child


def _param_names(params_node: Optional[Node]) -> List[str]:
    """Positional-or-keyword parameter names only — mirrors
    `[arg.arg for arg in node.args.args]` (excludes *args/**kwargs and
    keyword-only params after a bare `*`; does NOT exclude positional-
    only params before a `/`, a documented v1 gap — see module docstring)."""
    if params_node is None:
        return []
    names: List[str] = []
    seen_star = False
    for child in params_node.named_children:
        is_splat = _param_unwrapped(child).type in _SPLAT_KINDS
        if child.type == "keyword_separator" or is_splat:
            seen_star = True
            continue
        if seen_star or child.type not in (*_PARAM_WITH_NAME_FIELD, "identifier"):
            continue
        name = _param_identifier_name(child)
        if name is not None:
            names.append(name)
    return names


class PythonTreeSitterExtractor:
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        # Matches PythonASTExtractor's own module_name derivation exactly
        # (F-05: strip the ".py" suffix, not the character set).
        module_path = (
            relative_path[:-3] if relative_path.endswith(".py") else relative_path
        )
        self.module_name = module_path.replace("/", ".")
        # node.id -> (kind, symbol_path)
        self._symbol_path_cache: Dict[int, tuple[str, str]] = {}
        self._enclosing_def: Dict[int, Optional[Node]] = {}
        self._nearest_class: Dict[int, Optional[Node]] = {}
        self._source_bytes: bytes = b""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, source_code: str) -> ExtractionResult:
        self._source_bytes = source_code.encode("utf-8")
        tree = parser_for_path(self.relative_path).parse(self._source_bytes)
        language = language_for_path(self.relative_path)
        self._symbol_path_cache = {}
        self._enclosing_def, self._nearest_class = _build_ancestry(tree.root_node)

        symbol_nodes = self._sorted_captures(language, SYMBOLS_QUERY, tree.root_node)
        import_nodes = self._sorted_captures(language, IMPORTS_QUERY, tree.root_node)
        call_nodes = self._sorted_captures(language, CALLS_QUERY, tree.root_node)

        symbols = [self._module_symbol(source_code)]
        symbols.extend(self._build_symbol(node) for node in symbol_nodes)
        imports = self._build_imports(import_nodes)
        calls = [c for node in call_nodes if (c := self._build_call(node)) is not None]

        return ExtractionResult(symbols=symbols, imports=imports, calls=calls)

    def _sorted_captures(self, language, query_source: str, root: Node) -> List[Node]:
        captures = run_query(language, query_source, root)
        return sorted(captures.get("node", []), key=lambda n: n.start_byte)

    # ------------------------------------------------------------------
    # Symbol path / classification (bug-compatible with the AST scope
    # stack — see module docstring)
    # ------------------------------------------------------------------

    def _classify_and_path(self, node: Node) -> tuple[str, str]:
        cached = self._symbol_path_cache.get(node.id)
        if cached is not None:
            return cached

        parent_def = self._enclosing_def.get(node.id)
        parent_path = (
            self._classify_and_path(parent_def)[1] if parent_def is not None else None
        )

        if node.type == "class_definition":
            name = _text(node.child_by_field_name("name"))
            kind = "CLASS"
            symbol_path = f"{parent_path}.{name}" if parent_path else name
        else:
            name = _text(node.child_by_field_name("name"))
            nearest_class = self._nearest_class.get(node.id)
            if nearest_class is not None:
                kind = "METHOD"
                class_bare_name = _text(nearest_class.child_by_field_name("name"))
                symbol_path = f"{class_bare_name}.{name}"
            else:
                kind = "FUNCTION"
                symbol_path = name

        result = (kind, symbol_path)
        self._symbol_path_cache[node.id] = result
        return result

    def _parent_symbol_path(self, node: Node) -> Optional[str]:
        parent_def = self._enclosing_def.get(node.id)
        if parent_def is None:
            return None
        return self._classify_and_path(parent_def)[1]

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    def _module_symbol(self, source_code: str) -> SymbolRecord:
        return SymbolRecord(
            kind="MODULE",
            name=self.module_name,
            symbol_path=None,
            parent_symbol_path=None,
            span=None,
            text=source_code,
            metadata={"doc_type": DEFAULT_DOC_TYPE},
        )

    def _build_symbol(self, node: Node) -> SymbolRecord:
        kind, symbol_path = self._classify_and_path(node)
        parent_symbol_path = self._parent_symbol_path(node)
        name = _text(node.child_by_field_name("name"))
        lineno = node.start_point.row + 1
        end_byte, end_point = _effective_end(node)
        end_lineno = end_point.row + 1

        if kind == "CLASS":
            metadata: Dict[str, object] = {
                "lineno": lineno,
                "col_offset": node.start_point.column,
                "bases": self._extract_bases(node),
                "doc_type": DEFAULT_DOC_TYPE,
            }
        else:
            params_node = node.child_by_field_name("parameters")
            metadata = {
                "lineno": lineno,
                "col_offset": node.start_point.column,
                "args": _param_names(params_node),
                "is_async": any(c.type == "async" for c in node.children),
                "doc_type": DEFAULT_DOC_TYPE,
            }

        text = self._source_bytes[node.start_byte:end_byte].decode(
            "utf-8", errors="replace"
        )
        return SymbolRecord(
            kind=kind,
            name=name,
            symbol_path=symbol_path,
            parent_symbol_path=parent_symbol_path,
            span=(lineno, end_lineno),
            text=text,
            metadata=metadata,
        )

    def _extract_bases(self, node: Node) -> List[str]:
        args_node = node.child_by_field_name("superclasses")
        if args_node is None:
            return []
        bases: List[str] = []
        for child in args_node.named_children:
            if child.type == "keyword_argument":
                continue  # metaclass=..., etc. — not a base
            bases.append(_text(child))
        return bases

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _build_call(self, node: Node) -> Optional[CallSite]:
        func_node = node.child_by_field_name("function")
        if func_node is None:
            return None
        if func_node.type == "attribute":
            name = _text(func_node.child_by_field_name("attribute"))
            receiver = _text(func_node.child_by_field_name("object"))
        elif func_node.type == "identifier":
            name = _text(func_node)
            receiver = None
        else:
            name = _text(func_node)
            receiver = None

        lineno = node.start_point.row + 1
        return CallSite(
            callee_name=name,
            receiver=receiver,
            caller_symbol_path=self._parent_symbol_path(node),
            span=(lineno, lineno),
            metadata={"col_offset": node.start_point.column},
        )

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _build_imports(self, import_nodes: List[Node]) -> List[ImportRecord]:
        imports: List[ImportRecord] = []
        for node in import_nodes:
            if node.type == "import_statement":
                imports.extend(self._lower_import_statement(node))
            else:  # import_from_statement or future_import_statement
                imports.extend(self._lower_import_from_statement(node))
        return imports

    def _lower_import_statement(self, node: Node) -> List[ImportRecord]:
        parent_symbol_path = self._parent_symbol_path(node)
        lineno = node.start_point.row + 1
        records: List[ImportRecord] = []
        for name_node in node.children_by_field_name("name"):
            if name_node.type == "aliased_import":
                raw_module = _text(name_node.child_by_field_name("name"))
                alias = _text(name_node.child_by_field_name("alias"))
            else:
                raw_module = _text(name_node)
                alias = None
            records.append(ImportRecord(
                raw_module=raw_module,
                imported_name=None,
                alias=alias,
                parent_symbol_path=parent_symbol_path,
                span=(lineno, lineno),
                metadata={
                    "col_offset": node.start_point.column,
                    "doc_type": DEFAULT_DOC_TYPE,
                },
            ))
        return records

    def _lower_import_from_statement(self, node: Node) -> List[ImportRecord]:
        parent_symbol_path = self._parent_symbol_path(node)
        lineno = node.start_point.row + 1
        if node.type == "future_import_statement":
            # `from __future__ import x` — its own grammar rule with no
            # module_name field (the module is always the literal
            # `__future__` token, not a dotted_name node).
            module, level = "__future__", 0
        else:
            module_node = node.child_by_field_name("module_name")
            module, level = self._module_and_level(module_node)

        # `wildcard_import` (`from x import *`) carries no "name" field —
        # unlike aliased_import/dotted_name targets, which do — so it must
        # be found by scanning children directly, or `from x import *`
        # would silently drop the import entirely.
        name_nodes = list(node.children_by_field_name("name"))
        if not name_nodes:
            wildcard = next(
                (c for c in node.children if c.type == "wildcard_import"), None
            )
            if wildcard is not None:
                name_nodes = [wildcard]

        records: List[ImportRecord] = []
        for name_node in name_nodes:
            if name_node.type == "aliased_import":
                imported_name = _text(name_node.child_by_field_name("name"))
                alias = _text(name_node.child_by_field_name("alias"))
            elif name_node.type == "wildcard_import":
                imported_name = "*"
                alias = None
            else:
                imported_name = _text(name_node)
                alias = None
            records.append(ImportRecord(
                raw_module=module,
                imported_name=imported_name,
                alias=alias,
                parent_symbol_path=parent_symbol_path,
                span=(lineno, lineno),
                metadata={
                    "level": level,
                    "col_offset": node.start_point.column,
                    "doc_type": DEFAULT_DOC_TYPE,
                },
            ))
        return records

    def _module_and_level(self, module_node: Optional[Node]) -> tuple[str, int]:
        if module_node is None:
            return "", 0
        if module_node.type == "relative_import":
            prefix_node = next(
                (c for c in module_node.children if c.type == "import_prefix"), None
            )
            level = _text(prefix_node).count(".") if prefix_node is not None else 0
            dotted = next(
                (c for c in module_node.children if c.type == "dotted_name"), None
            )
            return (_text(dotted), level)
        return (_text(module_node), 0)
