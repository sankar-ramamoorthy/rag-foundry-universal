from src.retrieval.repository_typed_facts import render_typed_facts


INVENTORY = {
    "services": [
        {
            "name": "app",
            "compose_file": "docker-compose.yml",
            "dockerfile": "app/Dockerfile",
        },
        {
            "name": "app",
            "compose_file": "docker-compose.test.yml",
            "dockerfile": "app/Dockerfile",
        },
        {"name": "postgres", "compose_file": "docker-compose.yml"},
    ],
    "manifests": [{"path": "app/pyproject.toml"}],
    "test_dirs": ["app/tests"],
    "languages": {"python": 3},
    "file_counts": {"total": 8},
}
GRAPH = {
    "nodes": [
        {"relative_path": "app/src/__init__.py", "doc_type": "python source"},
        {"relative_path": "app/src/main.py", "doc_type": "python source"},
        {
            "relative_path": "app/tests/fixtures/pkg/__init__.py",
            "doc_type": "python source",
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


def test_service_table_counts_distinct_names_and_keeps_fields_separate():
    text = render_typed_facts("service_table", INVENTORY, GRAPH, "repo", "demo")
    assert "Distinct Compose service identities: 2; Compose declarations: 3" in text
    assert "SERVICE app |" in text
    assert "tests=observed" in text
    assert "SERVICE postgres |" in text
    assert "repository directory=not established" in text
    assert "indexed source files by language={'python': 3}" in text


def test_observed_manifest_path_establishes_directory_without_source_file():
    graph = {"nodes": [{"relative_path": "app/pyproject.toml", "doc_type": "manifest"}]}
    text = render_typed_facts("service_table", INVENTORY, graph, "repo", "demo")
    assert "SERVICE app |" in text
    assert "repository directory=observed" in text
    assert "indexed source directory=not established" in text
    assert "SERVICE postgres |" in text


def test_package_markers_do_not_use_manifests_or_test_fixtures():
    text = render_typed_facts("package_markers", INVENTORY, GRAPH, "repo", "demo")
    assert "Package marker paths: ['app/src/__init__.py']" in text
    assert "marker count=1" in text
    assert "SERVICE postgres |" in text
    assert "Python package markers=not established" in text
    assert "pyproject manifest is dependency metadata" in text


def test_architecture_keeps_call_and_datastore_types_distinct():
    text = render_typed_facts("architecture_edges", INVENTORY, GRAPH, "repo", "demo")
    assert "service -> datastore: not established" in text
    assert "exposed host ports: not established" in text
    assert "HTTP candidate app -> postgres" not in text
