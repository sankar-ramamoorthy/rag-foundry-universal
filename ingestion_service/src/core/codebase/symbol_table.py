# ingestion_service\src\core\codebase\symbol_table.py
"""
src/core/codebase/symbol_table.py

SymbolTable — two-layer symbol index (F-04 / WP-G4, ADR-032).

Layers:
- per-file: relative_path -> symbol_name -> canonical_id
  (FUNCTION/CLASS shadow METHODs of the same bare name; ties resolve to
  the lexicographically smallest canonical id — deterministic.)
- global: symbol_name -> sorted list of canonical_ids
  (a list, so ambiguity is surfaced instead of last-write-wins.)

Indexed artifact types: CLASS, INTERFACE, FUNCTION, METHOD. (WP-L2:
INTERFACE added so TS/JS `implements`/`extends Interface` resolves to the
actual INTERFACE node instead of falling through to EXTERNAL_SYMBOL —
same priority tier as CLASS, since both are referable by bare name.)
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# FUNCTION/CLASS/INTERFACE are callable/referable by bare name; METHOD is
# not, so it only matches when nothing else in the file has the name.
_PRIORITY = {"CLASS": 0, "INTERFACE": 0, "FUNCTION": 0, "METHOD": 1}


class SymbolTable:
    """Two-layer symbol table for repository artifacts."""

    def __init__(self):
        # relative_path -> name -> (priority, canonical_id)
        self._per_file: Dict[str, Dict[str, Tuple[int, str]]] = {}
        # name -> list of canonical_ids (kept sorted on read)
        self._global: Dict[str, List[str]] = {}

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def add(
        self,
        symbol_name: str,
        canonical_id: str,
        relative_path: Optional[str] = None,
        artifact_type: str = "FUNCTION",
    ):
        """Register a symbol in both layers."""
        self._global.setdefault(symbol_name, []).append(canonical_id)

        if relative_path:
            candidate = (
                _PRIORITY.get(artifact_type, 1), canonical_id
            )
            bucket = self._per_file.setdefault(relative_path, {})
            existing = bucket.get(symbol_name)
            if existing is None or candidate < existing:
                bucket[symbol_name] = candidate

    def lookup(self, symbol_name: str) -> str | None:
        """Repo-wide lookup; ambiguous names resolve to the smallest
        canonical id (deterministic first match — ADR-048)."""
        bucket = self._global.get(symbol_name)
        return min(bucket) if bucket else None

    def lookup_in_file(
        self, relative_path: str, symbol_name: str
    ) -> Optional[str]:
        """Same-file lookup (ADR-032 resolution layer 1)."""
        entry = self._per_file.get(relative_path, {}).get(symbol_name)
        return entry[1] if entry else None

    def lookup_global(self, symbol_name: str) -> List[str]:
        """All bindings of a name across the repo, sorted. Callers use
        this only when unambiguous (len == 1) — ADR-032 layer 3."""
        return sorted(self._global.get(symbol_name, []))

    def all_symbols(self) -> Dict[str, str]:
        return {name: min(cids) for name, cids in self._global.items()}


# ----------------------------------------------------------------
# Builder Function
# ----------------------------------------------------------------

def build_symbol_table(graph) -> SymbolTable:
    """Build a SymbolTable from a RepoGraph (CLASS/INTERFACE/FUNCTION/METHOD)."""
    table = SymbolTable()

    for entity in graph.all_entities():
        artifact_type = entity.get("artifact_type")

        if artifact_type in {"CLASS", "INTERFACE", "FUNCTION", "METHOD"}:
            name = entity.get("name")
            canonical_id = entity.get("canonical_id")

            if isinstance(name, str) and isinstance(canonical_id, str):
                table.add(
                    name,
                    canonical_id,
                    relative_path=entity.get("relative_path"),
                    artifact_type=artifact_type,
                )

    return table
