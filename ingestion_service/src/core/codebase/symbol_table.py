## ingestion_service\src\core\codebase\symbol_table.py
"""
src/core/codebase/symbol_table.py

SymbolTable

Builds a repository-wide mapping:

    symbol_name -> canonical_id

Phase 1 scope:
- CLASS
- FUNCTION
- METHOD

This is a global flat symbol index.
Later phases may extend to scoped or multi-binding resolution.
"""
from __future__ import annotations  # Python 3.7+ feature
#to try and avoid circular reference
#from src.core.codebase.repo_graph_builder import RepoGraph

from typing import Dict


class SymbolTable:
    """
    Global symbol table for repository artifacts.

    Maps:
        symbol_name -> canonical_id
    """

    def __init__(self):
        self._symbols: Dict[str, str] = {}

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def add(self, symbol_name: str, canonical_id: str):
        """
        Register a symbol in the table.

        If duplicate symbol exists, last definition wins.
        (Phase 1 simplification — deterministic but not scoped.)
        """
        self._symbols[symbol_name] = canonical_id

    def lookup(self, symbol_name: str) -> str | None:
        """
        Retrieve canonical_id for a symbol.
        """
        return self._symbols.get(symbol_name)

    def all_symbols(self) -> Dict[str, str]:
        return dict(self._symbols)


# ----------------------------------------------------------------
# Builder Function
# ----------------------------------------------------------------

def build_symbol_table(graph: RepoGraph) -> SymbolTable:
    """
    Build a SymbolTable from a RepoGraph.

    Indexes:
        CLASS
        FUNCTION
        METHOD
    """

    table = SymbolTable()

    for entity in graph.all_entities():
        artifact_type = entity.get("artifact_type")

        if artifact_type in {"CLASS", "FUNCTION", "METHOD"}:
            name = entity.get("name")
            canonical_id = entity.get("id")

            if isinstance(name, str) and isinstance(canonical_id, str):
                table.add(name, canonical_id)


    return table
