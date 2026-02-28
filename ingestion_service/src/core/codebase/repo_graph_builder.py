# ingestion_service/src/core/codebase/repo_graph_builder.py

from pathlib import Path
from typing import Optional, Tuple
import ast
import logging

from src.core.codebase.identity import build_global_id
from src.core.extractors.python_extractor import PythonASTExtractor
from src.core.codebase.repo_graph import RepoGraph
from src.core.codebase.symbol_table import build_symbol_table
from src.core.extractors.markdown_extractor import MarkdownSectionExtractor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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

            for artifact in artifacts:
                artifact["relative_path"] = relative_path
                artifact["ingestion_id"] = self.ingestion_id
                artifact.setdefault("title", artifact.get("name", "Untitled"))
                #artifact.setdefault("doc_type", "python source")
                if "doc_type" not in artifact:
                    artifact["doc_type"] = "python source"

                global_id = build_global_id(
                    self.ingestion_id,
                    relative_path,
                    artifact.get("id")
                )

                artifact["global_id"] = global_id
                artifact["canonical_id"] = global_id[1]
                artifact["text"] = self._extract_artifact_text(source, artifact)
                artifact["defines"] = []

                graph.add_entity(relative_path, artifact)

        symbol_table = build_symbol_table(graph)
        self._attach_defines(graph)
        self._resolve_calls(graph, symbol_table)

        return graph

    # -----------------------------
    # DEFINES Relationships
    # -----------------------------

    def _attach_defines(self, graph: RepoGraph):
        definition_types = {"CLASS", "FUNCTION", "METHOD",
                            "MARKDOWN_SECTION",}

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
    # CALL Relationships
    # -----------------------------

    def _resolve_calls(self, graph: RepoGraph, symbol_table):

        for call in self._calls(graph):
            caller_parent_id = call.get("parent_id")
            if not caller_parent_id:
                continue

            caller_parent = graph.get_entity(
                self._canonical_from_id(graph, caller_parent_id)
            )
            if not caller_parent:
                continue

            name = call.get("name") or ""

            resolution, confidence = self._resolve_in_scope(call, graph)

            if not resolution:
                resolution = symbol_table.lookup(name)
                confidence = 0.5 if resolution else 0.0

            if not resolution:
                continue  # Skip EXTERNAL for now

            target = graph.get_entity(
                self._canonical_from_id(graph, resolution)
            )
            if not target:
                continue

            graph.add_relationship({
                "from_canonical_id": caller_parent["canonical_id"],
                "to_canonical_id": target["canonical_id"],
                "relation_type": "CALL",
                "relationship_metadata": {"confidence": confidence}
            })

    # -----------------------------
    # Helpers
    # -----------------------------

    def _calls(self, graph: RepoGraph):
        for entity in graph.all_entities():
            if entity.get("artifact_type") == "CALL":
                yield entity

    def _resolve_in_scope(self, call: dict, graph: RepoGraph) -> Tuple[Optional[str], float]:
        current_parent = call.get("parent_id")

        while current_parent:
            for entity in graph.all_entities():
                if entity.get("id") == current_parent:
                    if entity.get("name") == call.get("name"):
                        return entity.get("id"), 1.0
                    current_parent = entity.get("parent_id")
                    break
            else:
                current_parent = None

        return None, 0.0

    def _canonical_from_id(self, graph: RepoGraph, entity_id: str) -> Optional[str]:
        for entity in graph.all_entities():
            if entity.get("id") == entity_id:
                return entity.get("canonical_id")
        return None

    def _walk_repo(self):
        SUPPORTED = {".py", ".md"}   # MS6-IS2: added .md
        for path in self.repo_root.rglob("*"):
            if path.suffix not in SUPPORTED:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            yield path

    def _select_extractor(self, file_path: Path):
        rel = file_path.relative_to(self.repo_root).as_posix()
        if file_path.suffix == ".py":
            #rel = file_path.relative_to(self.repo_root).as_posix()
            return PythonASTExtractor(relative_path=rel)
        if file_path.suffix == ".md":
            return MarkdownSectionExtractor(relative_path=rel)     
        return None

    def _extract_artifact_text(self, source: str, artifact: dict) -> str:
            #  Markdown extractors pre-populate text — don't re-extract
        if artifact.get("text"):
            return artifact["text"]
    
        artifact_type = artifact.get("artifact_type")

        if artifact_type == "MODULE":
            return source

        if artifact_type in {"CLASS", "FUNCTION", "METHOD"}:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                return ""

            lineno = artifact.get("metadata", {}).get("lineno")
            if lineno is None:
                return ""

            for node in ast.walk(tree):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    if node.lineno == lineno:
                        return ast.get_source_segment(source, node) or ""

        return ""
