"""Prevent the local baseline from uploading documents to remote services."""

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "document_baseline", SCRIPTS / "document_rag_baseline.py")
assert SPEC is not None and SPEC.loader is not None
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)
sys.path.pop(0)


@pytest.mark.parametrize("url", ["http://203.0.113.10:8001",
                                 "http://localhost.example.com:8101",
                                 "http://localhost@203.0.113.10:8001",
                                 "file:///tmp/source.md"])
def test_remote_and_disguised_remote_urls_rejected(url):
    with pytest.raises(ValueError, match="loopback"):
        baseline.require_local(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8101", "http://localhost:8101",
                                 "http://[::1]:8101"])
def test_loopback_urls_accepted(url):
    baseline.require_local(url)
