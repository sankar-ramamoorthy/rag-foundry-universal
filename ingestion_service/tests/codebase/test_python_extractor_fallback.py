# ingestion_service/tests/codebase/test_python_extractor_fallback.py
"""
WP-L5 rollback verification (DOCS/audit/03-Multi-Language-Graph-Plan.md
WP-L5 section, issue #134): proves _PythonExtractorProxy's automatic
crash-only fallback actually works and is gated by
PYTHON_TREESITTER_AUTO_FALLBACK — the "roll it back without a code
revert" mechanism.

This tests the fallback's narrow job only (catching a raised exception).
It intentionally does NOT prove semantic equivalence between the two
extractors — that's test_python_parity_harness.py's job, run with
PYTHON_TREESITTER_AUTO_FALLBACK=False specifically so this kind of
fallback can't mask a real bug there.
"""
import logging

import pytest

from src.core.codebase.repo_graph_builder import _PythonExtractorProxy
from src.core.config import reset_settings_cache

pytestmark = pytest.mark.unit

REL_PATH = "pkg/mod.py"


@pytest.fixture(autouse=True)
def _reset_settings():
    yield
    reset_settings_cache()


def test_auto_fallback_recovers_from_treesitter_exception(monkeypatch, caplog):
    monkeypatch.setenv("PYTHON_TREESITTER_ENABLED", "true")
    monkeypatch.setenv("PYTHON_TREESITTER_AUTO_FALLBACK", "true")
    reset_settings_cache()

    def _boom(self, source_code):
        raise RuntimeError("simulated tree-sitter extractor crash")

    monkeypatch.setattr(
        "src.core.codebase.repo_graph_builder.PythonTreeSitterExtractor.extract",
        _boom,
    )

    proxy = _PythonExtractorProxy(relative_path=REL_PATH)
    with caplog.at_level(logging.WARNING):
        result = proxy.extract("x = 1\n")

    assert result is not None
    assert any(s.kind == "MODULE" for s in result.symbols)
    assert any(
        "PYTHON_TREESITTER_AUTO_FALLBACK" in record.message
        for record in caplog.records
    )


def test_auto_fallback_disabled_lets_exception_propagate(monkeypatch):
    monkeypatch.setenv("PYTHON_TREESITTER_ENABLED", "true")
    monkeypatch.setenv("PYTHON_TREESITTER_AUTO_FALLBACK", "false")
    reset_settings_cache()

    def _boom(self, source_code):
        raise RuntimeError("simulated tree-sitter extractor crash")

    monkeypatch.setattr(
        "src.core.codebase.repo_graph_builder.PythonTreeSitterExtractor.extract",
        _boom,
    )

    proxy = _PythonExtractorProxy(relative_path=REL_PATH)
    with pytest.raises(RuntimeError, match="simulated tree-sitter extractor crash"):
        proxy.extract("x = 1\n")


def test_disabled_flag_uses_ast_extractor_directly(monkeypatch):
    """The manual rollback lever: PYTHON_TREESITTER_ENABLED=False routes
    straight to PythonASTExtractor, no tree-sitter involved at all — the
    "no code revert, just flip a flag" guarantee."""
    monkeypatch.setenv("PYTHON_TREESITTER_ENABLED", "false")
    reset_settings_cache()

    def _boom(self, source_code):
        raise RuntimeError("tree-sitter should never even be called")

    monkeypatch.setattr(
        "src.core.codebase.repo_graph_builder.PythonTreeSitterExtractor.extract",
        _boom,
    )

    proxy = _PythonExtractorProxy(relative_path=REL_PATH)
    result = proxy.extract("x = 1\n")
    assert any(s.kind == "MODULE" for s in result.symbols)
