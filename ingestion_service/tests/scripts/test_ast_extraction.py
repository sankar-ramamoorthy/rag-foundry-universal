import os
import pytest
from src.core.extractors import python_extractor

# ----------------------------
# Fixture: PythonASTExtractor on its own file
# ----------------------------
@pytest.fixture
def extractor():
    # Dynamically locate this extractor file
    sample_file = os.path.join(
        os.path.dirname(__file__),
        "../../src/core/extractors/python_extractor.py"
    )
    # Normalize path for canonical ID
    relative_path = os.path.relpath(sample_file).replace("\\", "/")
    return python_extractor.PythonASTExtractor(relative_path=relative_path)


# ----------------------------
# Test: extract artifacts from the extractor itself
# ----------------------------
def test_extractor_on_self_file(extractor):
    # Read source code
    sample_file = os.path.join(
        os.path.dirname(__file__),
        "../../src/core/extractors/python_extractor.py"
    )
    with open(sample_file, "r", encoding="utf-8") as f:
        source_code = f.read()

    # Extract artifacts
    artifacts = extractor.extract(source_code)
    for artifact in artifacts:
        print(artifact)


    # ----------------------------
    # Module artifact
    # ----------------------------
    module_artifacts = [a for a in artifacts if a["artifact_type"] == "MODULE"]
    assert len(module_artifacts) == 1
    assert module_artifacts[0]["id"].endswith("python_extractor.py")

    # ----------------------------
    # Class artifacts
    # ----------------------------
    class_artifacts = [a for a in artifacts if a["artifact_type"] == "CLASS"]
    class_names = [c["name"] for c in class_artifacts]
    assert "PythonASTExtractor" in class_names

    # ----------------------------
    # Method artifacts (inside PythonASTExtractor)
    # ----------------------------
    method_artifacts = [a for a in artifacts if a["artifact_type"] == "METHOD"]
    method_names = [m["name"] for m in method_artifacts]
    expected_methods = [
        "extract",
        "visit_ClassDef",
        "visit_FunctionDef",
        "visit_Import",
        "visit_ImportFrom",
        "visit_Call",
        "_get_parent_class"
    ]
    for method in expected_methods:
        assert method in method_names

    # ----------------------------
    # Top-level functions
    # ----------------------------
    function_artifacts = [a for a in artifacts if a["artifact_type"] == "FUNCTION"]
    function_names = [f["name"] for f in function_artifacts]
    assert "annotate_parents" in function_names

    # ----------------------------
    # Import artifacts
    # ----------------------------
    import_artifacts = [a for a in artifacts if a["artifact_type"] == "IMPORT"]
    import_names = [i["name"] for i in import_artifacts]
    import_modules = [
        i.get("metadata", {}).get("module")
        for i in import_artifacts
        if "module" in i.get("metadata", {})
    ]

    # Standard imports
    assert "ast" in import_names
    for symbol in ["List", "Dict", "Optional"]:
        assert symbol in import_names
    assert "typing" in import_modules

    # ----------------------------
    # Call artifacts (unresolved)
    # ----------------------------
    call_artifacts = [a for a in artifacts if a["artifact_type"] == "CALL"]
    call_names = [c["name"] for c in call_artifacts]

    # Ensure at least one known call exists
    assert any("ast.unparse" in c for c in call_names)
    assert any("setattr" in c for c in call_names)
