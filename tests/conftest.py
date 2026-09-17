"""Make repo-level shared modules importable with either pytest entrypoint."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
