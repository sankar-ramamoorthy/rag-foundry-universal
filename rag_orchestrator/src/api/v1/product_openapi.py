# rag_orchestrator/src/api/v1/product_openapi.py
"""
Published OpenAPI artifact for the browser-facing product API (issue #434).

The artifact is the `/v1/product` subset of the orchestrator's schema with only
the components those routes reference, a product-specific title and the
`PRODUCT_API_VERSION`. It is committed at `frontend/openapi/product.openapi.json`
and a unit test fails when it drifts from the app.

    python -m src.api.v1.product_openapi --write   # regenerate (from rag_orchestrator/)
    python -m src.api.v1.product_openapi --check   # exit 1 when out of date
"""

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:  # `shared` lives at the repository root
    sys.path.insert(0, str(REPO_ROOT))

from src.api.v1.main import app  # noqa: E402
from src.api.v1.product_routes import PRODUCT_API_VERSION  # noqa: E402

ARTIFACT = (
    Path(__file__).resolve().parents[4]
    / "frontend"
    / "openapi"
    / "product.openapi.json"
)
PREFIX = "/v1/product/"
REF = "#/components/schemas/"


def _refs(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(REF):
            found.add(ref[len(REF) :])
        for value in node.values():
            _refs(value, found)
    elif isinstance(node, list):
        for value in node:
            _refs(value, found)


def product_schema() -> dict[str, Any]:
    full = app.openapi()
    paths = {p: v for p, v in full["paths"].items() if p.startswith(PREFIX)}
    schemas = full.get("components", {}).get("schemas", {})
    needed: set[str] = set()
    _refs(paths, needed)
    pending = list(needed)
    while pending:
        name = pending.pop()
        found: set[str] = set()
        _refs(schemas[name], found)
        for extra in found - needed:
            needed.add(extra)
            pending.append(extra)
    return {
        "openapi": full["openapi"],
        "info": {"title": "Foundry product API", "version": PRODUCT_API_VERSION},
        "paths": paths,
        "components": {"schemas": {n: schemas[n] for n in sorted(needed)}},
    }


def render() -> str:
    return json.dumps(product_schema(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--write" in argv:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(text, encoding="utf-8", newline="\n")
        return 0
    current = ARTIFACT.read_text(encoding="utf-8") if ARTIFACT.exists() else ""
    if current != text:
        print(f"{ARTIFACT} is out of date; run with --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
