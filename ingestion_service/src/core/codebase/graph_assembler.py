# ingestion_service/src/core/codebase/graph_assembler.py
"""
GraphAssembler (WP-L1, DOCS/audit/03-Multi-Language-Graph-Plan.md §2/§3
WP-L1). The single, language-agnostic pass that turns every extractor's
ExtractionResult into identity-assigned entities and relationships:

    IR (SymbolRecord/ImportRecord/CallSite) -> identity -> DEFINES ->
    IMPORTS -> INHERITS/OVERRIDES -> CALL -> DOCUMENTS

This is the exact resolution logic that used to live inline in
RepoGraphBuilder (WP-G2 through WP-G5, IS8) — moved here unchanged in
behavior, parameterized by a per-language ModulePathConvention instead
of hard-coding Python's file->module rules. It has zero imports from
`ast` or any tree-sitter module: every input is already IR.
"""
from __future__ import annotations

from collections import deque
import logging
import re
from typing import Dict, List, Optional, Tuple

from src.core.codebase.identity import build_canonical_id
from src.core.codebase.ir import CallSite, ExtractionResult, ImportRecord, SymbolRecord
from src.core.codebase.module_conventions import ModulePathConvention
from src.core.codebase.repo_graph import RepoGraph
from src.core.codebase.symbol_table import build_symbol_table

logger = logging.getLogger(__name__)

# IS8: code artifact types eligible for DOCUMENTS relationships
# WP-L2: INTERFACE (TS/JS) is documentable the same way CLASS is.
DOCUMENTABLE_TYPES = {"CLASS", "INTERFACE", "FUNCTION", "METHOD", "MODULE"}

# WP-L2: nodes eligible for INHERITS resolution (extends/implements)  and
# for OVERRIDES's base-hierarchy walk. CLASS-only under WP-L1 (Python has
# no interface-like kind); TS/JS interfaces extend other interfaces and
# classes implement them, so both kinds participate identically.
INHERITABLE_TYPES = {"CLASS", "INTERFACE"}

# F-04: receivers that are plain dotted names keep their context in
# EXTERNAL_SYMBOL ids; anything else (subscripts, call results) doesn't.
_DOTTED_NAME = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")


class GraphAssembler:
    def __init__(self, module_convention: ModulePathConvention):
        self.module_convention = module_convention

    def assemble(
        self,
        repo_root,
        ingestion_id: str,
        extracted_files: List[Tuple[str, ExtractionResult]],
    ) -> RepoGraph:
        graph = RepoGraph(repo_root, ingestion_id)

        for relative_path, result in extracted_files:
            for sym in result.symbols:
                graph.add_entity(
                    relative_path,
                    self._lower_symbol(relative_path, sym, ingestion_id),
                )
            for imp in result.imports:
                graph.add_entity(
                    relative_path,
                    self._lower_import(relative_path, imp, ingestion_id),
                )
            for cs in result.calls:
                graph.call_sites.append(self._lower_call_site(relative_path, cs))

        symbol_table = build_symbol_table(graph)
        self._attach_defines(graph)
        self._resolve_imports(graph)                    # WP-G2 — before calls
        self._resolve_inheritance(graph, symbol_table)   # WP-G5 — before calls
        self._resolve_calls(graph, symbol_table)
        self._link_docs_to_code(graph, symbol_table)     # IS8 — last step

        return graph

    # -----------------------------
    # IR -> entity/call-site lowering (identity assignment)
    # -----------------------------

    def _lower_symbol(
        self, relative_path: str, sym: SymbolRecord, ingestion_id
    ) -> dict:
        canonical_id = build_canonical_id(relative_path, sym.symbol_path)
        parent_id = (
            build_canonical_id(relative_path, sym.parent_symbol_path)
            if sym.symbol_path is not None
            else None  # MODULE has no parent
        )
        metadata = {k: v for k, v in sym.metadata.items() if k != "doc_type"}
        return {
            "artifact_type": sym.kind,
            "id": canonical_id,
            "canonical_id": canonical_id,
            "name": sym.name,
            "parent_id": parent_id,
            "relative_path": relative_path,
            "ingestion_id": ingestion_id,
            "title": sym.name or "Untitled",
            "doc_type": sym.metadata.get("doc_type", "unknown"),
            "text": sym.text,
            "metadata": metadata,
            "defines": [],
        }

    def _lower_import(
        self, relative_path: str, imp: ImportRecord, ingestion_id
    ) -> dict:
        name = imp.imported_name if imp.imported_name is not None else imp.raw_module
        symbol_path = (
            f"import:{imp.raw_module}.{imp.imported_name}"
            if imp.imported_name is not None
            else f"import:{imp.raw_module}"
        )
        canonical_id = build_canonical_id(relative_path, symbol_path)
        parent_id = (
            build_canonical_id(relative_path, imp.parent_symbol_path)
            if imp.parent_symbol_path is not None
            else relative_path
        )
        lineno = imp.span[0] if imp.span else None
        metadata: Dict[str, object] = {"asname": imp.alias}
        if imp.imported_name is not None:
            metadata["module"] = imp.raw_module
            metadata["level"] = imp.metadata.get("level", 0)
        metadata["lineno"] = lineno
        metadata["col_offset"] = imp.metadata.get("col_offset")
        return {
            "artifact_type": "IMPORT",
            "id": canonical_id,
            "canonical_id": canonical_id,
            "name": name,
            "parent_id": parent_id,
            "relative_path": relative_path,
            "ingestion_id": ingestion_id,
            "title": name,
            "doc_type": imp.metadata.get("doc_type", "unknown"),
            "text": "",
            "metadata": metadata,
            "defines": [],
        }

    def _lower_call_site(self, relative_path: str, cs: CallSite) -> dict:
        caller_id = (
            build_canonical_id(relative_path, cs.caller_symbol_path)
            if cs.caller_symbol_path is not None
            else relative_path
        )
        lineno = cs.span[0] if cs.span else None
        return {
            "name": cs.callee_name,
            "receiver": cs.receiver,
            "parent_id": caller_id,
            "relative_path": relative_path,
            "lineno": lineno,
            "col_offset": cs.metadata.get("col_offset"),
        }

    # -----------------------------
    # DEFINES Relationships
    # -----------------------------

    def _attach_defines(self, graph: RepoGraph):
        definition_types = {
            "CLASS", "INTERFACE", "FUNCTION", "METHOD",
            "MARKDOWN_SECTION",
        }

        for entity in graph.all_entities():
            if entity.get("artifact_type") not in definition_types:
                continue

            parent_id = entity.get("parent_id")
            if not parent_id:
                continue

            parent_cid = self._canonical_from_id(graph, parent_id)
            parent = graph.get_entity(parent_cid) if parent_cid else None
            if not parent:
                continue

            graph.add_relationship({
                "from_canonical_id": parent["canonical_id"],
                "to_canonical_id": entity["canonical_id"],
                "relation_type": "DEFINES",
                "relationship_metadata": {}
            })

    # -----------------------------
    # WP-G2: IMPORTS Relationships
    # -----------------------------

    def _resolve_imports(self, graph: RepoGraph) -> None:
        """Materialize MODULE --IMPORTS--> MODULE edges from IMPORT
        artifacts. Intra-repo imports resolve against the dotted-module
        map; external imports get one EXTERNAL_MODULE node per root
        package. Also records per-file import bindings for call
        resolution (ADR-032 layer 2)."""
        module_map: dict[str, str] = {}
        for entity in graph.all_entities():
            if entity.get("artifact_type") != "MODULE":
                continue
            dotted = self.module_convention.dotted_path(entity["canonical_id"])
            if dotted:
                module_map[dotted] = entity["canonical_id"]

        imports = sorted(
            (
                e for e in graph.all_entities()
                if e.get("artifact_type") == "IMPORT"
            ),
            key=lambda e: (
                e.get("relative_path", ""),
                e.get("metadata", {}).get("lineno", 0),
                e.get("metadata", {}).get("col_offset", 0),
                e.get("name", ""),
            ),
        )

        # (from_cid, to_cid) -> [[imported_name, asname], ...]
        edges: dict = {}

        for imp in imports:
            rel = imp.get("relative_path", "")
            if rel not in graph.entities:
                continue  # MODULE canonical id == relative path (ADR-031)

            name = imp.get("name", "")
            asname = imp.get("metadata", {}).get("asname")

            target_cid, binding = self._resolve_import_target(
                graph, imp, module_map
            )
            # `import pkg.util` binds the dotted path as written at call
            # sites (`pkg.util.calc()`); an asname replaces it.
            bindings = graph.import_bindings.setdefault(rel, {})
            bindings[asname or name] = binding

            if target_cid == rel:
                continue  # a module importing itself is never an edge

            edges.setdefault((rel, target_cid), []).append(
                [name, asname]
            )

        for (from_cid, to_cid) in sorted(edges):
            pairs = sorted(
                edges[(from_cid, to_cid)],
                key=lambda p: (p[0], p[1] or ""),
            )
            graph.add_relationship({
                "from_canonical_id": from_cid,
                "to_canonical_id": to_cid,
                "relation_type": "IMPORTS",
                "relationship_metadata": {
                    "imports": pairs,
                    "count": len(pairs),
                },
            })

    def _resolve_import_target(
        self, graph: RepoGraph, imp: dict, module_map: dict
    ) -> Tuple[str, dict]:
        """Resolve one IMPORT artifact to (target canonical id, binding).

        ImportFrom tries `base.name` as a module first (`from pkg import
        util`), then `base` as the module the symbol lives in; plain
        Import tries the dotted name directly. Misses become one
        EXTERNAL_MODULE per root package.
        """
        meta = imp.get("metadata", {})
        name = imp.get("name", "")
        rel = imp.get("relative_path", "")

        if "module" not in meta:  # `import X[.Y]`
            if name in module_map:
                return module_map[name], {
                    "kind": "module", "module_cid": module_map[name],
                }
            root = name.split(".")[0]
            return self._external_module_node(graph, root), {
                "kind": "external_module", "dotted": name,
            }

        # `from X import name`
        dotted_base = self.module_convention.absolute_import_base(
            rel, meta.get("module", ""), meta.get("level", 0) or 0
        )
        as_module = f"{dotted_base}.{name}" if dotted_base else name

        if as_module in module_map:
            # the imported name is itself a module
            return module_map[as_module], {
                "kind": "module", "module_cid": module_map[as_module],
            }
        if dotted_base in module_map:
            return module_map[dotted_base], {
                "kind": "symbol",
                "module_cid": module_map[dotted_base],
                "symbol": name,
            }
        root = (dotted_base or name).split(".")[0]
        return self._external_module_node(graph, root), {
            "kind": "external_symbol", "dotted": as_module,
        }

    def _external_module_node(self, graph: RepoGraph, root: str) -> str:
        """Get or create the single EXTERNAL_MODULE node for an external
        root package (`numpy`, not `numpy.linalg`). Persisted with empty
        text so it is never embedded (ADR-039)."""
        canonical_id = f"EXTERNAL_MODULE:{root}"
        if canonical_id not in graph.entities:
            graph.add_entity("", {
                "artifact_type": "EXTERNAL_MODULE",
                "id": canonical_id,
                "canonical_id": canonical_id,
                "name": root,
                "title": root,
                "doc_type": "external",
                "relative_path": "",
                "text": "",
                "metadata": {},
                "ingestion_id": graph.ingestion_id,
                "defines": [],
            })
        return canonical_id

    # -----------------------------
    # WP-G5: INHERITS / OVERRIDES Relationships
    # -----------------------------

    def _resolve_inheritance(self, graph: RepoGraph, symbol_table) -> None:
        """WP-G5: materialize the class hierarchy.

        For each CLASS or INTERFACE (WP-L2: TS/JS interfaces extend other
        interfaces and classes implement them, resolved identically),
        resolve its `metadata.bases` strings through the same machinery as
        call resolution (same-file → imports → unique-global →
        EXTERNAL_SYMBOL) and emit CLASS|INTERFACE --INHERITS-->
        CLASS|INTERFACE|EXTERNAL_SYMBOL edges. Then, for each METHOD
        redefining a name that exists on the nearest resolved ancestor,
        emit METHOD --OVERRIDES--> base METHOD. Also records
        graph.class_bases so `self.x()`/`this.x()` resolution can fall back
        to inherited methods (ADR-032 step 1 extension)."""
        classes = sorted(
            (
                e for e in graph.all_entities()
                if e.get("artifact_type") in INHERITABLE_TYPES
            ),
            key=lambda e: e["canonical_id"],
        )

        # (from_cid, to_cid) -> {"bases": [strings], "confidence": float}
        edges: dict = {}
        for cls in classes:
            rel = cls.get("relative_path", "")
            for base_str in cls.get("metadata", {}).get("bases", []):
                target_id, confidence = self._resolve_base(
                    graph, symbol_table, rel, base_str
                )
                target = graph.get_entity_by_id(target_id)
                if not target or target["id"] == cls["id"]:
                    continue

                if target.get("artifact_type") in INHERITABLE_TYPES:
                    bases = graph.class_bases.setdefault(cls["id"], [])
                    if target["id"] not in bases:
                        bases.append(target["id"])

                key = (cls["canonical_id"], target["canonical_id"])
                record = edges.setdefault(
                    key, {"bases": [], "confidence": confidence}
                )
                record["bases"].append(base_str)
                record["confidence"] = max(record["confidence"], confidence)

        for (from_cid, to_cid) in sorted(edges):
            record = edges[(from_cid, to_cid)]
            graph.add_relationship({
                "from_canonical_id": from_cid,
                "to_canonical_id": to_cid,
                "relation_type": "INHERITS",
                "relationship_metadata": {
                    "bases": record["bases"],
                    "confidence": record["confidence"],
                },
            })

        self._emit_overrides(graph, classes)

    def _emit_overrides(self, graph: RepoGraph, classes: list) -> None:
        """METHOD --OVERRIDES--> base METHOD for each method whose name is
        defined on the nearest resolved intra-repo ancestor class."""
        methods_by_class: dict = {}
        for entity in graph.all_entities():
            if entity.get("artifact_type") == "METHOD":
                methods_by_class.setdefault(
                    entity.get("parent_id"), []
                ).append(entity)

        for cls in classes:
            if cls["id"] not in graph.class_bases:
                continue
            methods = sorted(
                methods_by_class.get(cls["id"], []),
                key=lambda m: m["canonical_id"],
            )
            for method in methods:
                base_method_id = self._lookup_method_in_hierarchy(
                    graph, cls["id"], method["name"], include_self=False
                )
                if not base_method_id:
                    continue
                base_method = graph.get_entity_by_id(base_method_id)
                if not base_method:
                    continue
                graph.add_relationship({
                    "from_canonical_id": method["canonical_id"],
                    "to_canonical_id": base_method["canonical_id"],
                    "relation_type": "OVERRIDES",
                    "relationship_metadata": {
                        "method_name": method["name"],
                    },
                })

    def _resolve_base(
        self, graph: RepoGraph, symbol_table, rel: str, base_str: str
    ) -> Tuple[str, float]:
        """Resolve one base-class expression to an entity id.

        Subscripts are stripped (`Generic[T]` → `Generic`) so typed bases
        resolve to the generic class. Order mirrors ADR-032: same-file →
        import binding → unique-global → EXTERNAL_SYMBOL."""
        name = base_str.split("[", 1)[0].strip()

        if not _DOTTED_NAME.match(name):
            # dynamic bases (call results, subscript-only) fold into an
            # external symbol carrying the raw expression
            return self._external_symbol_node(graph, name or base_str), 0.0

        if "." in name:
            receiver, attr = name.rsplit(".", 1)
            binding = graph.import_bindings.get(rel, {}).get(receiver)
            if binding:
                return self._resolve_via_binding(
                    graph, symbol_table, binding, attr
                )
            local_receiver = symbol_table.lookup_in_file(rel, receiver)
            if local_receiver:
                candidate = f"{local_receiver}.{attr}"
                if graph.get_entity_by_id(candidate):
                    return candidate, 1.0
            return self._external_symbol_node(graph, name), 0.0

        local = symbol_table.lookup_in_file(rel, name)
        if local:
            return local, 1.0

        binding = graph.import_bindings.get(rel, {}).get(name)
        if binding:
            return self._resolve_via_binding(graph, symbol_table, binding, None)

        candidates = symbol_table.lookup_global(name)
        if len(candidates) == 1:
            return candidates[0], 0.5

        return self._external_symbol_node(graph, name), 0.0

    def _lookup_method_in_hierarchy(
        self,
        graph: RepoGraph,
        class_id: str,
        method_name: str,
        include_self: bool = True,
    ) -> Optional[str]:
        """Find `method_name` on class_id or its resolved intra-repo
        ancestors (BFS in base-declaration order, cycle-guarded). Returns
        the method entity id of the nearest definition, or None."""
        initial = (
            [class_id] if include_self
            else list(graph.class_bases.get(class_id, []))
        )
        queue = deque(initial)
        seen = {class_id, *initial}
        while queue:
            current = queue.popleft()
            candidate = f"{current}.{method_name}"
            if graph.get_entity_by_id(candidate):
                return candidate
            for base_id in graph.class_bases.get(current, []):
                if base_id not in seen:
                    seen.add(base_id)
                    queue.append(base_id)
        return None

    # -----------------------------
    # CALL Relationships
    # -----------------------------

    def _resolve_calls(self, graph: RepoGraph, symbol_table):
        """F-03 (WP-G3): consume call-site evidence records and emit one
        aggregated CALL edge per caller→callee pair. Multiple sites of the
        same pair land in metadata (call_sites linenos + count) instead of
        colliding on a shared canonical id."""
        # (from_cid, to_cid) -> {"linenos": [...], "confidence": float}
        edges: dict = {}

        for site in sorted(
            graph.call_sites,
            key=lambda s: (
                s["relative_path"], s["lineno"], s.get("col_offset") or 0,
            ),
        ):
            caller_parent_id = site.get("parent_id")
            if not caller_parent_id:
                continue

            caller_cid = self._canonical_from_id(graph, caller_parent_id)
            caller_parent = (
                graph.get_entity(caller_cid) if caller_cid else None
            )
            if not caller_parent:
                continue

            resolution, confidence = self._resolve_call_site(
                site, graph, symbol_table
            )
            if not resolution:
                continue

            target_cid = self._canonical_from_id(graph, resolution)
            target = graph.get_entity(target_cid) if target_cid else None
            if not target:
                continue

            key = (caller_parent["canonical_id"], target["canonical_id"])
            record = edges.setdefault(
                key, {"linenos": [], "confidence": confidence}
            )
            record["linenos"].append(site["lineno"])
            record["confidence"] = max(record["confidence"], confidence)

        for (from_cid, to_cid) in sorted(edges):
            record = edges[(from_cid, to_cid)]
            graph.add_relationship({
                "from_canonical_id": from_cid,
                "to_canonical_id": to_cid,
                "relation_type": "CALL",
                "relationship_metadata": {
                    "confidence": record["confidence"],
                    "call_sites": record["linenos"],
                    "count": len(record["linenos"]),
                },
            })

    def _resolve_call_site(
        self, site: dict, graph: RepoGraph, symbol_table
    ) -> Tuple[Optional[str], float]:
        """F-04 (WP-G4): resolve one call site per ADR-032's order:
        (1) receiver `self`/`cls`/`this` (WP-L2: TS/JS's own-instance
        receiver, same structural meaning) → enclosing class's methods;
        (2) bare name → same-file symbols;
        (3) name/receiver imported in this file → target module's symbol;
        (4) global index, only if unambiguous;
        (5) else an EXTERNAL_SYMBOL node — never silently dropped.

        Confidence: 1.0 scoped/import-resolved, 0.5 unique-global,
        0.0 external/unknown. Confidence lives in edge metadata, never
        in identity (ADR-031)."""
        name = site.get("name") or ""
        receiver = site.get("receiver")

        if receiver in ("self", "cls", "this"):
            class_id = self._enclosing_class_id(site, graph)
            if class_id:
                # WP-G5: fall back through resolved base classes so a
                # method defined only on the base still resolves.
                candidate = self._lookup_method_in_hierarchy(
                    graph, class_id, name
                )
                if candidate:
                    return candidate, 1.0
            return (
                self._external_symbol_node(graph, f"{receiver}.{name}"),
                0.0,
            )

        if receiver is None:
            return self._resolve_bare_call(site, graph, symbol_table)

        return self._resolve_attribute_call(site, graph, symbol_table)

    def _resolve_bare_call(
        self, site: dict, graph: RepoGraph, symbol_table
    ) -> Tuple[str, float]:
        name = site.get("name") or ""
        rel = site.get("relative_path", "")

        local = symbol_table.lookup_in_file(rel, name)
        if local:
            return local, 1.0

        binding = graph.import_bindings.get(rel, {}).get(name)
        if binding:
            return self._resolve_via_binding(
                graph, symbol_table, binding, None
            )

        candidates = symbol_table.lookup_global(name)
        if len(candidates) == 1:
            return candidates[0], 0.5

        # zero candidates (unknown/builtin) or >1 (ambiguous): surface
        # as external instead of guessing an arbitrary winner.
        return self._external_symbol_node(graph, name), 0.0

    def _resolve_attribute_call(
        self, site: dict, graph: RepoGraph, symbol_table
    ) -> Tuple[str, float]:
        name = site.get("name") or ""
        receiver = site.get("receiver") or ""
        rel = site.get("relative_path", "")

        binding = graph.import_bindings.get(rel, {}).get(receiver)
        if binding:
            return self._resolve_via_binding(
                graph, symbol_table, binding, name
            )

        # receiver may be a class in the same file: `Calculator.add()`
        local_receiver = symbol_table.lookup_in_file(rel, receiver)
        if local_receiver:
            candidate = f"{local_receiver}.{name}"
            if graph.get_entity_by_id(candidate):
                return candidate, 1.0

        # dynamic receivers (`items[0].strip()`, `get_db().query`) fold
        # into the bare method name; dotted-name receivers keep context.
        external_name = (
            f"{receiver}.{name}"
            if _DOTTED_NAME.match(receiver)
            else name
        )
        return self._external_symbol_node(graph, external_name), 0.0

    def _resolve_via_binding(
        self, graph: RepoGraph, symbol_table, binding: dict, attr: Optional[str]
    ) -> Tuple[str, float]:
        """Resolve a call through an import binding (ADR-032 layer 2).
        `attr` is None for `calc()` where calc itself was imported, or
        the called attribute for `utils.calc()` / `numpy.array()`."""
        kind = binding["kind"]

        if kind == "module":
            module_cid = binding["module_cid"]
            dotted = self.module_convention.dotted_path(module_cid) or module_cid
            if attr is None:
                # calling a module object — nothing to resolve to
                return self._external_symbol_node(graph, dotted), 0.0
            target = symbol_table.lookup_in_file(module_cid, attr)
            if target:
                return target, 1.0
            return (
                self._external_symbol_node(graph, f"{dotted}.{attr}"),
                0.0,
            )

        if kind == "symbol":
            module_cid = binding["module_cid"]
            symbol = binding["symbol"]
            target = symbol_table.lookup_in_file(module_cid, symbol)
            if attr is None:
                if target:
                    return target, 1.0
            elif target:
                # imported class used as receiver: `Calculator.add()`
                candidate = f"{target}.{attr}"
                if graph.get_entity_by_id(candidate):
                    return candidate, 1.0
            dotted = self.module_convention.dotted_path(module_cid) or module_cid
            external = f"{dotted}.{symbol}" + (f".{attr}" if attr else "")
            return self._external_symbol_node(graph, external), 0.0

        # external_module / external_symbol
        external = binding["dotted"] + (f".{attr}" if attr else "")
        return self._external_symbol_node(graph, external), 0.0

    def _enclosing_class_id(
        self, site: dict, graph: RepoGraph
    ) -> Optional[str]:
        """Nearest enclosing CLASS of a call site (via the parent chain)."""
        current = site.get("parent_id")
        while current:
            entity = graph.get_entity_by_id(current)
            if entity is None:
                return None
            if entity.get("artifact_type") == "CLASS":
                return entity.get("id")
            current = entity.get("parent_id")
        return None

    def _external_symbol_node(self, graph: RepoGraph, dotted: str) -> str:
        """Get or create the EXTERNAL_SYMBOL node for an unresolved
        callee (`requests.get`, `print`). Empty text — never embedded."""
        canonical_id = f"EXTERNAL_SYMBOL:{dotted}"
        if canonical_id not in graph.entities:
            graph.add_entity("", {
                "artifact_type": "EXTERNAL_SYMBOL",
                "id": canonical_id,
                "canonical_id": canonical_id,
                "name": dotted,
                "title": dotted,
                "doc_type": "external",
                "relative_path": "",
                "text": "",
                "metadata": {},
                "ingestion_id": graph.ingestion_id,
                "defines": [],
            })
        return canonical_id

    # -----------------------------
    # IS8: DOCUMENTS Relationships
    # Markdown sections → code symbols (exact name match)
    # -----------------------------

    def _link_docs_to_code(self, graph: RepoGraph, symbol_table) -> None:
        """
        IS8: Create DOCUMENTS relationships from MARKDOWN_SECTION nodes
        to the code symbols they document.

        Strategy: exact name match via symbol table.
        Deterministic, no LLM, rebuild-safe (ADR-048).

        Only runs within repo ingestion — uploaded files are out of scope.
        """
        linked = 0
        skipped = 0

        for entity in graph.all_entities():
            if entity.get("artifact_type") != "MARKDOWN_SECTION":
                continue

            # Raw heading text e.g. "add", "Calculator", "run_demo"
            section_name = entity.get("name", "").strip()
            if not section_name:
                continue

            # Normalise: lowercase, strip whitespace
            normalised = section_name.lower().strip()

            # Try original casing first, then normalised lowercase
            target_canonical = symbol_table.lookup(section_name) or \
                            symbol_table.lookup(normalised)

            if not target_canonical:
                skipped += 1
                continue

            # Verify target is a documentable code artifact
            target = graph.get_entity(target_canonical)
            if not target:
                skipped += 1
                continue

            if target.get("artifact_type") not in DOCUMENTABLE_TYPES:
                skipped += 1
                continue

            # Don't link a section to itself (shouldn't happen but guard)
            if entity["canonical_id"] == target["canonical_id"]:
                skipped += 1
                continue

            graph.add_relationship({
                "from_canonical_id": entity["canonical_id"],
                "to_canonical_id": target["canonical_id"],
                "relation_type": "DOCUMENTS",
                "relationship_metadata": {
                    "match_strategy": "exact_name",
                    "section_name": section_name,
                    "confidence": 1.0,
                },
            })

            logger.debug(
                "IS8: DOCUMENTS link: %s → %s",
                entity["canonical_id"],
                target["canonical_id"],
            )
            linked += 1

        logger.info(
            "IS8: _link_docs_to_code complete — %d DOCUMENTS links created, "
            "%d sections skipped (no match)",
            linked, skipped,
        )

    # -----------------------------
    # Helpers
    # -----------------------------

    def _canonical_from_id(
        self, graph: RepoGraph, entity_id: str
    ) -> Optional[str]:
        entity = graph.get_entity_by_id(entity_id)
        return entity.get("canonical_id") if entity else None
