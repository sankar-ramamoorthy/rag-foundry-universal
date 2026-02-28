import pytest
from src.core.codebase.identity import build_canonical_id, build_global_id

def test_build_canonical_id_file_only():
    cid = build_canonical_id("src/module.py")
    assert cid == "src/module.py"

def test_build_canonical_id_with_symbol():
    cid = build_canonical_id("src/module.py", "MyClass.my_method")
    assert cid == "src/module.py#MyClass.my_method"

def test_build_global_id():
    gid = build_global_id("123e4567-e89b-12d3-a456-426614174000", "src/module.py", "func")
    assert gid == ("123e4567-e89b-12d3-a456-426614174000", "src/module.py#func")
