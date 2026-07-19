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
