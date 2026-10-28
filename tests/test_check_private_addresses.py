"""The tailnet-address guard flags planted addresses and ignores clean files."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_private_addresses.py"
SPEC = importlib.util.spec_from_file_location("check_private_addresses", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def _tailnet(last: str = "5") -> str:
    # Built at runtime so this file never contains a literal tailnet address.
    return ".".join(["100", "101", "2", last])


@pytest.mark.parametrize(
    "line",
    [
        f"HOST = 'http://{_tailnet()}:8001'",
        f"api_base: http://{_tailnet('250')}:11434",
        "url = 'https://box.tail1234.ts.net'",
        "http://100.64.0.1:80",
        "http://100.127.255.254",
    ],
)
def test_flags_tailnet_addresses(tmp_path, line):
    (tmp_path / "x.py").write_text(line + "\n")
    assert guard.find_violations(tmp_path, ["x.py"])


@pytest.mark.parametrize(
    "line",
    [
        "http://100.63.0.1",  # below the CGNAT range
        "http://100.128.0.1",  # above it
        "version = '1100.100.2.3'",
        "http://203.0.113.10:8001",
        "http://localhost:8001",
    ],
)
def test_ignores_non_tailnet_addresses(tmp_path, line):
    (tmp_path / "x.py").write_text(line + "\n")
    assert not guard.find_violations(tmp_path, ["x.py"])


def test_exempts_docs_and_non_code_suffixes(tmp_path):
    (tmp_path / "DOCS").mkdir()
    (tmp_path / "DOCS" / "n.py").write_text(f"{_tailnet()}\n")
    (tmp_path / "data.json").write_text(f"{_tailnet()}\n")
    assert not guard.find_violations(tmp_path, ["DOCS/n.py", "data.json"])


def test_repository_is_clean():
    root = SCRIPT.parents[1]
    assert not guard.find_violations(root, guard.candidate_files(root))
