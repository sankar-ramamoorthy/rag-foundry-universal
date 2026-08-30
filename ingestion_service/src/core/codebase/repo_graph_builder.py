# ingestion_service/src/core/codebase/repo_graph_builder.py
"""
RepoGraphBuilder (WP-L1: thin orchestration only — DOCS/audit/
03-Multi-Language-Graph-Plan.md §3 WP-L1). Walks the repo, runs each
file through the registered extractor for its suffix, and hands the
accumulated IR to GraphAssembler. Adding a new language extractor means
adding one registry entry and one extractor file — nothing here or in
GraphAssembler changes.
"""

from pathlib import Path
import logging
import os

from src.core.codebase.graph_assembler import GraphAssembler
from src.core.codebase.ir import ExtractionResult
from src.core.codebase.module_conventions import PythonModuleConvention
from src.core.codebase.repo_graph import RepoGraph
from src.core.extractors.python_extractor import PythonASTExtractor
from src.core.extractors.markdown_extractor import MarkdownSectionExtractor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Registry pattern (WP-L1 acceptance criterion): a new language extractor
# is added here, by suffix — nothing else in this file or in
# GraphAssembler needs to change.
EXTRACTORS = {
    ".py": PythonASTExtractor,
    ".md": MarkdownSectionExtractor,
}

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


class RepoGraphBuilder:

    def __init__(self, repo_root: Path, ingestion_id: str):
        self.repo_root = repo_root
        self.ingestion_id = ingestion_id
        # Python is the only language today; the assembler takes a
        # per-language convention once suffix-based dispatch to more
        # than one convention is needed (WP-L2+).
        self.assembler = GraphAssembler(module_convention=PythonModuleConvention())

    def build(self) -> RepoGraph:
        extracted_files: list[tuple[str, ExtractionResult]] = []

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
                result = extractor.extract(source)
            except Exception:
                continue

            extracted_files.append((relative_path, result))

        return self.assembler.assemble(
            self.repo_root, self.ingestion_id, extracted_files
        )

    # -----------------------------
    # Helpers
    # -----------------------------

    def _walk_repo(self):
        supported = set(EXTRACTORS.keys())
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
                if path.suffix not in supported:
                    continue
                yield path

    def _select_extractor(self, file_path: Path):
        rel = file_path.relative_to(self.repo_root).as_posix()
        extractor_cls = EXTRACTORS.get(file_path.suffix)
        if extractor_cls is None:
            return None
        return extractor_cls(relative_path=rel)
