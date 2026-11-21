# rag_orchestrator/tests/conftest.py
# src.core.service imports via both `src.*` (service-local, covered by
# pytest.ini pythonpath=.) and `rag_orchestrator.*`/`shared.*` (repo-root
# packages, available in the Docker build context). Add the repo root so
# unit tests can import the service layer outside Docker.
import sys
from pathlib import Path

REPO_ROOT = str(Path(__file__).resolve().parents[2])
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_envelope_commit_lookup(monkeypatch):
    """Issue #406: the envelope's commit lookup is one extra HTTP call to
    ingestion_service. Unit tests must not reach the network, so stub it;
    test_evidence_envelope.py exercises the real function directly and
    overrides this stub where it needs a specific commit."""
    from src.core import envelope

    async def _no_commit(repo_id, generation_id):
        return None, ["commit_sha not recorded for this generation"]

    monkeypatch.setattr(envelope, "fetch_commit_sha", _no_commit)
