# ingestion_service/src/core/codebase/module_conventions.py
"""
ModulePathConvention: how one language maps file paths to importable
module names (WP-L1, DOCS/audit/03-Multi-Language-Graph-Plan.md §2).
GraphAssembler is parameterized by one of these instead of hard-coding
Python's rules, so a future language only needs its own convention, not
changes to import resolution itself.
"""
from __future__ import annotations

import posixpath
from typing import Dict, Optional, Protocol


class ModulePathConvention(Protocol):
    def dotted_path(self, relative_path: str) -> Optional[str]:
        """`pkg/util.py` -> `pkg.util`, or None if not a module file."""
        ...

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        """Resolve a possibly-relative import base to an absolute
        dotted path. `level` is the language's relative-import depth
        (0 = already absolute)."""
        ...


class PythonModuleConvention:
    def dotted_path(self, relative_path: str) -> Optional[str]:
        if not relative_path.endswith(".py"):
            return None
        parts = relative_path[:-3].split("/")
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        if not level:
            return base
        pkg_parts = relative_path.split("/")[:-1]
        drop = level - 1
        pkg_parts = pkg_parts[: len(pkg_parts) - drop] if drop else pkg_parts
        if base:
            pkg_parts = pkg_parts + base.split(".")
        return ".".join(pkg_parts)


_TS_MODULE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


class TypeScriptModuleConvention:
    """WP-L2: relative-path-based module identity for TS/JS. Unlike
    Python's dotted names, the map keys here are extension-less,
    index-collapsed, slash-separated relative paths (`src/util.ts` ->
    `src/util`, `src/sub/index.ts` -> `src/sub`) — GraphAssembler's import
    resolution never assumes a dot-separated key shape, only exact-string
    matches on whatever dotted_path() returns (DOCS/audit/
    03-Multi-Language-Graph-Plan.md §3 WP-L2 research)."""

    def dotted_path(self, relative_path: str) -> Optional[str]:
        if not relative_path.endswith(_TS_MODULE_SUFFIXES):
            return None
        return self._collapse(relative_path)

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        # `level` has no meaning for TS/JS relative specifiers (no
        # dot-counted relative-import depth) — resolution is entirely
        # driven by whether `base` itself starts with "." / "..".
        if not base.startswith("."):
            return base  # bare specifier: left as-is for the external-
                          # module fallback in GraphAssembler
        base_dir = posixpath.dirname(relative_path)
        joined = posixpath.normpath(posixpath.join(base_dir, base))
        joined = joined.replace("\\", "/")
        return self._collapse(joined, has_suffix=False)

    def _collapse(self, path: str, has_suffix: bool = True) -> str:
        stripped = path
        if has_suffix:
            for suffix in _TS_MODULE_SUFFIXES:
                if stripped.endswith(suffix):
                    stripped = stripped[: -len(suffix)]
                    break
        parts = stripped.split("/")
        if parts and parts[-1] == "index":
            parts = parts[:-1]
        return "/".join(parts) if parts else stripped


class CompositeModuleConvention:
    """WP-L2: dispatches to a per-suffix ModulePathConvention so one repo
    can mix languages (e.g. Python + TypeScript) in a single ingestion run
    without either language's import resolution corrupting the other's
    module map (DOCS/audit/03-Multi-Language-Graph-Plan.md §3 WP-L2 —
    the necessary, additive alternative to WP-L1's single hardcoded
    PythonModuleConvention)."""

    def __init__(self, by_suffix: Dict[str, ModulePathConvention]):
        self._by_suffix = by_suffix

    def _convention_for(self, relative_path: str) -> Optional[ModulePathConvention]:
        for suffix, convention in self._by_suffix.items():
            if relative_path.endswith(suffix):
                return convention
        return None

    def dotted_path(self, relative_path: str) -> Optional[str]:
        convention = self._convention_for(relative_path)
        return convention.dotted_path(relative_path) if convention else None

    def absolute_import_base(
        self, relative_path: str, base: str, level: int
    ) -> str:
        convention = self._convention_for(relative_path)
        if convention is None:
            return base
        return convention.absolute_import_base(relative_path, base, level)
