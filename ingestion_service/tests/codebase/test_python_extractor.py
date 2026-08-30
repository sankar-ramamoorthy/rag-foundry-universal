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

    result = extractor.extract(source_code)
    symbols = result.symbols

    # -----------------------------
    # Module symbol
    # -----------------------------
    module_symbols = [s for s in symbols if s.kind == "MODULE"]
    assert len(module_symbols) == 1
    assert module_symbols[0].symbol_path is None

    # -----------------------------
    # Class symbols
    # -----------------------------
    class_symbols = [s for s in symbols if s.kind == "CLASS"]
    class_names = [c.name for c in class_symbols]
    assert "PythonASTExtractor" in class_names

    # -----------------------------
    # Method symbols
    # -----------------------------
    method_symbols = [s for s in symbols if s.kind == "METHOD"]
    method_names = [m.name for m in method_symbols]
    # Methods inside PythonASTExtractor
    expected_methods = [
        "extract",
        "visit_ClassDef",
        "visit_FunctionDef",
        "visit_Import",
        "visit_ImportFrom",
        "visit_Call",
        "_get_parent_class",
    ]
    for method in expected_methods:
        assert method in method_names

    # -----------------------------
    # Function symbols (top-level)
    # -----------------------------
    function_symbols = [s for s in symbols if s.kind == "FUNCTION"]
    function_names = [f.name for f in function_symbols]
    # The top-level helper function
    assert "annotate_parents" in function_names

    # -----------------------------
    # Import records
    # -----------------------------
    import_names = [
        i.imported_name if i.imported_name is not None else i.raw_module
        for i in result.imports
    ]
    import_modules = [
        i.raw_module for i in result.imports if i.imported_name is not None
    ]

    # Check standard imports
    assert "ast" in import_names  # from 'import ast'

    # Check 'from typing import List, Optional'
    for symbol in ["List", "Optional"]:
        assert symbol in import_names
    assert "typing" in import_modules  # ensure the module itself is tracked

    # -----------------------------
    # Call sites (F-03: evidence list, not symbols)
    # -----------------------------
    assert not any(s.kind == "CALL" for s in symbols)
    site_keys = {(s.receiver, s.callee_name) for s in extractor.call_sites}

    # Check at least one known call exists: ast.unparse used in extractor
    assert ("ast", "unparse") in site_keys
