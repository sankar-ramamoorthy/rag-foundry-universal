"""#161 explicit legacy-job maintenance after all old workers have stopped.

Run with the ingestion service's environment/dependencies. Does not delete
artifacts/vectors or retry jobs. Ordinary startup recovers managed jobs only.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ingestion_service"))


def main():
    from src.core.ingestion_ownership import main as reconcile_main
    reconcile_main()


if __name__ == "__main__":
    main()
