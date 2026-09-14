# ingestion_service/src/core/extractors/treesitter/java.py
"""
JavaExtractor (WP-L4, DOCS/audit/03-Multi-Language-Graph-Plan.md §3,
issue #132): emits the same language-agnostic IR the Python/TS/Rust
extractors emit, for `.java` files, so GraphAssembler (additive-only
changes — see its WP-L4 comments) can produce
MODULE/CLASS/INTERFACE/ENUM/RECORD/METHOD nodes and IMPORTS/CALL/INHERITS
edges without any Java-specific code outside this file plus the
registry/module-convention wiring in repo_graph_builder.py.

Symbol kinds emitted: MODULE, CLASS, INTERFACE, ENUM, RECORD, METHOD.

v1 design decisions (DOCS audit plan + issue #132 acceptance criteria):
- Methods/constructors are syntactic children of their enclosing type's
  body (class_body/interface_body/enum_body's enum_body_declarations) —
  unlike Rust, there is no separate "impl block" indirection, so
  `_enclosing_symbol_node` walks the parent chain to the nearest
  classified type ancestor exactly like TS does for its classes.
- `extends`/`implements` land on `metadata["bases"]` (TS's exact
  pattern), reusing GraphAssembler's unmodified inheritance resolution —
  Rust's InheritRecord machinery isn't needed here since Java's bases are
  always declared inline on the type itself.
- Overload collapsing: Java allows multiple methods (or constructors)
  sharing a name in one type. Since canonical_id carries no parameter
  types (ADR-031: `relative_path#Outer.Inner.method`), all
  method_declaration/constructor_declaration nodes sharing an (enclosing
  type, bare name) key are grouped into ONE METHOD SymbolRecord, with
  `metadata["overload_signatures"]` listing each overload's parameter
  types (sorted for determinism, ADR-036). Constructors get the
  synthetic bare name `<init>` (can't collide with a real method name,
  which Java disallows anyway; avoids the `ClassName.ClassName`
  awkwardness).
- `new Foo(...)` is lowered to a CALL with receiver=`Foo`,
  callee_name=`<init>` — reuses the exact same `receiver.method()`
  resolution path as any other qualified call.
- Interface method declarations (no body) ARE extracted as METHOD
  symbols, unlike WP-L2's TS interface-member skip — Java's interface
  methods are syntactically identical siblings of class methods (same
  method_declaration node, just missing a body field), so skipping them
  would require MORE special-casing, not less.
- Single-class imports (`import com.acme.Util;`) are lowered "from-style"
  (module=`com.acme`, imported_name=`Util`), not "plain-style" — Java
  code always references the short name (`Util.calc()`), never the fully
  qualified form, mirroring Rust's `use crate::Item` insight. Wildcard
  imports (`import com.acme.*;`) are recorded best-effort/unresolved
  (mirrors TS's `export * from` / Rust's `use foo::*`). `import static
  ...;` is skipped entirely in v1 (documented gap — no acceptance
  criterion requires it).
- Locally-nested types/methods (a local or anonymous class inside a
  method body) are not extracted — an implementation detail, not part of
  the public API surface, mirroring Rust's identical decision for
  locally-nested `fn`.
- `this(...)`/`super(...)` constructor-chaining calls
  (`explicit_constructor_invocation`) are not extracted as CallSites in
  v1 — a documented gap, not required by any acceptance criterion.
- Annotations land on `metadata["annotations"]`, the same treatment as
  decorators elsewhere in this codebase. The package declaration lands on
  `metadata["package"]`/`metadata["fqcn"]` for search/display only —
  module *identity* stays purely path-derived (JavaModuleConvention),
  never dependent on the file's own `package` statement matching its
  directory.
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

_QUERY_DIR = Path(__file__).parent / "queries" / "java"
SYMBOLS_QUERY = (_QUERY_DIR / "symbols.scm").read_text(encoding="utf-8")
IMPORTS_QUERY = (_QUERY_DIR / "imports.scm").read_text(encoding="utf-8")
CALLS_QUERY = (_QUERY_DIR / "calls.scm").read_text(encoding="utf-8")

_TYPE_KINDS = {
    "class_declaration": "CLASS",
    "interface_declaration": "INTERFACE",
    "enum_declaration": "ENUM",
    "record_declaration": "RECORD",
}
_METHOD_LIKE = ("method_declaration", "constructor_declaration")
_BODY_MARKERS = ("block", "constructor_body")


def _classify(node: Node) -> Optional[Tuple[str, Node]]:
    kind = _TYPE_KINDS.get(node.type)
    if kind is None:
        return None
    name = node.child_by_field_name("name")
    return (kind, name) if name is not None else None


def _text(node: Optional[Node]) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _type_name_text(node: Node) -> str:
    """Bare type name, unwrapping `generic_type`
    (`Comparable<Animal>` -> `Comparable`) — the Java grammar gives this
    node's inner type_identifier no field name, so positional access via
    the first named child is required (unlike Rust's `generic_type`,
    which does have a `type` field)."""
    if node.type == "generic_type" and node.named_children:
        return _type_name_text(node.named_children[0])
    return _text(node)


def _extract_bases(node: Node) -> List[str]:
    bases: List[str] = []
    superclass = node.child_by_field_name("superclass")
    if superclass is not None and superclass.named_children:
        bases.append(_type_name_text(superclass.named_children[0]))
    interfaces_field = node.child_by_field_name("interfaces")
    if interfaces_field is not None and interfaces_field.named_children:
        type_list = interfaces_field.named_children[0]
        bases.extend(_type_name_text(t) for t in type_list.named_children)
    for child in node.children:
        # interface_declaration's own `extends A, B` (extends_interfaces)
        # has no field name, unlike class's `superclass`/`interfaces`.
        if child.type == "extends_interfaces" and child.named_children:
            type_list = child.named_children[0]
            bases.extend(_type_name_text(t) for t in type_list.named_children)
    return bases


def _extract_annotations(node: Node) -> List[str]:
    modifiers = next((c for c in node.children if c.type == "modifiers"), None)
    if modifiers is None:
        return []
    names = []
    for child in modifiers.named_children:
        if child.type in ("marker_annotation", "annotation"):
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                names.append(_text(name_node))
    return names


def _is_locally_nested(node: Node) -> bool:
    """True if `node`'s nearest containing scope is a method/constructor
    body rather than a type body or the file itself — a local or
    anonymous class/method, out of scope for v1 (mirrors Rust's identical
    decision for locally-nested `fn`). Transitive: a method inside a
    locally-nested class is itself locally nested even though its own
    immediate parent chain reaches that class (a classified ancestor)
    before any body marker — recurses on the enclosing type's own
    nesting status rather than stopping at the first classified node."""
    current = node.parent
    while current is not None:
        if current.type in _BODY_MARKERS:
            return True
        if current.type == "program":
            return False
        if _classify(current) is not None:
            return _is_locally_nested(current)
        current = current.parent
    return False


def _enclosing_symbol_node(node: Node) -> Optional[Node]:
    current = node.parent
    while current is not None:
        if _classify(current) is not None:
            return current
        current = current.parent
    return None


class JavaExtractor:
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        self.doc_type = "java source"
        stem = relative_path.rsplit("/", 1)[-1]
        if stem.endswith(".java"):
            stem = stem[: -len(".java")]
        self.module_name = stem
        self._symbol_path_cache: Dict[int, str] = {}
        self._package: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, source_code: str) -> ExtractionResult:
        tree = self._parse(source_code)
        language = language_for_path(self.relative_path)

        self._symbol_path_cache = {}
        self._package = self._find_package(tree.root_node)

        symbol_nodes = self._sorted_captures(language, SYMBOLS_QUERY, tree.root_node)
        call_nodes = self._sorted_captures(language, CALLS_QUERY, tree.root_node)
        import_nodes = self._sorted_captures(language, IMPORTS_QUERY, tree.root_node)

        symbols = self._build_symbols(source_code, symbol_nodes)
        imports = self._build_imports(import_nodes)
        calls = self._build_calls(call_nodes)

        return ExtractionResult(symbols=symbols, imports=imports, calls=calls)

    def _parse(self, source_code: str):
        parser = parser_for_path(self.relative_path)
        tree = parser.parse(source_code.encode("utf-8"))
        if tree.root_node.has_error:
            raise ValueError(f"tree-sitter parse errors in {self.relative_path}")
        return tree

    def _sorted_captures(self, language, query_source: str, root: Node) -> List[Node]:
        captures = run_query(language, query_source, root)
        return sorted(captures.get("node", []), key=lambda n: n.start_byte)

    def _find_package(self, root: Node) -> Optional[str]:
        for child in root.children:
            if child.type == "package_declaration":
                for sub in child.children:
                    if sub.type in ("scoped_identifier", "identifier"):
                        return _text(sub)
        return None

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    def _module_symbol(self, source_code: str) -> SymbolRecord:
        metadata: Dict[str, object] = {"doc_type": self.doc_type}
        if self._package:
            metadata["package"] = self._package
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
        classification = _classify(node)
        name_node = classification[1] if classification else None
        name = _text(name_node)
        parent_node = _enclosing_symbol_node(node)
        parent_path = (
            self._symbol_path_of(parent_node) if parent_node is not None else None
        )
        path = f"{parent_path}.{name}" if parent_path else name
        self._symbol_path_cache[node.id] = path
        return path

    def _build_symbols(
        self, source_code: str, symbol_nodes: List[Node]
    ) -> List[SymbolRecord]:
        symbols: List[SymbolRecord] = [self._module_symbol(source_code)]
        method_groups: Dict[Tuple[Optional[str], str], List[Node]] = {}

        for node in symbol_nodes:
            if _is_locally_nested(node):
                continue
            if node.type in _METHOD_LIKE:
                enclosing = _enclosing_symbol_node(node)
                if enclosing is None:
                    continue  # a method always has an enclosing type in Java
                parent_path = self._symbol_path_of(enclosing)
                if node.type == "constructor_declaration":
                    bare_name = "<init>"
                else:
                    bare_name = _text(node.child_by_field_name("name"))
                key = (parent_path, bare_name)
                method_groups.setdefault(key, []).append(node)
                continue

            classification = _classify(node)
            if classification is None:
                continue
            kind, _ = classification
            enclosing = _enclosing_symbol_node(node)
            symbols.append(self._lower_type_symbol(node, kind, enclosing))

        for (parent_path, bare_name), nodes in method_groups.items():
            symbols.append(self._lower_method_group(parent_path, bare_name, nodes))

        return symbols

    def _lower_type_symbol(
        self, node: Node, kind: str, enclosing: Optional[Node]
    ) -> SymbolRecord:
        symbol_path = self._symbol_path_of(node)
        parent_path = (
            self._symbol_path_of(enclosing) if enclosing is not None else None
        )
        lineno = node.start_point.row + 1
        end_lineno = node.end_point.row + 1
        metadata: Dict[str, object] = {
            "lineno": lineno,
            "col_offset": node.start_point.column,
            "doc_type": self.doc_type,
        }
        bases = _extract_bases(node)
        if bases:
            metadata["bases"] = bases
        annotations = _extract_annotations(node)
        if annotations:
            metadata["annotations"] = annotations
        if self._package:
            metadata["package"] = self._package
            metadata["fqcn"] = f"{self._package}.{symbol_path}"
        name_node = node.child_by_field_name("name")
        return SymbolRecord(
            kind=kind,
            name=_text(name_node),
            symbol_path=symbol_path,
            parent_symbol_path=parent_path,
            span=(lineno, end_lineno),
            text=_text(node),
            metadata=metadata,
        )

    def _lower_method_group(
        self, parent_path: Optional[str], bare_name: str, nodes: List[Node]
    ) -> SymbolRecord:
        nodes_sorted = sorted(nodes, key=lambda n: n.start_byte)
        primary = nodes_sorted[0]
        symbol_path = f"{parent_path}.{bare_name}" if parent_path else bare_name
        lineno = primary.start_point.row + 1
        end_lineno = primary.end_point.row + 1
        metadata: Dict[str, object] = {
            "lineno": lineno,
            "col_offset": primary.start_point.column,
            "doc_type": self.doc_type,
        }
        signatures = sorted(
            self._signature_text(bare_name, n) for n in nodes_sorted
        )
        if len(nodes_sorted) > 1:
            metadata["overload_signatures"] = signatures
        annotations = _extract_annotations(primary)
        if annotations:
            metadata["annotations"] = annotations
        return SymbolRecord(
            kind="METHOD",
            name=bare_name,
            symbol_path=symbol_path,
            parent_symbol_path=parent_path,
            span=(lineno, end_lineno),
            text=_text(primary),
            metadata=metadata,
        )

    def _signature_text(self, bare_name: str, node: Node) -> str:
        params = node.child_by_field_name("parameters")
        param_types: List[str] = []
        if params is not None:
            for child in params.named_children:
                if child.type == "formal_parameter":
                    type_node = child.child_by_field_name("type")
                    if type_node is not None:
                        param_types.append(_type_name_text(type_node))
        return f"{bare_name}({', '.join(param_types)})"

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _enclosing_caller_symbol_path(self, node: Node) -> Optional[str]:
        current = node.parent
        while current is not None:
            if current.type in _METHOD_LIKE and not _is_locally_nested(current):
                enclosing = _enclosing_symbol_node(current)
                if enclosing is not None:
                    parent_path = self._symbol_path_of(enclosing)
                    if current.type == "constructor_declaration":
                        return f"{parent_path}.<init>"
                    name = _text(current.child_by_field_name("name"))
                    return f"{parent_path}.{name}"
            current = current.parent
        return None

    def _lower_call(self, node: Node) -> Optional[CallSite]:
        if node.type == "object_creation_expression":
            type_node = node.child_by_field_name("type")
            if type_node is None:
                return None
            receiver = _type_name_text(type_node)
            name = "<init>"
        elif node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return None
            name = _text(name_node)
            object_node = node.child_by_field_name("object")
            receiver = _text(object_node) if object_node is not None else None
        else:
            return None

        caller_symbol_path = self._enclosing_caller_symbol_path(node)
        lineno = node.start_point.row + 1
        return CallSite(
            callee_name=name,
            receiver=receiver,
            caller_symbol_path=caller_symbol_path,
            span=(lineno, lineno),
            metadata={"col_offset": node.start_point.column},
        )

    def _build_calls(self, call_nodes: List[Node]) -> List[CallSite]:
        calls: List[CallSite] = []
        for node in call_nodes:
            call = self._lower_call(node)
            if call is not None:
                calls.append(call)
        return calls

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _lower_import(self, node: Node) -> List[ImportRecord]:
        is_static = any(c.type == "static" for c in node.children)
        if is_static:
            return []  # v1: static imports not extracted (documented gap)

        path_node = next(
            (c for c in node.children if c.type in ("scoped_identifier", "identifier")),
            None,
        )
        if path_node is None:
            return []
        is_wildcard = any(c.type == "asterisk" for c in node.children)

        segments = self._flatten_scoped_identifier(path_node)
        lineno = node.start_point.row + 1
        metadata: Dict[str, object] = {
            "col_offset": node.start_point.column,
            "doc_type": self.doc_type,
        }

        if is_wildcard:
            # `import com.acme.*;` — best-effort: recorded, unresolved
            # (v1, mirrors TS's `export * from` / Rust's `use foo::*`).
            return [
                ImportRecord(
                    raw_module=".".join(segments),
                    imported_name="*",
                    alias=None,
                    parent_symbol_path=None,
                    span=(lineno, lineno),
                    metadata=metadata,
                )
            ]

        if not segments:
            return []
        module = ".".join(segments[:-1])
        imported_name = segments[-1]
        return [
            ImportRecord(
                raw_module=module,
                imported_name=imported_name,
                alias=None,
                parent_symbol_path=None,  # `import` is always file-scoped
                span=(lineno, lineno),
                metadata=metadata,
            )
        ]

    def _flatten_scoped_identifier(self, node: Node) -> List[str]:
        if node.type == "identifier":
            return [_text(node)]
        if node.type == "scoped_identifier":
            scope = node.child_by_field_name("scope")
            name = node.child_by_field_name("name")
            parts = self._flatten_scoped_identifier(scope) if scope is not None else []
            if name is not None:
                parts.append(_text(name))
            return parts
        return [_text(node)]

    def _build_imports(self, import_nodes: List[Node]) -> List[ImportRecord]:
        imports: List[ImportRecord] = []
        for node in import_nodes:
            imports.extend(self._lower_import(node))
        return imports
