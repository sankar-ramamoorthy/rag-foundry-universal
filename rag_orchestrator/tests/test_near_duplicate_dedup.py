# rag_orchestrator/tests/test_near_duplicate_dedup.py
"""
Issue #65: a module/root artifact with exactly one child covering (almost)
the same text produces near-duplicate embeddings — e.g. README.md's
markdown_module vs. its sole H1 markdown_section, or a single-class
module vs. that class. Both land in the seed candidate set competing for
the same top-k slots.

Covers `dedupe_near_identical_chunks()`: same-file near-duplicate pairs
collapse to the higher-scoring chunk; unrelated content, multi-child
modules, and cross-file matches are all left alone.
"""
import pytest

from rag_orchestrator.src.retrieval.codebase_utils import (
    dedupe_near_identical_chunks,
)
from rag_orchestrator.src.retrieval.types import RetrievedChunk

pytestmark = pytest.mark.unit


def _chunk(chunk_id, text, score, relative_path, canonical_id, document_id=None):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        text=text,
        score=score,
        metadata={"relative_path": relative_path, "canonical_id": canonical_id},
    )


README_TEXT = (
    "# smoke_repo\n\nThis fixture backs the live smoke test. "
    "It ingests a tiny repo and asks a handful of questions."
)


def test_module_and_sole_child_readme_collapses_to_higher_score():
    """README.md's markdown_module (whole file) vs. its only H1
    markdown_section (same text, since the H1 is the first line)."""
    module = _chunk("mod", README_TEXT, 0.81, "README.md", "README.md")
    section = _chunk(
        "sec", README_TEXT, 0.79, "README.md", "README.md#smoke_repo"
    )

    result = dedupe_near_identical_chunks([module, section])

    assert [c.chunk_id for c in result] == ["mod"]


def test_module_and_sole_class_collapses_to_higher_score():
    """shared/smoke_repo/animals.py: the whole file *is* the one Animal
    class (no imports, no other symbols), so MODULE.text == CLASS.text
    verbatim — exactly the issue #65 evidence."""
    class_text = (
        'class Animal:\n'
        '    """Base creature for the smoke-test menagerie."""\n\n'
        "    def speak(self):\n"
        '        return "generic noise"\n\n'
        "    def eat(self):\n"
        '        return "eating quietly"'
    )
    module = _chunk("mod", class_text, 0.5, "animals.py", "animals.py")
    cls = _chunk(
        "cls", class_text, 0.9, "animals.py", "animals.py#Animal"
    )

    result = dedupe_near_identical_chunks([module, cls])

    assert [c.chunk_id for c in result] == ["cls"]


def test_module_with_small_import_preamble_still_collapses():
    """A more general case than the smoke_repo fixture: a short import
    line before the sole child still leaves containment high enough
    (~93%) to count as a near-duplicate."""
    class_text = (
        'class Animal:\n'
        '    """Base creature for the smoke-test menagerie."""\n\n'
        "    def speak(self):\n"
        '        return "generic noise"\n\n'
        "    def eat(self):\n"
        '        return "eating quietly"'
    )
    module_text = "import os\n\n" + class_text
    module = _chunk("mod", module_text, 0.5, "animals.py", "animals.py")
    cls = _chunk("cls", class_text, 0.9, "animals.py", "animals.py#Animal")

    result = dedupe_near_identical_chunks([module, cls])

    assert [c.chunk_id for c in result] == ["cls"]


def test_module_with_large_preamble_is_not_deduped():
    """Enough distinct preamble content (beyond the sole child) means
    the module carries real information the child doesn't — containment
    drops below threshold, so both are kept rather than losing the
    preamble's context."""
    class_text = "class Animal:\n    def speak(self):\n        return 'noise'"
    module_text = "from __future__ import annotations\n\n" + class_text
    module = _chunk("mod", module_text, 0.5, "animals.py", "animals.py")
    cls = _chunk("cls", class_text, 0.9, "animals.py", "animals.py#Animal")

    result = dedupe_near_identical_chunks([module, cls])

    assert {c.chunk_id for c in result} == {"mod", "cls"}


def test_tie_break_prefers_deeper_canonical_id():
    module = _chunk("mod", README_TEXT, 0.5, "README.md", "README.md")
    section = _chunk(
        "sec", README_TEXT, 0.5, "README.md", "README.md#smoke_repo"
    )

    result = dedupe_near_identical_chunks([module, section])

    assert [c.chunk_id for c in result] == ["sec"]


def test_multi_child_module_is_not_deduped():
    """A module with several siblings isn't a near-duplicate of any one
    of them — only a fraction of its text is contained in each child."""
    module_text = "\n\n".join(
        f"def fn_{i}():\n    return {i}" for i in range(6)
    )
    module = _chunk("mod", module_text, 0.6, "kennel.py", "kennel.py")
    one_fn = _chunk(
        "fn0", "def fn_0():\n    return 0", 0.7, "kennel.py", "kennel.py#fn_0"
    )

    result = dedupe_near_identical_chunks([module, one_fn])

    assert {c.chunk_id for c in result} == {"mod", "fn0"}


def test_different_files_are_never_compared():
    a = _chunk("a", README_TEXT, 0.5, "README.md", "README.md")
    b = _chunk("b", README_TEXT, 0.9, "OTHER.md", "OTHER.md")

    result = dedupe_near_identical_chunks([a, b])

    assert {c.chunk_id for c in result} == {"a", "b"}


def test_unrelated_content_same_file_is_kept():
    a = _chunk("a", "def foo(): pass", 0.5, "kennel.py", "kennel.py#foo")
    b = _chunk("b", "def bar(): pass", 0.5, "kennel.py", "kennel.py#bar")

    result = dedupe_near_identical_chunks([a, b])

    assert {c.chunk_id for c in result} == {"a", "b"}


def test_sub_chunked_pairs_still_collapse():
    """Both artifacts split into two sub-chunks each (same chunker
    output for effectively-identical text) — matching sub-chunks pair
    up and collapse independently."""
    part1 = "# smoke_repo\n\nThis fixture backs the live smoke test."
    part2 = "It ingests a tiny repo and asks a handful of questions."

    mod0 = _chunk("mod0", part1, 0.81, "README.md", "README.md")
    mod1 = _chunk("mod1", part2, 0.80, "README.md", "README.md")
    sec0 = _chunk("sec0", part1, 0.79, "README.md", "README.md#smoke_repo")
    sec1 = _chunk("sec1", part2, 0.78, "README.md", "README.md#smoke_repo")

    result = dedupe_near_identical_chunks([mod0, mod1, sec0, sec1])

    assert {c.chunk_id for c in result} == {"mod0", "mod1"}


def test_missing_relative_path_is_never_deduped():
    a = _chunk("a", README_TEXT, 0.5, "", "x")
    b = _chunk("b", README_TEXT, 0.9, "", "y")

    result = dedupe_near_identical_chunks([a, b])

    assert {c.chunk_id for c in result} == {"a", "b"}


def test_empty_input():
    assert dedupe_near_identical_chunks([]) == []
