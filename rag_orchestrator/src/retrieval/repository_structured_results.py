"""Validated repository-overview result shapes for issue #240 experiments.

The builders derive typed facts. Renderers accept only validated results and
never ask a generator to reconstruct finite inventory or edge semantics.
"""

from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

PACKAGE_STATES = frozenset({"OBSERVED", "UNKNOWN", "PROVEN_ABSENT"})
_SOURCE_TYPES = {
    "python source": "python",
    "rust source": "rust",
    "java source": "java",
    "typescript source": "typescript",
    "javascript source": "javascript",
}


def build_service_result(
    inventory: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    """Build service-keyed facts without interpreting missing paths as absence."""
    declarations = inventory.get("services", [])
    names = sorted({row["name"] for row in declarations if row.get("name")})
    paths: dict[str, set[str]] = defaultdict(set)
    source_files: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    top_level: set[str] = set()
    for node in graph.get("nodes", []):
        path = node.get("relative_path")
        if not isinstance(path, str) or "/" not in path:
            continue
        root = path.split("/", 1)[0]
        top_level.add(root)
        if root not in names:
            continue
        paths[root].add(path)
        language = _SOURCE_TYPES.get(node.get("doc_type"))
        if language and "/tests/" not in path and "/fixtures/" not in path:
            source_files[root][language].add(path)
    manifests = {row["path"] for row in inventory.get("manifests", [])}
    test_dirs = set(inventory.get("test_dirs", []))
    rows: dict[str, dict[str, Any]] = {}
    for name in names:
        own = [row for row in declarations if row.get("name") == name]
        markers = sorted(
            path
            for path in paths[name]
            if path.endswith("/__init__.py")
            and "/tests/" not in path
            and "/fixtures/" not in path
        )
        rows[name] = {
            "compose_declarations": sorted({row["compose_file"] for row in own}),
            "repository_directory": "OBSERVED" if paths[name] else "UNKNOWN",
            "indexed_source_directory": (
                "OBSERVED" if source_files[name] else "UNKNOWN"
            ),
            "dockerfiles": sorted(
                {row["dockerfile"] for row in own if row.get("dockerfile")}
            ),
            "manifests": sorted(
                path for path in manifests if path.rsplit("/", 1)[0] == name
            ),
            "test_directories": sorted(
                path for path in test_dirs if path == name + "/tests"
            ),
            "indexed_implementation_files_by_language": {
                lang: len(files) for lang, files in sorted(source_files[name].items())
            },
            "package": {
                "status": "OBSERVED" if markers else "UNKNOWN",
                "markers": markers,
            },
        }
    return {
        "schema": "repository-service-result-v1",
        "top_level_directories": sorted(top_level),
        "service_count": len(names),
        "compose_declaration_count": len(declarations),
        "services": rows,
        "whole_repository_file_counts": inventory.get("file_counts", {}),
        "whole_repository_language_counts": inventory.get("languages", {}),
    }


def validate_service_result(  # noqa: C901 - checks every required typed field
    result: dict[str, Any], inventory: dict[str, Any], graph: dict[str, Any]
) -> list[str]:
    """Reject missing fields, changed enum states, and wrong source derivation."""
    expected = build_service_result(inventory, graph)
    errors = []
    if result.get("schema") != expected["schema"]:
        errors.append("wrong_schema")
    if result.get("top_level_directories") != expected["top_level_directories"]:
        errors.append("top_level_directories_mismatch")
    if result.get("service_count") != expected["service_count"]:
        errors.append("service_count_mismatch")
    if result.get("compose_declaration_count") != expected["compose_declaration_count"]:
        errors.append("compose_declaration_count_mismatch")
    rows = result.get("services")
    if not isinstance(rows, dict) or set(rows) != set(expected["services"]):
        return errors + ["service_identity_mismatch"]
    for name, expected_row in expected["services"].items():
        row = rows[name]
        if not isinstance(row, dict):
            errors.append(f"{name}:invalid_row")
            continue
        for field, value in expected_row.items():
            if row.get(field) != value:
                errors.append(f"{name}:{field}_mismatch")
        package = row.get("package")
        if isinstance(package, dict) and package.get("status") not in PACKAGE_STATES:
            errors.append(f"{name}:invalid_package_state")
    for field in ("whole_repository_file_counts", "whole_repository_language_counts"):
        if result.get(field) != expected[field]:
            errors.append(f"{field}_mismatch")
    return errors


def build_architecture_result(  # noqa: C901 - handles four disjoint edge types
    service_result: dict[str, Any],
    graph: dict[str, Any],
    compose_files: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Keep HTTP evidence, datastore configuration, deployment, ports apart."""
    names = set(service_result["services"])
    http_edges: set[tuple[str, str, str]] = set()
    datastore_edges: set[tuple[str, str, str, str]] = set()
    deployment_edges: set[tuple[str, str, str]] = set()
    ports: set[tuple[str, str, str, str]] = set()
    components = {}
    for name, row in service_result["services"].items():
        components[name] = {
            "kind": "application" if row["dockerfiles"] else "external_container",
            "package_status": row["package"]["status"],
        }
    for filename, document in compose_files.items():
        for source, spec in document.get("services", {}).items():
            if source not in names:
                continue
            image = str(spec.get("image", ""))
            if image.startswith(("postgres", "pgvector/pgvector")):
                components[source]["kind"] = "datastore"
            dependencies = spec.get("depends_on") or []
            for target in dependencies:
                if target in names:
                    deployment_edges.add((filename, source, target))
            environment = spec.get("environment") or {}
            if isinstance(environment, list):
                environment = dict(
                    item.split("=", 1) for item in environment if "=" in item
                )
            for key, value in environment.items():
                parsed = urlparse(str(value))
                target = parsed.hostname
                if target is None or target not in names or target == source:
                    continue
                if parsed.scheme in {"http", "https"}:
                    http_edges.add((source, target, f"compose:{filename}:{key}"))
                elif parsed.scheme.startswith("postgres"):
                    datastore_edges.add((filename, source, target, str(key)))
            for item in spec.get("ports") or []:
                if isinstance(item, str) and ":" in item:
                    host, container = item.rsplit(":", 1)
                    ports.add((filename, source, host, container))
    for caller, edges in graph.get("relationships", {}).items():
        source = caller.split("/", 1)[0]
        if source not in names or components[source]["kind"] != "application":
            continue
        for edge in edges:
            if edge.get("relation_type") != "CALLS_SERVICE":
                continue
            target = str(edge.get("to_canonical_id", "")).split("#")[-1]
            metadata = edge.get("relationship_metadata") or {}
            identifier = str(metadata.get("matched_identifier", ""))
            if (
                target in names
                and components[target]["kind"] == "application"
                and "URL" in identifier
            ):
                http_edges.add((source, target, f"heuristic:{identifier}"))
    return {
        "schema": "repository-architecture-result-v1",
        "components": components,
        "http_edges": sorted(http_edges),
        "datastore_edges": sorted(datastore_edges),
        "deployment_edges": sorted(deployment_edges),
        "ports": sorted(ports),
        "scope": sorted(compose_files),
    }


def validate_architecture_result(
    result: dict[str, Any],
    service_result: dict[str, Any],
    graph: dict[str, Any],
    compose_files: dict[str, dict[str, Any]],
) -> list[str]:
    expected = build_architecture_result(service_result, graph, compose_files)
    return [
        f"{field}_mismatch"
        for field, value in expected.items()
        if result.get(field) != value
    ]


def render_service_answer(result: dict[str, Any], focus: str) -> str:
    if focus not in {"q2", "q3"}:
        raise ValueError("focus must be q2 or q3")
    lines = [
        "Observed top-level directories: "
        f"{', '.join(result['top_level_directories'])}.",
        f"Compose declares {result['service_count']} distinct service identities "
        f"in {result['compose_declaration_count']} declarations.",
    ]
    for name, row in result["services"].items():
        package = row["package"]
        if package["status"] == "OBSERVED":
            package_text = (
                f"OBSERVED ({len(package['markers'])} traditional package markers)"
                if focus == "q2"
                else f"observed markers: {', '.join(package['markers'])}"
            )
        else:
            package_text = (
                "UNKNOWN: no traditional package marker observed; package "
                "absence is not proven"
            )
        if focus == "q3":
            lines.append(
                f"{name}: repository directory {row['repository_directory']}; "
                f"Python package {package_text}."
            )
        else:
            lines.append(
                f"{name}: Compose {row['compose_declarations']}; repository "
                f"directory {row['repository_directory']}; indexed source directory "
                f"{row['indexed_source_directory']}; Dockerfiles {row['dockerfiles']}; "
                f"manifests {row['manifests']}; test directories "
                f"{row['test_directories']}; indexed implementation files "
                f"by language {row['indexed_implementation_files_by_language']}; "
                "Python package "
                f"{package_text}."
            )
    if focus == "q2":
        lines.append(
            f"Whole-repository file counts: {result['whole_repository_file_counts']}; "
            f"language counts: {result['whole_repository_language_counts']}."
        )
    return "\n".join(lines)


def render_architecture_answer(result: dict[str, Any]) -> str:
    lines = [
        "Components: "
        + ", ".join(
            f"{name} ({item['kind']})" for name, item in result["components"].items()
        )
        + ".",
        "Application HTTP relationships (Compose URL configuration or "
        "heuristic graph calls):",
    ]
    lines.extend(
        f"- {source} -> {target} [{evidence}]"
        for source, target, evidence in result["http_edges"]
    )
    lines.append("Service-to-datastore configuration (DATABASE_URL, not HTTP):")
    lines.extend(
        f"- {source} -> {target} [{filename}:{key}]"
        for filename, source, target, key in result["datastore_edges"]
    )
    lines.append("Compose startup dependencies (not request edges):")
    lines.extend(
        f"- {source} depends on {target} [{filename}]"
        for filename, source, target in result["deployment_edges"]
    )
    lines.append("Published host:container ports by Compose file:")
    lines.extend(
        f"- {source}: {host}:{container} [{filename}]"
        for filename, source, host, container in result["ports"]
    )
    lines.append(
        "Scope: " + ", ".join(result["scope"]) + ". These declarations do "
        "not establish every runtime call or the active deployment profile."
    )
    return "\n".join(lines)
