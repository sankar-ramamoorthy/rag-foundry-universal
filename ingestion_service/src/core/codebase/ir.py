# ingestion_service/src/core/codebase/ir.py
"""
Language-agnostic intermediate representation (WP-L1,
DOCS/audit/03-Multi-Language-Graph-Plan.md §2). Every extractor emits
an ExtractionResult; GraphAssembler is the only thing that resolves
identity, imports, calls, and inheritance — it never inspects a
language's own syntax tree.

InheritRecord exists for extractors where a base/trait reference isn't
naturally expressed as class metadata (e.g. Rust's `impl Trait for
Type`, WP-L3). The current Python extractor keeps base-class strings on
SymbolRecord.metadata["bases"] instead — GraphAssembler's inheritance
resolution reads that shape today; InheritRecord is unused until a
future extractor needs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SymbolRecord:
    kind: str  # MODULE|CLASS|FUNCTION|METHOD|IMPORT|... (extractor-defined)
    name: str
    symbol_path: Optional[str]  # None for MODULE; dot-separated otherwise
    parent_symbol_path: Optional[str]  # None if the parent is the module itself
    span: Optional[Tuple[int, int]]  # (lineno, end_lineno)
    text: str
    signature: Optional[str] = None
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportRecord:
    raw_module: str  # dotted module path as written (relative-import
                      # base is resolved by ModulePathConvention, not here)
    imported_name: Optional[str]  # None for `import X`; symbol for `from X import Y`
    alias: Optional[str]  # the `as` binding, if any
    parent_symbol_path: Optional[str]
    span: Optional[Tuple[int, int]]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallSite:
    callee_name: str
    receiver: Optional[str]
    caller_symbol_path: Optional[str]  # None if the call is at module scope
    span: Optional[Tuple[int, int]]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InheritRecord:
    child_symbol_path: str
    parent_name: str  # unresolved name/path text
    kind: str  # EXTENDS|IMPLEMENTS|TRAIT_IMPL
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    """Everything one extractor produces for one file."""
    symbols: List[SymbolRecord]
    imports: List[ImportRecord] = field(default_factory=list)
    calls: List[CallSite] = field(default_factory=list)
    inherits: List[InheritRecord] = field(default_factory=list)
