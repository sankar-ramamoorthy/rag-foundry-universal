# ingestion_service/src/core/codebase/module_conventions.py
"""
ModulePathConvention: how one language maps file paths to importable
module names (WP-L1, DOCS/audit/03-Multi-Language-Graph-Plan.md §2).
GraphAssembler is parameterized by one of these instead of hard-coding
Python's rules, so a future language only needs its own convention, not
changes to import resolution itself.
"""
from __future__ import annotations

from typing import Optional, Protocol


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
