# ingestion_service/tests/codebase/test_python_repo_graph_golden.py
"""
WP-L5 golden-file + determinism tests over the checked-in fixture repos
(issue #134 acceptance criteria), mirroring test_java_repo_graph_golden.py's
pattern.

Two fixtures, deliberately kept SEPARATE (see test_python_parity_harness.py
for why):
- tests/fixtures/python_repo_valid/ — every file parses cleanly under both
  PythonASTExtractor and PythonTreeSitterExtractor. This file asserts the
  exact node/edge inventory produced when PYTHON_TREESITTER_ENABLED=True,
  covering: package/subpackage MODULEs, a cross-module `from .movable
  import Movable` + inheritance producing INHERITS/OVERRIDES, a
  cross-module `from .util.helpers import calc` call, and a bare
  `Animal()` construction call.
- tests/fixtures/python_repo_syntax_error/ — one file with a deliberate
  syntax error. Asserts PythonTreeSitterExtractor's partial-extraction
  improvement (symbols outside the broken region are still extracted)
  directly, as an independent expectation — NOT diffed against AST's
  skip-the-file behavior.
"""
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.config import reset_settings_cache

pytestmark = pytest.mark.unit

VALID_FIXTURE_ROOT = (
    Path(__file__).resolve().parent.parent / "fixtures" / "python_repo_valid"
)
SYNTAX_ERROR_FIXTURE_ROOT = (
    Path(__file__).resolve().parent.parent / "fixtures" / "python_repo_syntax_error"
)

_ANIMAL = "pkg/animal.py#Animal"
_MOVABLE = "pkg/movable.py#Movable"
_CALLER = "pkg/caller.py#run"
_CALC = "pkg/util/helpers.py#calc"


@pytest.fixture
def treesitter_enabled(monkeypatch):
    """Forces the tree-sitter Python extractor on (via
    _PythonExtractorProxy) with auto-fallback disabled, so a crash in the
    extractor fails the test loudly rather than silently masking a bug
    with the AST result."""
    monkeypatch.setenv("PYTHON_TREESITTER_ENABLED", "true")
    monkeypatch.setenv("PYTHON_TREESITTER_AUTO_FALLBACK", "false")
    reset_settings_cache()
    yield
    reset_settings_cache()


def _build(fixture_root: Path):
    builder = RepoGraphBuilder(fixture_root, ingestion_id=uuid4())
    return builder.build()


def _entity_inventory(graph):
    return sorted((e["artifact_type"], e["canonical_id"]) for e in graph.all_entities())


def _relationship_inventory(graph):
    return sorted(
        (r["relation_type"], r["from_canonical_id"], r["to_canonical_id"])
        for r in graph.relationships
    )


EXPECTED_ENTITIES = sorted([
    ("CLASS", _ANIMAL),
    ("CLASS", _MOVABLE),
    ("EXTERNAL_SYMBOL", "EXTERNAL_SYMBOL:a.describe"),
    ("FUNCTION", _CALLER),
    ("FUNCTION", _CALC),
    ("IMPORT", "pkg/animal.py#import:movable.Movable"),
    ("IMPORT", "pkg/animal.py#import:util.helpers.calc"),
    ("IMPORT", "pkg/caller.py#import:animal.Animal"),
    ("METHOD", f"{_ANIMAL}.describe"),
    ("METHOD", f"{_ANIMAL}.move_to"),
    ("METHOD", f"{_ANIMAL}.scaled"),
    ("METHOD", f"{_ANIMAL}.speak"),
    ("METHOD", f"{_MOVABLE}.move_to"),
    ("MODULE", "pkg/__init__.py"),
    ("MODULE", "pkg/animal.py"),
    ("MODULE", "pkg/caller.py"),
    ("MODULE", "pkg/movable.py"),
    ("MODULE", "pkg/util/__init__.py"),
    ("MODULE", "pkg/util/helpers.py"),
])

EXPECTED_RELATIONSHIPS = sorted([
    ("CALL", f"{_ANIMAL}.describe", f"{_ANIMAL}.speak"),
    ("CALL", f"{_ANIMAL}.move_to", f"{_ANIMAL}.speak"),
    ("CALL", f"{_ANIMAL}.scaled", _CALC),
    ("CALL", _CALLER, "EXTERNAL_SYMBOL:a.describe"),
    ("CALL", _CALLER, _ANIMAL),
    ("DEFINES", "pkg/animal.py", _ANIMAL),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.describe"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.move_to"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.scaled"),
    ("DEFINES", _ANIMAL, f"{_ANIMAL}.speak"),
    ("DEFINES", "pkg/caller.py", _CALLER),
    ("DEFINES", "pkg/movable.py", _MOVABLE),
    ("DEFINES", _MOVABLE, f"{_MOVABLE}.move_to"),
    ("DEFINES", "pkg/util/helpers.py", _CALC),
    ("IMPORTS", "pkg/animal.py", "pkg/movable.py"),
    ("IMPORTS", "pkg/animal.py", "pkg/util/helpers.py"),
    ("IMPORTS", "pkg/caller.py", "pkg/animal.py"),
    ("INHERITS", _ANIMAL, _MOVABLE),
    ("OVERRIDES", f"{_ANIMAL}.move_to", f"{_MOVABLE}.move_to"),
])


def test_golden_entity_inventory(treesitter_enabled):
    graph = _build(VALID_FIXTURE_ROOT)
    assert _entity_inventory(graph) == EXPECTED_ENTITIES


def test_golden_relationship_inventory(treesitter_enabled):
    graph = _build(VALID_FIXTURE_ROOT)
    assert _relationship_inventory(graph) == EXPECTED_RELATIONSHIPS


def test_cross_module_import_and_call_resolve(treesitter_enabled):
    graph = _build(VALID_FIXTURE_ROOT)
    rels = _relationship_inventory(graph)
    assert ("CALL", f"{_ANIMAL}.scaled", _CALC) in rels
    assert ("IMPORTS", "pkg/animal.py", "pkg/util/helpers.py") in rels


def test_inheritance_produces_inherits_and_overrides(treesitter_enabled):
    graph = _build(VALID_FIXTURE_ROOT)
    rels = _relationship_inventory(graph)
    assert ("INHERITS", _ANIMAL, _MOVABLE) in rels
    assert ("OVERRIDES", f"{_ANIMAL}.move_to", f"{_MOVABLE}.move_to") in rels


def test_rebuild_determinism(treesitter_enabled):
    """ADR-036: re-running ingestion on the unchanged fixture twice
    produces byte-identical node/edge sets under tree-sitter, exactly as
    it does under ast."""
    first = _build(VALID_FIXTURE_ROOT)
    second = _build(VALID_FIXTURE_ROOT)
    assert _entity_inventory(first) == _entity_inventory(second)
    assert _relationship_inventory(first) == _relationship_inventory(second)


def test_syntax_error_file_yields_partial_extraction(treesitter_enabled):
    """Acceptance criterion: a file with a syntax error yields partial
    artifacts (symbols outside the broken region) instead of a full file
    skip — a deliberate improvement over PythonASTExtractor's behavior,
    NOT a parity assertion against it (see module docstring)."""
    graph = _build(SYNTAX_ERROR_FIXTURE_ROOT)
    ids = [e["canonical_id"] for e in graph.all_entities()]
    assert "pkg/broken.py#good_before" in ids
    assert "pkg/broken.py#good_after" in ids


def test_syntax_error_file_ast_extractor_skips_whole_file():
    """Documents PythonASTExtractor's existing (unchanged) behavior on the
    same fixture, for contrast with the tree-sitter test above — this is
    the behavior WP-L5 improves on, not something it must preserve."""
    graph = _build(SYNTAX_ERROR_FIXTURE_ROOT)
    ids = [e["canonical_id"] for e in graph.all_entities()]
    assert "pkg/broken.py#good_before" not in ids
    assert "pkg/broken.py#good_after" not in ids
