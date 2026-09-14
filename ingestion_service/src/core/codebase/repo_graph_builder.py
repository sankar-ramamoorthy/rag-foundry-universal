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
import re

from src.core.codebase.graph_assembler import GraphAssembler
from src.core.codebase.ir import ExtractionResult
from src.core.codebase.module_conventions import (
    CompositeModuleConvention,
    JavaModuleConvention,
    PythonModuleConvention,
    RustModuleConvention,
    TypeScriptModuleConvention,
)
from src.core.codebase.repo_graph import RepoGraph
from src.core.extractors.python_extractor import PythonASTExtractor
from src.core.extractors.markdown_extractor import MarkdownSectionExtractor
from src.core.extractors.treesitter.java import JavaExtractor
from src.core.extractors.treesitter.rust import RustExtractor
from src.core.extractors.treesitter.typescript import TypeScriptExtractor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Registry pattern (WP-L1 acceptance criterion): a new language extractor
# is added here, by suffix — nothing else in this file or in
# GraphAssembler needs to change. (WP-L2: the one necessary exception is
# module-convention selection below, since TS/JS needs a different
# file-path -> module-name rule than Python's dotted-path convention.)
EXTRACTORS = {
    ".py": PythonASTExtractor,
    ".md": MarkdownSectionExtractor,
    ".ts": TypeScriptExtractor,
    ".tsx": TypeScriptExtractor,
    ".js": TypeScriptExtractor,
    ".jsx": TypeScriptExtractor,
    ".mjs": TypeScriptExtractor,
    ".cjs": TypeScriptExtractor,
    ".rs": RustExtractor,
    ".java": JavaExtractor,
}

_STATIC_MODULE_CONVENTIONS = {
    ".py": PythonModuleConvention(),
    ".ts": TypeScriptModuleConvention(),
    ".tsx": TypeScriptModuleConvention(),
    ".js": TypeScriptModuleConvention(),
    ".jsx": TypeScriptModuleConvention(),
    ".mjs": TypeScriptModuleConvention(),
    ".cjs": TypeScriptModuleConvention(),
    # WP-L4: Java's package->directory convention is purely path-derivable
    # (like Python's), no repo-wide pre-scan needed — unlike Rust's
    # crate-aware convention below, this can live in the static dict.
    ".java": JavaModuleConvention(),
}

# WP-L2: per-suffix module-naming convention dispatch, so a repo mixing
# Python and TS/JS resolves each language's imports correctly in one
# ingestion run (DOCS/audit/03-Multi-Language-Graph-Plan.md §3 WP-L2).
# WP-L3: kept as a static module-level default for non-Rust suffixes;
# RepoGraphBuilder.build() rebuilds a fresh CompositeModuleConvention per
# build with a Rust convention informed by that specific repo's crate
# layout (see _discover_crate_roots) — unlike Python/TS, Rust's `use
# crate::…`/`use super::…` resolution needs repo-wide crate-boundary
# knowledge that no single file's path can supply on its own.
_MODULE_CONVENTIONS = CompositeModuleConvention({
    **_STATIC_MODULE_CONVENTIONS,
    ".rs": RustModuleConvention(),
})

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


_CARGO_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.MULTILINE)


class RepoGraphBuilder:

    def __init__(self, repo_root: Path, ingestion_id: str):
        self.repo_root = repo_root
        self.ingestion_id = ingestion_id
        crate_roots = self._discover_crate_roots()
        if crate_roots:
            conventions = dict(_STATIC_MODULE_CONVENTIONS)
            conventions[".rs"] = RustModuleConvention(crate_roots)
            module_convention = CompositeModuleConvention(conventions)
        else:
            module_convention = _MODULE_CONVENTIONS
        self.assembler = GraphAssembler(module_convention=module_convention)

    def _discover_crate_roots(self) -> dict:
        """WP-L3: {crate_root_relative_dir: crate_name} for every
        Cargo.toml in the repo — multi-crate workspace support (plan
        doc's "treat each Cargo.toml dir as a namespace prefix"). Unlike
        Python/TS, Rust's `use crate::…`/`use super::…` resolution needs
        this repo-wide crate-boundary knowledge up front; a single file's
        own path can't supply it. Crate name is read from the manifest's
        `[package] name = "..."` line (best-effort regex, not a full TOML
        parse — v1 limitation, no `[workspace.package]` inheritance);
        falls back to the directory's own basename if absent/unparseable.
        Returns {} for repos with no Cargo.toml at all, in which case the
        static module-level _MODULE_CONVENTIONS default is used instead
        (RustModuleConvention() with no crate_roots falls back to an
        implicit single crate named "crate" — keeps Cargo.toml-less
        fixtures/repos working)."""
        crate_roots: dict[str, str] = {}
        for dirpath, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = sorted(
                d for d in dirnames
                if not d.startswith(".") and d not in DEFAULT_IGNORED_DIRS
            )
            if "Cargo.toml" not in filenames:
                continue
            try:
                rel_dir = Path(dirpath).relative_to(self.repo_root).as_posix()
            except Exception:
                continue
            rel_dir = "" if rel_dir == "." else rel_dir
            crate_name = Path(dirpath).name or "crate"
            try:
                text = (Path(dirpath) / "Cargo.toml").read_text(encoding="utf-8")
                match = _CARGO_NAME_RE.search(text)
                if match:
                    crate_name = match.group(1)
            except Exception:
                pass
            crate_roots[rel_dir] = crate_name
        return crate_roots

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
