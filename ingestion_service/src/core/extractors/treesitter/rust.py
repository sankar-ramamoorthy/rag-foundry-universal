# ingestion_service/src/core/extractors/treesitter/rust.py
"""
RustExtractor (WP-L3, DOCS/audit/03-Multi-Language-Graph-Plan.md §3,
issue #130): emits the same language-agnostic IR the Python/TS extractors
emit, for `.rs` files, so GraphAssembler (additive-only changes — see its
WP-L3 comments) can produce MODULE/STRUCT/ENUM/TRAIT/FUNCTION/METHOD nodes
and IMPORTS/CALL/INHERITS edges without any Rust-specific code outside this
file plus the registry/module-convention wiring in repo_graph_builder.py.

Symbol kinds emitted: MODULE, STRUCT, ENUM, TRAIT, FUNCTION, METHOD.

v1 design decisions (DOCS audit plan + issue #130 acceptance criteria):
- `impl Type { fn m() }` blocks are transparent: `fn`s inside an impl
  become METHOD symbols with symbol_path `Type.m` directly (no IMPL node
  kind) — multiple impl blocks for the same type merge automatically
  since canonical_id is keyed by symbol_path, not by which impl block
  wrote it. Limitation: this merge (and the METHOD's DEFINES edge from
  its type) only works when the impl block is in the SAME FILE as the
  type's own struct/enum definition — canonical_id is always
  relative_path-scoped (ADR-031), so a method's parent_id can only match
  a struct/enum entity extracted from that same file. Cross-file
  `impl Type` blocks for a type defined elsewhere are a known v1 gap
  (impl-block methods, unlike `impl Trait for Type` relationships below,
  aren't independently re-resolved against a repo-wide name lookup).
- `impl Trait for Type` emits an InheritRecord (ir.py), not
  metadata["bases"] — GraphAssembler._resolve_inherit_records resolves
  both the type name and the trait name independently via the same
  same-file/import/global machinery as any other name, so this works
  correctly even when the impl lives in a different file than either the
  type or the trait.
- `self.method()` receivers already resolve via GraphAssembler's existing
  self/cls/this handling. `Self::assoc_fn()` (capital-S) is rewritten by
  this extractor at lowering time to the actual enclosing impl target's
  type name, so GraphAssembler never needs a "Self" special case.
  `Type::method()` (explicit qualified call, no `self`) is lowered the
  same way TS lowers `receiver.method()` member calls.
- Inline `mod name { ... }` blocks are v1-transparent: their contents are
  extracted as if declared at file top level (no `mod.`-prefixed
  symbol_path segment). File-based module trees (`foo/mod.rs`,
  `foo/bar.rs`) are what the plan doc's WP-L3 module-map direction
  actually targets — see RustModuleConvention in module_conventions.py.
- Trait method *declarations* (`function_signature_item`, no body) and
  default-bodied trait methods are not extracted as METHOD symbols in v1
  — mirrors WP-L2's identical decision for TS interface members (no
  acceptance criterion requires it). Locally-nested `fn` (a function
  defined inside another function's body) is likewise not extracted —
  an implementation detail, not part of the public API surface.
- Macros: bodies are never inspected; each owning symbol's
  metadata["macro_invocations"] records a count only (no expansion).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tree_sitter import Node

from src.core.codebase.ir import (
    CallSite,
    ExtractionResult,
    ImportRecord,
    InheritRecord,
    SymbolRecord,
)
from src.core.extractors.treesitter.base import (
    language_for_path,
    parser_for_path,
    run_query,
)

_QUERY_DIR = Path(__file__).parent / "queries" / "rust"
SYMBOLS_QUERY = (_QUERY_DIR / "symbols.scm").read_text(encoding="utf-8")
IMPORTS_QUERY = (_QUERY_DIR / "imports.scm").read_text(encoding="utf-8")
CALLS_QUERY = (_QUERY_DIR / "calls.scm").read_text(encoding="utf-8")
MACROS_QUERY = (_QUERY_DIR / "macros.scm").read_text(encoding="utf-8")

_ITEM_KINDS = {
    "struct_item": "STRUCT",
    "enum_item": "ENUM",
    "trait_item": "TRAIT",
    "function_item": "FUNCTION",  # refined to METHOD by container context
}


def _classify(node: Node) -> Optional[Tuple[str, Node]]:
    kind = _ITEM_KINDS.get(node.type)
    if kind is None:
        return None
    name = node.child_by_field_name("name")
    return (kind, name) if name is not None else None


def _text(node: Optional[Node]) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _type_name_text(node: Optional[Node]) -> str:
    """Bare type name from an impl `type`/`trait` field, unwrapping
    `generic_type` (`Container<T>` -> `Container`) and
    `scoped_type_identifier` (`crate::foo::Bar` -> `Bar`, since only the
    bare name is meaningful for symbol_path/lookup purposes — the
    qualifying path is resolved separately, the same way TS unwraps
    `generic_type` for base-class names)."""
    if node is None:
        return ""
    if node.type == "generic_type":
        inner = node.child_by_field_name("type")
        return _type_name_text(inner) if inner is not None else _text(node)
    if node.type == "scoped_type_identifier":
        name = node.child_by_field_name("name")
        return _text(name) if name is not None else _text(node)
    if node.type == "reference_type":
        inner = node.child_by_field_name("type")
        return _type_name_text(inner) if inner is not None else _text(node)
    return _text(node)


def _container_of(node: Node) -> Tuple[str, Optional[str]]:
    """Where a symbol-candidate node structurally lives:
    ("top", None) — file scope, or (v1) inside an inline `mod` block;
    ("impl", type_name) — a `function_item` directly inside an
        `impl_item`'s body (becomes a METHOD on `type_name`);
    ("trait_skip", None) — inside a `trait_item`'s body (v1: not
        extracted — mirrors TS's interface-member-skip precedent);
    ("skip", None) — nested inside anything else (a `block`, i.e. a
        locally-defined item inside a function body) — not a symbol.
    """
    parent = node.parent
    if parent is None or parent.type == "source_file":
        return ("top", None)
    if parent.type == "declaration_list":
        grandparent = parent.parent
        if grandparent is None:
            return ("skip", None)
        if grandparent.type == "impl_item":
            type_node = grandparent.child_by_field_name("type")
            return ("impl", _type_name_text(type_node))
        if grandparent.type == "trait_item":
            return ("trait_skip", None)
        if grandparent.type == "mod_item":
            return ("top", None)  # v1: inline `mod` is transparent
        return ("skip", None)
    return ("skip", None)


class RustExtractor:
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        self.doc_type = "rust source"
        stem = relative_path.rsplit("/", 1)[-1]
        if stem.endswith(".rs"):
            stem = stem[: -len(".rs")]
        self.module_name = stem
        self._macro_counts: Dict[Optional[int], int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, source_code: str) -> ExtractionResult:
        tree = self._parse(source_code)
        language = language_for_path(self.relative_path)

        self._macro_counts = {}

        symbol_nodes = self._sorted_captures(language, SYMBOLS_QUERY, tree.root_node)
        call_nodes = self._sorted_captures(language, CALLS_QUERY, tree.root_node)
        use_nodes = self._sorted_captures(language, IMPORTS_QUERY, tree.root_node)
        macro_nodes = self._sorted_captures(language, MACROS_QUERY, tree.root_node)

        self._count_macro_invocations(macro_nodes, symbol_nodes)

        symbols = self._build_symbols(source_code, symbol_nodes)
        imports = self._build_imports(use_nodes)
        calls = self._build_calls(call_nodes)
        inherits = self._build_inherits(symbol_nodes)

        return ExtractionResult(
            symbols=symbols, imports=imports, calls=calls, inherits=inherits
        )

    def _parse(self, source_code: str):
        parser = parser_for_path(self.relative_path)
        tree = parser.parse(source_code.encode("utf-8"))
        if tree.root_node.has_error:
            raise ValueError(f"tree-sitter parse errors in {self.relative_path}")
        return tree

    def _sorted_captures(self, language, query_source: str, root: Node) -> List[Node]:
        captures = run_query(language, query_source, root)
        return sorted(captures.get("node", []), key=lambda n: n.start_byte)

    # ------------------------------------------------------------------
    # Macro-invocation counting (metadata only — bodies never inspected)
    # ------------------------------------------------------------------

    def _owner_key(self, node: Node) -> Optional[int]:
        """The nearest enclosing extracted symbol's node id (for
        macro-count attribution), or None if at module scope. Distinct
        from _container_of: this walks up to the nearest FUNCTION/METHOD
        regardless of what's in between (a macro can be nested arbitrarily
        deep inside expressions/blocks)."""
        current = node.parent
        while current is not None:
            if current.type == "function_item":
                container, _ = _container_of(current)
                if container in ("top", "impl"):
                    return current.id
            current = current.parent
        return None

    def _count_macro_invocations(
        self, macro_nodes: List[Node], symbol_nodes: List[Node]
    ) -> None:
        for node in macro_nodes:
            key = self._owner_key(node)
            self._macro_counts[key] = self._macro_counts.get(key, 0) + 1

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    def _build_symbols(
        self, source_code: str, symbol_nodes: List[Node]
    ) -> List[SymbolRecord]:
        symbols: List[SymbolRecord] = [self._module_symbol(source_code)]
        for node in symbol_nodes:
            if node.type in ("impl_item", "mod_item"):
                continue  # transparent containers, never symbols themselves
            classification = _classify(node)
            if classification is None:
                continue
            kind, name_node = classification
            container, impl_type = _container_of(node)
            if container == "skip" or container == "trait_skip":
                continue
            if kind == "FUNCTION" and container == "impl":
                kind = "METHOD"
            symbols.append(
                self._lower_symbol(node, kind, name_node, impl_type)
            )
        return symbols

    def _module_symbol(self, source_code: str) -> SymbolRecord:
        metadata: Dict[str, object] = {"doc_type": self.doc_type}
        count = self._macro_counts.get(None, 0)
        if count:
            metadata["macro_invocations"] = count
        return SymbolRecord(
            kind="MODULE",
            name=self.module_name,
            symbol_path=None,
            parent_symbol_path=None,
            span=None,
            text=source_code,
            metadata=metadata,
        )

    def _lower_symbol(
        self,
        node: Node,
        kind: str,
        name_node: Node,
        impl_type: Optional[str],
    ) -> SymbolRecord:
        name = _text(name_node)
        symbol_path = f"{impl_type}.{name}" if impl_type else name
        parent_symbol_path = impl_type  # None for top-level items
        lineno = node.start_point.row + 1
        end_lineno = node.end_point.row + 1
        metadata: Dict[str, object] = {
            "lineno": lineno,
            "col_offset": node.start_point.column,
            "doc_type": self.doc_type,
        }
        if kind == "METHOD":
            metadata["impl_target"] = impl_type
        count = self._macro_counts.get(node.id, 0)
        if count:
            metadata["macro_invocations"] = count
        return SymbolRecord(
            kind=kind,
            name=name,
            symbol_path=symbol_path,
            parent_symbol_path=parent_symbol_path,
            span=(lineno, end_lineno),
            text=_text(node),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Inherits: `impl Trait for Type`
    # ------------------------------------------------------------------

    def _build_inherits(self, symbol_nodes: List[Node]) -> List[InheritRecord]:
        records: List[InheritRecord] = []
        for node in symbol_nodes:
            if node.type != "impl_item":
                continue
            trait_node = node.child_by_field_name("trait")
            type_node = node.child_by_field_name("type")
            if trait_node is None or type_node is None:
                continue  # plain inherent `impl Type { ... }` — no trait
            records.append(
                InheritRecord(
                    child_symbol_path=_type_name_text(type_node),
                    parent_name=_type_name_text(trait_node),
                    kind="TRAIT_IMPL",
                    metadata={
                        "lineno": node.start_point.row + 1,
                        "col_offset": node.start_point.column,
                    },
                )
            )
        return records

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _enclosing_impl_type(self, node: Node) -> Optional[str]:
        current = node.parent
        while current is not None:
            if current.type == "impl_item":
                return _type_name_text(current.child_by_field_name("type"))
            current = current.parent
        return None

    def _enclosing_caller_symbol_path(self, node: Node) -> Optional[str]:
        current = node.parent
        while current is not None:
            if current.type == "function_item":
                container, impl_type = _container_of(current)
                if container in ("top", "impl"):
                    name_node = current.child_by_field_name("name")
                    name = _text(name_node)
                    return f"{impl_type}.{name}" if impl_type else name
            current = current.parent
        return None

    def _lower_call(self, node: Node) -> Optional[CallSite]:
        fn = node.child_by_field_name("function")
        if fn is None:
            return None

        if fn.type == "identifier":
            name = _text(fn)
            receiver = None
        elif fn.type == "field_expression":
            field = fn.child_by_field_name("field")
            if field is None:
                return None
            name = _text(field)
            value = fn.child_by_field_name("value")
            receiver = _text(value) if value is not None else None
        elif fn.type == "scoped_identifier":
            name_node = fn.child_by_field_name("name")
            path_node = fn.child_by_field_name("path")
            if name_node is None:
                return None
            name = _text(name_node)
            receiver = _text(path_node).replace("::", ".") if path_node else None
        else:
            return None

        if receiver == "Self":
            # Capital-S associated-function syntax: rewrite to the actual
            # enclosing impl target's type name so GraphAssembler never
            # needs a "Self" special case (v1 design decision, module
            # docstring).
            receiver = self._enclosing_impl_type(node) or receiver

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
    # Imports: `use` declarations
    # ------------------------------------------------------------------

    def _resolved_prefix(
        self, path_node: Optional[Node], prefix: List[str]
    ) -> List[str]:
        """The flat segment list a `path` field resolves to, or `prefix`
        unchanged if there's nothing to resolve — shared by every
        `use`-subtree node type below that has a nested `path` field."""
        if path_node is None:
            return prefix
        sub = self._collect_use_paths(path_node, prefix)
        return sub[0][0] if sub else prefix

    def _collect_use_leaf(
        self, node: Node, prefix: List[str]
    ) -> List[Tuple[List[str], Optional[str]]]:
        return [(prefix + [_text(node)], None)]

    def _collect_use_scoped_identifier(
        self, node: Node, prefix: List[str]
    ) -> List[Tuple[List[str], Optional[str]]]:
        base_prefix = self._resolved_prefix(node.child_by_field_name("path"), prefix)
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return [(base_prefix + [_text(name_node)], None)]
        return [(base_prefix, None)]

    def _collect_use_as_clause(
        self, node: Node, prefix: List[str]
    ) -> List[Tuple[List[str], Optional[str]]]:
        path_node = node.child_by_field_name("path")
        if path_node is None:
            return []
        alias_node = node.child_by_field_name("alias")
        alias = _text(alias_node) if alias_node is not None else None
        sub = self._collect_use_paths(path_node, prefix)
        return [(segs, alias) for segs, _ in sub]

    def _collect_use_scoped_list(
        self, node: Node, prefix: List[str]
    ) -> List[Tuple[List[str], Optional[str]]]:
        base_prefix = self._resolved_prefix(node.child_by_field_name("path"), prefix)
        list_node = node.child_by_field_name("list")
        if list_node is None:
            return []
        return self._collect_use_paths(list_node, base_prefix)

    def _collect_use_list(
        self, node: Node, prefix: List[str]
    ) -> List[Tuple[List[str], Optional[str]]]:
        results: List[Tuple[List[str], Optional[str]]] = []
        for child in node.named_children:
            results.extend(self._collect_use_paths(child, prefix))
        return results

    def _collect_use_wildcard(
        self, node: Node, prefix: List[str]
    ) -> List[Tuple[List[str], Optional[str]]]:
        path_node = node.child_by_field_name("path")
        if path_node is None and node.named_children:
            path_node = node.named_children[0]
        base_prefix = self._resolved_prefix(path_node, prefix)
        # `use foo::*;` — best-effort: recorded as a literal `*` segment,
        # unresolved (v1, mirrors TS's `export * from` treatment).
        return [(base_prefix + ["*"], None)]

    _USE_LEAF_TYPES = ("identifier", "type_identifier", "crate", "self", "super")

    def _collect_use_paths(
        self, node: Node, prefix: List[str]
    ) -> List[Tuple[List[str], Optional[str]]]:
        """Flatten one `use` argument subtree into (full_segments, alias)
        pairs. Handles plain paths, `as` aliasing, grouped `{a, b}`
        lists (nested one level, matching real-world usage), and
        best-effort wildcards — dispatches by node type to the
        `_collect_use_*` helpers above."""
        if node.type in self._USE_LEAF_TYPES:
            return self._collect_use_leaf(node, prefix)
        handler = {
            "scoped_identifier": self._collect_use_scoped_identifier,
            "use_as_clause": self._collect_use_as_clause,
            "scoped_use_list": self._collect_use_scoped_list,
            "use_list": self._collect_use_list,
            "use_wildcard": self._collect_use_wildcard,
        }.get(node.type)
        return handler(node, prefix) if handler else []

    def _use_level_and_module(
        self, segments: List[str]
    ) -> Tuple[int, str, str]:
        """(level, module, imported_name) per the level scheme documented
        in RustModuleConvention.absolute_import_base: 0=bare/external,
        1=`crate::`, 2=`self::`, N>=3=`super::` repeated (N-2) times."""
        if not segments:
            return (0, "", "")
        if len(segments) == 1:
            return (0, "", segments[0])

        head = segments[0]
        if head == "crate":
            rest = segments[1:]
            return (1, ".".join(rest[:-1]), rest[-1])
        if head == "self":
            rest = segments[1:]
            return (2, ".".join(rest[:-1]), rest[-1])
        if head == "super":
            supers = 0
            i = 0
            while i < len(segments) and segments[i] == "super":
                supers += 1
                i += 1
            rest = segments[i:]
            if not rest:
                return (2 + supers, "", "")
            return (2 + supers, ".".join(rest[:-1]), rest[-1])

        # bare: external crate, or a same-named local workspace crate
        return (0, ".".join(segments[:-1]), segments[-1])

    def _lower_use(self, decl_node: Node) -> List[ImportRecord]:
        argument = decl_node.child_by_field_name("argument")
        if argument is None:
            return []
        paths = self._collect_use_paths(argument, [])
        lineno = decl_node.start_point.row + 1
        records: List[ImportRecord] = []
        for segments, alias in paths:
            level, module, imported_name = self._use_level_and_module(segments)
            if not imported_name:
                continue
            metadata: Dict[str, object] = {
                "col_offset": decl_node.start_point.column,
                "doc_type": self.doc_type,
            }
            if level == 0 and not module:
                # True plain import (`use plain_crate;`): the imported
                # name IS the module itself (Python's `import X` shape).
                # imported_name stays None so GraphAssembler's "module"
                # not in meta branch does a direct module_map lookup by
                # name, instead of a from-X-import-Y lookup — critically,
                # this is NOT the same as a qualified import whose
                # resolved `module` happens to be empty (crate root
                # itself, e.g. `use crate::Animal;` — module="",
                # imported_name="Animal" — collapsing that case into this
                # branch would silently break crate-root symbol imports).
                records.append(
                    ImportRecord(
                        raw_module=imported_name,
                        imported_name=None,
                        alias=alias,
                        parent_symbol_path=None,
                        span=(lineno, lineno),
                        metadata=metadata,
                    )
                )
                continue
            metadata["level"] = level
            records.append(
                ImportRecord(
                    raw_module=module,
                    imported_name=imported_name,
                    alias=alias,
                    parent_symbol_path=None,  # `use` is always module-scoped
                    span=(lineno, lineno),
                    metadata=metadata,
                )
            )
        return records

    def _build_imports(self, use_nodes: List[Node]) -> List[ImportRecord]:
        imports: List[ImportRecord] = []
        for node in use_nodes:
            imports.extend(self._lower_use(node))
        return imports
