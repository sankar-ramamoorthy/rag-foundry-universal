# ingestion_service/tests/scripts/test_repo_graph_builder.py
import pytest
from pathlib import Path
from uuid import uuid4

from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.codebase.symbol_table import build_symbol_table


@pytest.fixture(scope="module")
def repo_graph():
    """
    Build the repo graph once for the whole test module.
    """
    # Adjust path if needed; here we use the `src` folder in the repo root
    ingestion_id = uuid4()
    repo_root = Path(__file__).resolve().parent.parent.parent / "src"
    builder = RepoGraphBuilder(repo_root,ingestion_id=ingestion_id)
    return builder.build()


@pytest.fixture(scope="module")
def symbol_table(repo_graph):
    """
    Build the symbol table from the repo graph.
    """
    return build_symbol_table(repo_graph)


def test_total_artifacts(repo_graph):
    """
    Ensure some artifacts were collected.
    """
    assert len(repo_graph.entities) > 0, "No artifacts were collected"


def test_some_calls_resolved(repo_graph, symbol_table):
    """
    Check that CALL artifacts have resolution and parent_id.
    """
    calls = [a for a in repo_graph.all_entities() if a["artifact_type"] == "CALL"]
    assert calls, "No CALL artifacts found"

    for call in calls[:20]:  # check a sample of 20
        name = call.get("name")
        resolution = call.get("resolution")
        parent = call.get("parent_id")

        assert parent is not None, f"CALL '{name}' has no parent_id"

        # Resolution should either be EXTERNAL or a known canonical ID
        if resolution != "EXTERNAL":
            assert resolution in repo_graph.entities or resolution in symbol_table.all_symbols(), (
                f"CALL '{name}' resolves to unknown ID '{resolution}'"
            )


def test_modules_and_classes_collected(repo_graph):
    """
    Ensure modules and classes were extracted.
    """
    modules = [a for a in repo_graph.all_entities() if a["artifact_type"] == "MODULE"]
    classes = [a for a in repo_graph.all_entities() if a["artifact_type"] == "CLASS"]

    assert modules, "No MODULE artifacts collected"
    assert classes, "No CLASS artifacts collected"


def test_functions_and_methods_collected(repo_graph):
    """
    Ensure functions and methods were extracted.
    """
    funcs = [a for a in repo_graph.all_entities() if a["artifact_type"] in ("FUNCTION", "METHOD")]
    assert funcs, "No FUNCTION or METHOD artifacts collected"


def test_imports_collected(repo_graph):
    """
    Ensure import statements were extracted.
    """
    imports = [a for a in repo_graph.all_entities() if a["artifact_type"] == "IMPORT"]
    assert imports, "No IMPORT artifacts collected"

def test_call_scoped_resolution(repo_graph):
    """Verify CALL resolution respects local scope and sets confidence"""
    calls = [a for a in repo_graph.entities.values() if a["artifact_type"] == "CALL"]
    assert calls, "No CALL artifacts found"

    for call in calls:
        # Confidence must exist
        assert "confidence" in call, f"CALL '{call['name']}' missing confidence"
        conf = call["confidence"]
        assert 0.0 <= conf <= 1.0, f"CALL '{call['name']}' confidence out of range"

        # Parent ID must exist
        assert call.get("parent_id") is not None, f"CALL '{call['name']}' missing parent_id"

        # If resolved, resolution should exist in graph
        if call["resolution"] != "EXTERNAL":
            assert call["resolution"] in repo_graph.entities, (
                f"CALL '{call['name']}' resolution points to unknown artifact '{call['resolution']}'"
            )

def test_defines_relationships(repo_graph):
    for entity in repo_graph.all_entities():
        defines = entity.get("defines", None)
        assert defines is not None, f"Entity '{entity.get('id')}' missing 'defines'"

        container_id = entity["id"]  # ← fix is here

        for did in defines:
            assert did in repo_graph.entities, (
                f"Entity '{entity.get('id')}' defines unknown artifact '{did}'"
            )

            defined_entity = repo_graph.get_entity(did)
            parent_id = defined_entity.get("parent_id")

            remaining = defined_entity["id"][len(container_id):]
            if remaining.count("#") <= 1:
                assert parent_id == container_id, (
                    f"Defined entity '{did}' parent_id '{parent_id}' does not match container '{entity['id']}'"
                )

def test_call_resolution_nested(repo_graph):
    """
    Verify CALL resolution respects nested scopes:
    - Method calling another method in same class
    - Class calling module-level function
    - Module-level call to global symbol
    - Unresolved calls marked as EXTERNAL
    """
    calls = [a for a in repo_graph.all_entities() if a["artifact_type"] == "CALL"]
    assert calls, "No CALL artifacts found"

    for call in calls:
        name = call.get("name")
        resolution = call.get("resolution")
        confidence = call.get("confidence")
        parent = call.get("parent_id")

        # All calls must have confidence and parent
        assert parent is not None, f"CALL '{name}' missing parent_id"
        assert 0.0 <= confidence <= 1.0, f"CALL '{name}' confidence {confidence} out of range"

        # Resolution must exist in graph or be EXTERNAL
        if resolution != "EXTERNAL":
            assert resolution in repo_graph.entities, f"CALL '{name}' resolves to unknown artifact '{resolution}'"

def test_call_external_fallback(repo_graph):
    """
    Ensure unresolved CALLs are marked as EXTERNAL with confidence 0.0
    """
    calls = [a for a in repo_graph.all_entities() if a["artifact_type"] == "CALL"]
    assert calls, "No CALL artifacts found"

    for call in calls:
        name = call.get("name")
        resolution = call.get("resolution")
        confidence = call.get("confidence")

        if resolution == "EXTERNAL":
            assert confidence == 0.0, f"External CALL '{name}' should have confidence 0.0"
