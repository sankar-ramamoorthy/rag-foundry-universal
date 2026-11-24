# rag_orchestrator/tests/test_product_openapi.py
"""
Issue #434 / specs/016-product-frontend: the published product contract.

The committed OpenAPI artifact must match the app, and every committed fixture
must validate against the schema the artifact declares for its route and
status. The TypeScript client is generated from the same artifact.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.api.v1 import product_openapi

pytestmark = pytest.mark.unit

FIXTURES = sorted(
    (product_openapi.ARTIFACT.parent.parent / "fixtures" / "product").glob("*.json")
)
REPO_FIELDS = {
    "repo_id",
    "name",
    "display_name",
    "source_type",
    "branch",
    "ingested_at",
    "file_count",
    "node_count",
}


def _artifact():
    return json.loads(product_openapi.ARTIFACT.read_text(encoding="utf-8"))


def _fixture(name):
    return json.loads(
        (
            product_openapi.ARTIFACT.parent.parent / "fixtures" / "product" / name
        ).read_text(encoding="utf-8")
    )


def _response_schema(artifact, method, path, status):
    operation = artifact["paths"][path][method.lower()]
    response = operation["responses"].get(str(status))
    assert response is not None, f"{method} {path} does not declare {status}"
    return response["content"]["application/json"]["schema"]


def test_artifact_matches_the_app():
    assert product_openapi.ARTIFACT.read_text(encoding="utf-8") == (
        product_openapi.render()
    ), "frontend/openapi/product.openapi.json is out of date; run --write"


def test_artifact_is_versioned_and_product_only():
    artifact = _artifact()
    assert artifact["info"]["title"] == "Foundry product API"
    assert artifact["info"]["version"]
    assert artifact["paths"]
    assert all(p.startswith("/v1/product/") for p in artifact["paths"])


def test_artifact_has_no_dangling_references():
    artifact = _artifact()
    names = set(artifact["components"]["schemas"])
    text = json.dumps(artifact)
    import re

    used = set(re.findall(r'"#/components/schemas/([A-Za-z0-9_]+)"', text))
    assert used <= names
    assert names <= used, f"unreferenced components: {names - used}"


def test_every_route_declares_a_json_success_and_the_stable_error_body():
    artifact = _artifact()
    for path, item in artifact["paths"].items():
        for method, operation in item.items():
            assert "200" in operation["responses"], (method, path)
            if path == "/v1/product/capabilities":
                continue  # a static report of enabled modes; it has no 4xx
            errors = [c for c in operation["responses"] if c != "200" and c != "422"]
            assert errors, (method, path)
            for code in errors:
                schema = _response_schema(artifact, method, path, code)
                assert schema == {"$ref": "#/components/schemas/ProductErrorResponse"}


def test_generation_is_required_on_every_pinned_route():
    artifact = _artifact()
    for path, item in artifact["paths"].items():
        if path in ("/v1/product/repos", "/v1/product/capabilities") or path.endswith(
            "/readiness"
        ):
            continue
        operation = next(iter(item.values()))
        if path.endswith("/ask"):
            required = artifact["components"]["schemas"]["AskRequest"]["required"]
            assert "generation_id" in required, path
            continue
        if path.endswith("/investigations"):
            schemas = artifact["components"]["schemas"]
            required = schemas["InvestigateRequest"]["required"]
            assert "generation_id" in required, path
            continue
        if "/investigations/" in path:
            continue  # the signed run ID carries its generation
        names = {p["name"] for p in operation["parameters"] if p["required"]}
        assert "generation_id" in names, path


def test_repository_picker_exposes_only_sanitized_fields():
    schema = _artifact()["components"]["schemas"]["ProductRepo"]
    assert set(schema["properties"]) == REPO_FIELDS


def test_error_codes_are_a_closed_set():
    schema = _artifact()["components"]["schemas"]["ProductError"]
    assert set(schema["properties"]["code"]["enum"]) == {
        "unavailable",
        "stale",
        "invalid_range",
        "resource_limit",
        "not_found",
        "invalid_request",
    }


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_validates_against_its_declared_schema(path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    artifact = _artifact()
    request = fixture["request"]
    schema = _response_schema(
        artifact, request["method"], request["path"], fixture["status"]
    )
    root = {**schema, "components": artifact["components"]}
    Draft202012Validator.check_schema(root)
    errors = list(Draft202012Validator(root).iter_errors(fixture["body"]))
    assert not errors, [e.message for e in errors]


def test_fixtures_cover_every_route_and_the_required_states():
    names = {p.stem for p in FIXTURES}
    assert {
        "readiness_ready",
        "readiness_unavailable",
        "source_stale",
        "source_invalid_range",
        "source_resource_limit",
        "ask_ok",
        "ask_no_range_citations",
        "ask_stale",
    } <= names
    covered = {_fixture(f"{n}.json")["request"]["path"] for n in names}
    assert covered == set(_artifact()["paths"])


def test_source_fixtures_use_inclusive_one_based_intervals():
    for name in ("source_partial", "source_whole_file"):
        body = _fixture(f"{name}.json")["body"]
        lines = body["text"].splitlines(keepends=True)
        assert 1 <= body["start_line"] <= body["end_line"]
        assert body["end_line"] - body["start_line"] + 1 == len(lines)


def test_fixtures_carry_no_private_material():
    for path in FIXTURES:
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("c:\\\\", "/users/", "password", "secret", "token"):
            assert forbidden not in text, (path.name, forbidden)
        assert Path(path).read_text(encoding="utf-8").endswith("\n")
