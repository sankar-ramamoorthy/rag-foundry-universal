import pytest
from src.core.extractors import python_extractor

# Path to the file we want to test on (here we use the extractor itself)
SAMPLE_FILE_PATH = "core/extractors/python_extractor.py"

@pytest.fixture
def extractor():
    # Must pass relative_path for the extractor
    return python_extractor.PythonASTExtractor(relative_path=SAMPLE_FILE_PATH)

def test_extractor_on_self_file(extractor):
    # Read the extractor file itself
    with open(f"src/{SAMPLE_FILE_PATH}", "r", encoding="utf-8") as f:
        source_code = f.read()

    artifacts = extractor.extract(source_code)

    # -----------------------------
    # Module artifact
    # -----------------------------
    module_artifacts = [a for a in artifacts if a["artifact_type"] == "MODULE"]
    assert len(module_artifacts) == 1
    assert module_artifacts[0]["id"] == SAMPLE_FILE_PATH

    # -----------------------------
    # Class artifacts
    # -----------------------------
    class_artifacts = [a for a in artifacts if a["artifact_type"] == "CLASS"]
    class_names = [c["name"] for c in class_artifacts]
    assert "PythonASTExtractor" in class_names

    # -----------------------------
    # Method artifacts
    # -----------------------------
    method_artifacts = [a for a in artifacts if a["artifact_type"] == "METHOD"]
    method_names = [m["name"] for m in method_artifacts]
    # Methods inside PythonASTExtractor
    expected_methods = ["extract", "visit_ClassDef", "visit_FunctionDef", "visit_Import",
                        "visit_ImportFrom", "visit_Call", "_get_parent_class"]
    for method in expected_methods:
        assert method in method_names

    # -----------------------------
    # Function artifacts (top-level)
    # -----------------------------
    function_artifacts = [a for a in artifacts if a["artifact_type"] == "FUNCTION"]
    function_names = [f["name"] for f in function_artifacts]
    # The top-level helper function
    assert "annotate_parents" in function_names

    # -----------------------------
    # Import artifacts
    # -----------------------------
    import_artifacts = [a for a in artifacts if a["artifact_type"] == "IMPORT"]
    import_names = [i["name"] for i in import_artifacts]
    import_modules = [i.get("metadata", {}).get("module") for i in import_artifacts if "module" in i.get("metadata", {})]

    # Check standard imports
    assert "ast" in import_names  # from 'import ast'

    # Check 'from typing import List, Dict, Optional'
    for symbol in ["List", "Dict", "Optional"]:
        assert symbol in import_names
    assert "typing" in import_modules  # ensure the module itself is tracked in metadata

    # -----------------------------
    # Call artifacts (unresolved)
    # -----------------------------
    call_artifacts = [a for a in artifacts if a["artifact_type"] == "CALL"]
    call_names = [c["name"] for c in call_artifacts]

    # Check at least one known call exists: ast.unparse used in extractor
    assert any("ast.unparse" in c for c in call_names)

