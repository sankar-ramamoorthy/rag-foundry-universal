# ingestion_service/src/core/extractors/treesitter/typescript.py
"""
TypeScriptExtractor (WP-L2, DOCS/audit/03-Multi-Language-Graph-Plan.md §3):
emits the same language-agnostic IR (SymbolRecord/ImportRecord/CallSite)
the Python extractor emits, for `.ts`/`.tsx`/`.js`/`.jsx`/`.mjs`/`.cjs`
files, so GraphAssembler (unmodified in its resolution algorithm — see
graph_assembler.py's WP-L2 comments for the two additive exceptions) can
produce MODULE/CLASS/INTERFACE/FUNCTION/METHOD nodes, IMPORTS/CALL/INHERITS
edges without any language-specific code outside this file plus the
registry/module-convention wiring in repo_graph_builder.py.

Symbol kinds emitted: MODULE, CLASS, INTERFACE, FUNCTION, METHOD. Only
named function declarations, `const name = () => {}` / `const name =
function() {}` bindings, and class-property arrows become symbols;
anonymous function/arrow expressions are counted (not identity-bearing) in
the nearest enclosing symbol's `metadata.anonymous_functions_skipped`
(FR-002). `extends`/`implements` land on `metadata.bases` (CLASS.bases is
reused as-is, matching Python's precedent — no new IR shape needed;
ir.py's InheritRecord stays unused here too).

Grammar note: interface member signatures (`method(): void` with no body)
are not extracted as separate METHOD symbols in v1 — interfaces are
structural types with no implementation to embed, and no acceptance
criterion in the WP-L2 spec requires it (Assumptions, specs/
002-typescript-js-extractor/spec.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tree_sitter import Node

from src.core.codebase.ir import CallSite, ExtractionResult, ImportRecord, SymbolRecord
from src.core.extractors.treesitter.base import (
    language_for_path,
    parser_for_path,
    run_query,
)

_QUERY_DIR = Path(__file__).parent / "queries" / "typescript"
SYMBOLS_QUERY_TS = (_QUERY_DIR / "symbols_ts.scm").read_text(encoding="utf-8")
SYMBOLS_QUERY_JS = (_QUERY_DIR / "symbols_js.scm").read_text(encoding="utf-8")
IMPORTS_QUERY = (_QUERY_DIR / "imports.scm").read_text(encoding="utf-8")
CALLS_QUERY = (_QUERY_DIR / "calls.scm").read_text(encoding="utf-8")

_TS_SUFFIXES = (".ts", ".tsx")
_JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs")
_ALL_SUFFIXES = _TS_SUFFIXES + _JS_SUFFIXES

_FIELD_DEFINITION_TYPES = ("public_field_definition", "field_definition")
_FUNCTION_VALUE_TYPES = ("arrow_function", "function_expression")


def _classify(node: Node) -> Optional[Tuple[str, Node]]:
    """Return (kind, name_node) if `node` is symbol-bearing, else None.
    Pure function of node shape — also used to test whether an arrow/
    function expression is a *named* binding (its parent classifies) vs.
    an anonymous one (FR-002)."""
    t = node.type
    if t == "class_declaration":
        name = node.child_by_field_name("name")
        return ("CLASS", name) if name is not None else None
    if t == "interface_declaration":
        name = node.child_by_field_name("name")
        return ("INTERFACE", name) if name is not None else None
    if t == "function_declaration":
        name = node.child_by_field_name("name")
        return ("FUNCTION", name) if name is not None else None
    if t == "method_definition":
        name = node.child_by_field_name("name")
        return ("METHOD", name) if name is not None else None
    if t in _FIELD_DEFINITION_TYPES:
        value = node.child_by_field_name("value")
        # TypeScript's `public_field_definition` names the field-name
        # field "name"; plain JavaScript's `field_definition` names the
        # identical position "property" instead.
        name = (
            node.child_by_field_name("name")
            or node.child_by_field_name("property")
        )
        is_function_value = value is not None and value.type in _FUNCTION_VALUE_TYPES
        if is_function_value and name is not None:
            return ("METHOD", name)
        return None
    if t == "variable_declarator":
        value = node.child_by_field_name("value")
        name = node.child_by_field_name("name")
        if (
            value is not None
            and value.type in _FUNCTION_VALUE_TYPES
            and name is not None
            and name.type == "identifier"
        ):
            return ("FUNCTION", name)
        return None
    return None


def _enclosing_symbol_node(node: Node) -> Optional[Node]:
    current = node.parent
    while current is not None:
        if _classify(current) is not None:
            return current
        current = current.parent
    return None


def _is_default_export(node: Node) -> bool:
    """`export default function f() {}` / `export default class X {}` —
    the plan doc's "TS default exports: synthesize `default` symbol name"
    (DOCS/audit/03-Multi-Language-Graph-Plan.md §2): a default-imported
    binding (`import x from "./mod"`) always looks up the literal name
    `default` in the target module's symbol table, so the exported
    declaration's *symbol_path* becomes `default` regardless of its own
    declared name (which is preserved in SymbolRecord.name for display)."""
    parent = node.parent
    if parent is None or parent.type != "export_statement":
        return False
    return any(c.type == "default" for c in parent.children)


def _is_require_call(node: Node) -> bool:
    fn = node.child_by_field_name("function")
    return fn is not None and fn.type == "identifier" and fn.text == b"require"


def _first_child_of_type(node: Node, type_name: str) -> Optional[Node]:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _text(node: Optional[Node]) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


class TypeScriptExtractor:
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        self.doc_type = (
            "typescript source"
            if relative_path.endswith(_TS_SUFFIXES)
            else "javascript source"
        )
        stem = relative_path.rsplit("/", 1)[-1]
        for suffix in _ALL_SUFFIXES:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        self.module_name = stem
        self._symbol_path_cache: Dict[int, Optional[str]] = {}
        self._anon_counts: Dict[Optional[int], int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, source_code: str) -> ExtractionResult:
        tree = self._parse(source_code)
        language = language_for_path(self.relative_path)

        self._symbol_path_cache = {}
        self._anon_counts = {}

        symbols_query = (
            SYMBOLS_QUERY_TS
            if self.relative_path.endswith(_TS_SUFFIXES)
            else SYMBOLS_QUERY_JS
        )
        symbol_nodes = self._sorted_captures(language, symbols_query, tree.root_node)
        call_nodes = self._sorted_captures(language, CALLS_QUERY, tree.root_node)
        import_nodes = self._sorted_captures(language, IMPORTS_QUERY, tree.root_node)

        # Pass 1: anonymous-callback counting must precede symbol lowering
        # so each owner's metadata count is available when its own
        # SymbolRecord is built (FR-002).
        self._count_anonymous_callbacks(symbol_nodes)

        symbols = self._build_symbols(source_code, symbol_nodes)
        imports, require_ids = self._build_imports(call_nodes, import_nodes)
        calls = self._build_calls(call_nodes, require_ids)

        return ExtractionResult(symbols=symbols, imports=imports, calls=calls)

    def _parse(self, source_code: str):
        parser = parser_for_path(self.relative_path)
        tree = parser.parse(source_code.encode("utf-8"))
        if tree.root_node.has_error:
            # Mirrors ast.parse raising SyntaxError for Python: the
            # per-file try/except in RepoGraphBuilder.build() skips this
            # file without aborting the rest of ingestion (spec Edge Cases).
            raise ValueError(f"tree-sitter parse errors in {self.relative_path}")
        return tree

    def _count_anonymous_callbacks(self, symbol_nodes: List[Node]) -> None:
        for node in symbol_nodes:
            if node.type not in _FUNCTION_VALUE_TYPES:
                continue
            if node.parent is not None and _classify(node.parent) is not None:
                continue  # named binding — counted as its own symbol instead
            owner = _enclosing_symbol_node(node)
            key = owner.id if owner is not None else None
            self._anon_counts[key] = self._anon_counts.get(key, 0) + 1

    def _build_symbols(
        self, source_code: str, symbol_nodes: List[Node]
    ) -> List[SymbolRecord]:
        symbols: List[SymbolRecord] = [self._module_symbol(source_code)]
        for node in symbol_nodes:
            if node.type in _FUNCTION_VALUE_TYPES:
                continue
            classification = _classify(node)
            if classification is None:
                continue
            kind, name_node = classification
            symbols.append(self._lower_symbol(node, kind, name_node))
        return symbols

    def _build_imports(
        self, call_nodes: List[Node], import_nodes: List[Node]
    ) -> Tuple[List[ImportRecord], set]:
        imports: List[ImportRecord] = []
        require_ids: set = set()
        for node in call_nodes:
            if _is_require_call(node):
                require_ids.add(node.id)
                imports.extend(self._lower_require(node))
        for node in import_nodes:
            imports.extend(self._lower_import_node(node))
        return imports, require_ids

    def _build_calls(self, call_nodes: List[Node], require_ids: set) -> List[CallSite]:
        calls: List[CallSite] = []
        for node in call_nodes:
            if node.id in require_ids:
                continue
            call = self._lower_call(node)
            if call is not None:
                calls.append(call)
        return calls

    # ------------------------------------------------------------------
    # Query plumbing
    # ------------------------------------------------------------------

    def _sorted_captures(self, language, query_source: str, root: Node) -> List[Node]:
        captures = run_query(language, query_source, root)
        return sorted(captures.get("node", []), key=lambda n: n.start_byte)

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    def _module_symbol(self, source_code: str) -> SymbolRecord:
        metadata: Dict[str, object] = {"doc_type": self.doc_type}
        count = self._anon_counts.get(None, 0)
        if count:
            metadata["anonymous_functions_skipped"] = count
        return SymbolRecord(
            kind="MODULE",
            name=self.module_name,
            symbol_path=None,
            parent_symbol_path=None,
            span=None,
            text=source_code,
            metadata=metadata,
        )

    def _symbol_path_of(self, node: Node) -> str:
        cached = self._symbol_path_cache.get(node.id)
        if cached is not None:
            return cached
        kind, name_node = _classify(node)  # type: ignore[misc]
        name = _text(name_node)
        parent_node = _enclosing_symbol_node(node)
        parent_path = (
            self._symbol_path_of(parent_node) if parent_node is not None else None
        )
        if parent_path is None and _is_default_export(node):
            path = "default"
        else:
            path = f"{parent_path}.{name}" if parent_path else name
        self._symbol_path_cache[node.id] = path
        return path

    def _lower_symbol(self, node: Node, kind: str, name_node: Node) -> SymbolRecord:
        name = _text(name_node)
        symbol_path = self._symbol_path_of(node)
        parent_node = _enclosing_symbol_node(node)
        parent_symbol_path = (
            self._symbol_path_of(parent_node) if parent_node is not None else None
        )
        lineno = node.start_point.row + 1
        end_lineno = node.end_point.row + 1
        metadata: Dict[str, object] = {
            "lineno": lineno,
            "col_offset": node.start_point.column,
            "doc_type": self.doc_type,
        }
        if kind in ("CLASS", "INTERFACE"):
            metadata["bases"] = self._extract_bases(node)
        if kind in ("FUNCTION", "METHOD"):
            metadata["is_async"] = self._is_async(node)
        if parent_symbol_path is None and _is_default_export(node):
            # SymbolTable indexes by `name`, not symbol_path (build_symbol_
            # table/symbol_table.py) — a default import always looks up
            # the bare name "default" (ADR-032 layer 2 binding), so `name`
            # must become "default" too, not just symbol_path, or
            # cross-file default-import call/inherits resolution silently
            # falls through to EXTERNAL_SYMBOL. The declared name is kept
            # in metadata for display.
            metadata["default_export"] = True
            metadata["declared_name"] = name
            name = "default"
        count = self._anon_counts.get(node.id, 0)
        if count:
            metadata["anonymous_functions_skipped"] = count
        return SymbolRecord(
            kind=kind,
            name=name,
            symbol_path=symbol_path,
            parent_symbol_path=parent_symbol_path,
            span=(lineno, end_lineno),
            text=_text(node),
            metadata=metadata,
        )

    def _is_async(self, node: Node) -> bool:
        target = node
        if node.type == "variable_declarator" or node.type in _FIELD_DEFINITION_TYPES:
            value = node.child_by_field_name("value")
            if value is not None:
                target = value
        return any(c.type == "async" for c in target.children)

    def _extract_bases(self, node: Node) -> List[str]:
        bases: List[str] = []
        if node.type == "interface_declaration":
            clause = _first_child_of_type(node, "extends_type_clause")
            if clause is not None:
                bases.extend(self._base_name_text(b) for b in clause.named_children)
            return bases

        heritage = _first_child_of_type(node, "class_heritage")
        if heritage is None:
            return bases
        for child in heritage.named_children:
            if child.type == "extends_clause":
                value = child.child_by_field_name("value")
                if value is not None:
                    bases.append(self._base_name_text(value))
            elif child.type == "implements_clause":
                bases.extend(self._base_name_text(b) for b in child.named_children)
            else:
                # Plain JavaScript grammar: class_heritage wraps the base
                # expression directly (no extends_clause wrapper).
                bases.append(self._base_name_text(child))
        return bases

    def _base_name_text(self, node: Node) -> str:
        if node.type == "generic_type":
            name = node.child_by_field_name("name")
            if name is not None:
                return _text(name)
        return _text(node)

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _lower_call(self, node: Node) -> Optional[CallSite]:
        fn = node.child_by_field_name("function")
        if fn is None:
            return None
        if fn.type == "identifier":
            name = _text(fn)
            receiver = None
        elif fn.type == "member_expression":
            prop = fn.child_by_field_name("property")
            if prop is None:
                return None
            name = _text(prop)
            obj = fn.child_by_field_name("object")
            receiver = _text(obj) if obj is not None else None
        else:
            return None

        owner = _enclosing_symbol_node(node)
        parent_symbol_path = self._symbol_path_of(owner) if owner is not None else None
        lineno = node.start_point.row + 1
        return CallSite(
            callee_name=name,
            receiver=receiver,
            caller_symbol_path=parent_symbol_path,
            span=(lineno, lineno),
            metadata={"col_offset": node.start_point.column},
        )

    # ------------------------------------------------------------------
    # Imports: ESM import/export-from
    # ------------------------------------------------------------------

    def _lower_import_node(self, node: Node) -> List[ImportRecord]:
        source_node = node.child_by_field_name("source")
        if source_node is None:
            return []  # e.g. `export class X {}` — not an import at all

        source = self._string_value(source_node)
        lineno = node.start_point.row + 1
        meta_base = {"col_offset": node.start_point.column, "doc_type": self.doc_type}

        def record(imported_name: str, alias: Optional[str]) -> ImportRecord:
            return ImportRecord(
                raw_module=source,
                imported_name=imported_name,
                alias=alias,
                parent_symbol_path=None,  # ESM import/export is always module-scoped
                span=(lineno, lineno),
                metadata=dict(meta_base),
            )

        if node.type == "import_statement":
            return self._records_from_import_clause(node, record)
        return self._records_from_export_clause(node, record)

    def _records_from_import_clause(self, node: Node, record) -> List[ImportRecord]:
        clause = _first_child_of_type(node, "import_clause")
        if clause is None:
            return [record("*", None)]  # `import "./side-effect"`
        records: List[ImportRecord] = []
        for child in clause.children:
            if child.type == "identifier":
                records.append(record("default", _text(child)))
            elif child.type == "namespace_import":
                local = _first_child_of_type(child, "identifier")
                records.append(record("*", _text(local) if local else None))
            elif child.type == "named_imports":
                records.extend(
                    self._records_from_specifiers(child, "import_specifier", record)
                )
        return records

    def _records_from_export_clause(self, node: Node, record) -> List[ImportRecord]:
        # export_statement with a `source` field: `export {...} from "..."`
        # or `export * from "..."`.
        clause = _first_child_of_type(node, "export_clause")
        if clause is None:
            return [record("*", None)]
        return self._records_from_specifiers(clause, "export_specifier", record)

    def _records_from_specifiers(
        self, clause: Node, specifier_type: str, record
    ) -> List[ImportRecord]:
        records: List[ImportRecord] = []
        for spec in clause.named_children:
            if spec.type != specifier_type:
                continue
            name_node = spec.child_by_field_name("name")
            alias_node = spec.child_by_field_name("alias")
            if name_node is None:
                continue
            records.append(record(_text(name_node), _text(alias_node) or None))
        return records

    # ------------------------------------------------------------------
    # Imports: CommonJS require()
    # ------------------------------------------------------------------

    def _lower_require(self, node: Node) -> List[ImportRecord]:
        args = node.child_by_field_name("arguments")
        source = self._first_string_literal(args) if args is not None else None
        if source is None:
            return []  # dynamic require(expr) — not statically resolvable

        lineno = node.start_point.row + 1
        meta_base = {"col_offset": node.start_point.column, "doc_type": self.doc_type}
        owner = _enclosing_symbol_node(node)
        parent_symbol_path = self._symbol_path_of(owner) if owner is not None else None

        def record(imported_name: str, alias: Optional[str]) -> ImportRecord:
            return ImportRecord(
                raw_module=source,
                imported_name=imported_name,
                alias=alias,
                parent_symbol_path=parent_symbol_path,
                span=(lineno, lineno),
                metadata=dict(meta_base),
            )

        declarator = self._binding_declarator_for(node)
        if declarator is None:
            return [record("*", None)]  # side-effect require("./x");
        return self._records_from_require_binding(declarator, record)

    def _binding_declarator_for(self, node: Node) -> Optional[Node]:
        """The `variable_declarator` this require() call is the `value`
        of, or None if it's a bare/side-effect require() call."""
        declarator = node.parent
        if declarator is None or declarator.type != "variable_declarator":
            return None
        value = declarator.child_by_field_name("value")
        return declarator if value is not None and value.id == node.id else None

    def _records_from_require_binding(
        self, declarator: Node, record
    ) -> List[ImportRecord]:
        name_node = declarator.child_by_field_name("name")
        if name_node is None:
            return [record("*", None)]
        if name_node.type == "identifier":
            return [record("*", _text(name_node))]
        if name_node.type != "object_pattern":
            return []
        records: List[ImportRecord] = []
        for child in name_node.named_children:
            if child.type == "shorthand_property_identifier_pattern":
                records.append(record(_text(child), None))
            elif child.type == "pair_pattern":
                key = child.child_by_field_name("key")
                value = child.child_by_field_name("value")
                if key is not None:
                    records.append(record(_text(key), _text(value) or None))
        return records

    def _first_string_literal(self, args_node: Node) -> Optional[str]:
        for child in args_node.named_children:
            if child.type == "string":
                return self._string_value(child)
        return None

    def _string_value(self, string_node: Node) -> str:
        fragments = [
            _text(c) for c in string_node.children if c.type == "string_fragment"
        ]
        return "".join(fragments)
