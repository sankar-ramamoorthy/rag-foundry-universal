# ingestion_service/src/core/codebase/repo_graph_builder.py

from pathlib import Path
from typing import Optional, Tuple
import ast
import logging
import os
import re

from src.core.codebase.identity import build_global_id
from src.core.extractors.python_extractor import PythonASTExtractor
from src.core.codebase.repo_graph import RepoGraph
from src.core.codebase.symbol_table import build_symbol_table
from src.core.extractors.markdown_extractor import MarkdownSectionExtractor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# IS8: code artifact types eligible for DOCUMENTS relationships
DOCUMENTABLE_TYPES = {"CLASS", "FUNCTION", "METHOD", "MODULE"}

# F-16: directories that never contain first-party code worth ingesting.
# Dot-directories (.git, .venv, .tox, …) are excluded by a separate rule.
DEFAULT_IGNORED_DIRS = {
    "node_modules",
    "venv",
    "env",
    "build",
    "dist",
    "target",
    "vendor",
    "vendored",
    "__pycache__",
    "site-packages",
    "eggs",
}


# F-07: single-parse text extraction. These two helpers replicate
# ast.get_source_segment(padded=False) over pre-split lines, so each file's
# source is split once instead of once per artifact. Behavioral contract
# (verified by tests against ast.get_source_segment): lines split on
# \n / \r / \r\n only — NOT on form feed or other unicode breaks — and
# col_offset/end_col_offset are byte offsets into the UTF-8 encoded line.
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


class RepoGraphBuilder:

    def __init__(self, repo_root: Path, ingestion_id: str):
        self.repo_root = repo_root
        self.ingestion_id = ingestion_id

    def build(self) -> RepoGraph:
        graph = RepoGraph(self.repo_root, self.ingestion_id)

        for file_path in self._walk_repo():
            try:
                relative_path = file_path.relative_to(self.repo_root).as_posix()
            except Exception:
                continue

            extractor = self._select_extractor(file_path)
            if extractor is None:
                continue

            try:
                source = file_path.read_text(encoding="utf-8")
                artifacts = extractor.extract(source)
            except Exception:
                continue

            # F-07: parse the file once and index its AST nodes by line
            # number, instead of re-parsing per artifact.
            if file_path.suffix == ".py":
                line_nodes, source_lines = self._index_python_source(source)
            else:
                line_nodes, source_lines = {}, []

            for artifact in artifacts:
                artifact["relative_path"] = relative_path
                artifact["ingestion_id"] = self.ingestion_id
                artifact.setdefault("title", artifact.get("name", "Untitled"))
                if "doc_type" not in artifact:
                    artifact["doc_type"] = "python source"

                # IS1: fix canonical_id double filename
                artifact_id = artifact.get("id", "")
                if artifact_id.startswith(relative_path + "#"):
                    symbol_path = artifact_id[len(relative_path) + 1:]
                elif artifact_id == relative_path:
                    symbol_path = None  # MODULE node — no symbol
                else:
                    symbol_path = artifact_id  # fallback

                global_id = build_global_id(
                    self.ingestion_id,
                    relative_path,
                    symbol_path,
                )

                artifact["global_id"] = global_id
                artifact["canonical_id"] = global_id[1]
                artifact["text"] = self._extract_artifact_text(
                    source, artifact, line_nodes, source_lines
                )
                artifact["defines"] = []

                graph.add_entity(relative_path, artifact)

            # F-03: call sites travel outside the artifact list.
            graph.call_sites.extend(getattr(extractor, "call_sites", []))

        symbol_table = build_symbol_table(graph)
        self._attach_defines(graph)
        self._resolve_imports(graph)          # F-02 (WP-G2) — before calls
        self._resolve_calls(graph, symbol_table)
        self._link_docs_to_code(graph, symbol_table)   # IS8 — last step

        return graph

    # -----------------------------
    # DEFINES Relationships
    # -----------------------------

    def _attach_defines(self, graph: RepoGraph):
        definition_types = {
            "CLASS", "FUNCTION", "METHOD",
            "MARKDOWN_SECTION",
        }

        for entity in graph.all_entities():
            if entity.get("artifact_type") not in definition_types:
                continue

            parent_id = entity.get("parent_id")
            if not parent_id:
                continue

            parent = graph.get_entity(
                self._canonical_from_id(graph, parent_id)
            )
            if not parent:
                continue

            graph.add_relationship({
                "from_canonical_id": parent["canonical_id"],
                "to_canonical_id": entity["canonical_id"],
                "relation_type": "DEFINES",
                "relationship_metadata": {}
            })

    # -----------------------------
    # F-02 (WP-G2): IMPORTS Relationships
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
            dotted = self._dotted_module_path(entity["canonical_id"])
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
        dotted_base = self._absolute_import_base(
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

    def _dotted_module_path(self, relative_path: str) -> Optional[str]:
        """`pkg/util.py` → `pkg.util`; `pkg/__init__.py` → `pkg`."""
        if not relative_path.endswith(".py"):
            return None
        parts = relative_path[:-3].split("/")
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None

    def _absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        """Resolve an ImportFrom base to an absolute dotted path.
        level=0 → already absolute; level=n → n-1 packages above the
        importing file's package."""
        if not level:
            return base
        pkg_parts = relative_path.split("/")[:-1]
        drop = level - 1
        pkg_parts = pkg_parts[: len(pkg_parts) - drop] if drop else pkg_parts
        if base:
            pkg_parts = pkg_parts + base.split(".")
        return ".".join(pkg_parts)

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
                "ingestion_id": self.ingestion_id,
                "defines": [],
            })
        return canonical_id

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
            key=lambda s: (s["relative_path"], s["lineno"], s["col_offset"]),
        ):
            caller_parent_id = site.get("parent_id")
            if not caller_parent_id:
                continue

            caller_parent = graph.get_entity(
                self._canonical_from_id(graph, caller_parent_id)
            )
            if not caller_parent:
                continue

            resolution, confidence = self._resolve_call_site(
                site, graph, symbol_table
            )
            if not resolution:
                continue

            target = graph.get_entity(
                self._canonical_from_id(graph, resolution)
            )
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
        """Resolve one call site to an extractor-local entity id.

        F-03 keeps the pre-existing resolution semantics (enclosing-scope
        recursion match, then flat global symbol table) for receiver-less
        calls; receiver calls (`self.x()`, `obj.x()`) resolve in F-04.
        """
        if site.get("receiver") is not None:
            return None, 0.0

        resolution, confidence = self._resolve_in_scope(site, graph)
        if resolution:
            return resolution, confidence

        resolution = symbol_table.lookup(site.get("name") or "")
        if resolution:
            # symbol_table stores canonical ids; edge emission expects the
            # extractor-local id, which for code artifacts is identical.
            return resolution, 0.5

        return None, 0.0

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

    def _resolve_in_scope(
        self, site: dict, graph: RepoGraph
    ) -> Tuple[Optional[str], float]:
        """Recursion detection: an enclosing scope whose name matches the
        called name (works for both artifacts and call-site records)."""
        current_parent = site.get("parent_id")

        while current_parent:
            entity = graph.get_entity_by_id(current_parent)
            if entity is None:
                break
            if entity.get("name") == site.get("name"):
                return entity.get("id"), 1.0
            current_parent = entity.get("parent_id")

        return None, 0.0

    def _canonical_from_id(
        self, graph: RepoGraph, entity_id: str
    ) -> Optional[str]:
        entity = graph.get_entity_by_id(entity_id)
        return entity.get("canonical_id") if entity else None

    def _walk_repo(self):
        SUPPORTED = {".py", ".md"}
        for dirpath, dirnames, filenames in os.walk(self.repo_root):
            # Prune ignored directories in place so os.walk never descends
            # into them; sorted for deterministic traversal order (ADR-030).
            dirnames[:] = sorted(
                d for d in dirnames
                if not d.startswith(".") and d not in DEFAULT_IGNORED_DIRS
            )
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                path = Path(dirpath) / filename
                if path.suffix not in SUPPORTED:
                    continue
                yield path

    def _select_extractor(self, file_path: Path):
        rel = file_path.relative_to(self.repo_root).as_posix()
        if file_path.suffix == ".py":
            return PythonASTExtractor(relative_path=rel)
        if file_path.suffix == ".md":
            return MarkdownSectionExtractor(relative_path=rel)
        return None

    def _index_python_source(self, source: str):
        """F-07: parse a file once; map lineno → first AST node in walk
        order (matching the pre-refactor per-artifact scan), and pre-split
        the source lines for segment extraction."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}, []

        line_nodes: dict = {}
        for node in ast.walk(tree):
            if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                line_nodes.setdefault(node.lineno, node)
        return line_nodes, _splitlines_no_ff(source)

    def _extract_artifact_text(
        self,
        source: str,
        artifact: dict,
        line_nodes: dict,
        source_lines: list,
    ) -> str:
        # Markdown extractors pre-populate text — don't re-extract
        if artifact.get("text"):
            return artifact["text"]

        artifact_type = artifact.get("artifact_type")

        if artifact_type == "MODULE":
            return source

        if artifact_type in {"CLASS", "FUNCTION", "METHOD"}:
            lineno = artifact.get("metadata", {}).get("lineno")
            if lineno is None:
                return ""

            node = line_nodes.get(lineno)
            if node is not None:
                return _source_segment(source_lines, node) or ""

        return ""
