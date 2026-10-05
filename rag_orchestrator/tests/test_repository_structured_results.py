from copy import deepcopy

from src.retrieval.repository_structured_results import (
    build_architecture_result,
    build_service_result,
    render_architecture_answer,
    render_service_answer,
    validate_architecture_result,
    validate_service_result,
)

INVENTORY = {
    "services": [
        {
            "name": "app",
            "compose_file": "docker-compose.yml",
            "dockerfile": "app/Dockerfile",
        },
        {
            "name": "gradio",
            "compose_file": "docker-compose.yml",
            "dockerfile": "gradio/Dockerfile",
        },
        {"name": "postgres", "compose_file": "docker-compose.yml"},
    ],
    "manifests": [
        {"path": "gradio/pyproject.toml"},
        {"path": "app/tests/fixtures/rust_repo/Cargo.toml"},
    ],
    "test_dirs": ["app/tests"],
    "file_counts": {"total": 5},
    "languages": {"python": 2},
}
GRAPH = {
    "nodes": [
        {"relative_path": "app/src/__init__.py", "doc_type": "python source"},
        {"relative_path": "app/src/main.py", "doc_type": "python source"},
        {"relative_path": "gradio/pyproject.toml", "doc_type": "manifest"},
        {
            "relative_path": "app/tests/fixtures/rust_repo/src/main.rs",
            "doc_type": "rust source",
        },
    ],
    "relationships": {
        "app/src/main.py#run": [
            {
                "relation_type": "CALLS_SERVICE",
                "to_canonical_id": "compose:docker-compose.yml#postgres",
                "relationship_metadata": {"matched_identifier": "DATABASE_URL"},
            }
        ]
    },
}
COMPOSE = {
    "docker-compose.yml": {
        "services": {
            "app": {
                "build": {"dockerfile": "app/Dockerfile"},
                "environment": {
                    "DATABASE_URL": "postgresql://user:secret@postgres:5432/db",
                },
                "depends_on": {"postgres": {"condition": "service_healthy"}},
                "ports": ["8001:8000"],
            },
            "gradio": {"build": {"dockerfile": "gradio/Dockerfile"}},
            "postgres": {"image": "pgvector/pgvector:pg15", "ports": ["5434:5432"]},
        }
    }
}


def test_complete_service_result_and_unknown_package_state():
    result = build_service_result(INVENTORY, GRAPH)
    assert result["service_count"] == 3
    assert result["services"]["gradio"]["repository_directory"] == "OBSERVED"
    assert result["services"]["gradio"]["indexed_source_directory"] == "UNKNOWN"
    assert result["services"]["gradio"]["package"]["status"] == "UNKNOWN"
    assert result["services"]["app"]["package"]["status"] == "OBSERVED"
    assert result["services"]["app"]["manifests"] == []
    assert result["services"]["app"]["indexed_implementation_files_by_language"] == {
        "python": 2
    }
    assert validate_service_result(result, INVENTORY, GRAPH) == []
    answer = render_service_answer(result, "q3")
    assert "absence is not proven" in answer


def test_validator_rejects_unknown_to_absence_and_missing_fields():
    result = build_service_result(INVENTORY, GRAPH)
    changed = deepcopy(result)
    changed["services"]["gradio"]["package"]["status"] = "PROVEN_ABSENT"
    changed["services"]["app"].pop("test_directories")
    changed["service_count"] = 4
    errors = validate_service_result(changed, INVENTORY, GRAPH)
    assert "gradio:package_mismatch" in errors
    assert "app:test_directories_mismatch" in errors
    assert "service_count_mismatch" in errors


def test_architecture_separates_datastore_deployment_and_ports():
    services = build_service_result(INVENTORY, GRAPH)
    result = build_architecture_result(services, GRAPH, COMPOSE)
    assert result["components"]["postgres"]["kind"] == "datastore"
    assert result["http_edges"] == []
    assert result["datastore_edges"] == [
        ("docker-compose.yml", "app", "postgres", "DATABASE_URL")
    ]
    assert result["deployment_edges"] == [("docker-compose.yml", "app", "postgres")]
    assert ("docker-compose.yml", "postgres", "5434", "5432") in result["ports"]
    assert validate_architecture_result(result, services, GRAPH, COMPOSE) == []
    answer = render_architecture_answer(result)
    assert "DATABASE_URL, not HTTP" in answer
    assert "postgres: 5434:5432" in answer
    invalid = deepcopy(result)
    invalid["http_edges"].append(("app", "postgres", "made_up"))
    assert "http_edges_mismatch" in validate_architecture_result(
        invalid, services, GRAPH, COMPOSE
    )
