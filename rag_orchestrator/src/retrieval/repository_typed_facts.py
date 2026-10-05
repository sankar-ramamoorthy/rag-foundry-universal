"""Small, explicitly typed facts for issue #240 overview experiments."""

from collections import defaultdict
from typing import Any

EXPERIMENTS = frozenset({"service_table", "package_markers", "architecture_edges"})
_SOURCE_TYPES = {
    "python source": "python",
    "rust source": "rust",
    "java source": "java",
    "typescript source": "typescript",
    "javascript source": "javascript",
}


def render_typed_facts(  # noqa: C901 - bounded experiment composes three typed views
    experiment: str,
    inventory: dict[str, Any],
    graph: dict[str, Any],
    repo_id: str,
    repository_name: str | None,
) -> str:
    """Render facts only when both pinned structural sources are present."""
    if experiment not in EXPERIMENTS:
        raise ValueError(f"Unknown typed fact experiment: {experiment}")
    services = inventory.get("services", [])
    names = sorted({str(row["name"]) for row in services if row.get("name")})
    paths_by_service: dict[str, set[str]] = defaultdict(set)
    source_by_service: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for node in graph.get("nodes", []):
        path = node.get("relative_path")
        if not isinstance(path, str):
            continue
        name = path.split("/", 1)[0]
        if name not in names or "/" not in path:
            continue
        paths_by_service[name].add(path)
        language = _SOURCE_TYPES.get(node.get("doc_type"))
        if language:
            source_by_service[name][language].add(path)
    manifests = {row["path"] for row in inventory.get("manifests", [])}
    test_dirs = set(inventory.get("test_dirs", []))
    lines = [
        "PINNED REPOSITORY FACTS",
        f"Repository: {repository_name or 'name not established'}.",
        f"Repository ID (not a commit SHA): {repo_id}.",
        f"Distinct Compose service identities: {len(names)}; "
        f"Compose declarations: {len(services)}.",
        "Each row below is keyed by service identity. "
        "A missing marker means not established, not no.",
    ]
    top_level = sorted(
        {
            str(node["relative_path"]).split("/", 1)[0]
            for node in graph.get("nodes", [])
            if isinstance(node.get("relative_path"), str)
            and "/" in node["relative_path"]
        }
    )
    lines.append(f"Graph-observed top-level directories: {top_level}.")
    for name in names:
        declarations = [row for row in services if row.get("name") == name]
        compose = sorted({str(row["compose_file"]) for row in declarations})
        dockerfiles = sorted(
            {str(row["dockerfile"]) for row in declarations if row.get("dockerfile")}
        )
        directory = "observed" if paths_by_service[name] else "not established"
        source = "observed" if source_by_service[name] else "not established"
        language_counts = {
            lang: len(paths) for lang, paths in sorted(source_by_service[name].items())
        }
        package_markers = sorted(
            path
            for path in paths_by_service[name]
            if path.endswith("/__init__.py")
            and "/tests/" not in path
            and "/fixtures/" not in path
        )
        marker_status = "observed" if package_markers else "not established"
        pyproject = (
            "observed" if name + "/pyproject.toml" in manifests else "not listed"
        )
        lines.append(
            f"SERVICE {name} | Compose={compose} | repository directory={directory} "
            f"| indexed source directory={source} "
            f"| Dockerfile={dockerfiles or 'not listed'} "
            f"| pyproject={pyproject} "
            f"| tests={'observed' if name + '/tests' in test_dirs else 'not listed'} "
            f"| indexed source files by language={language_counts or 'none observed'} "
            f"| Python package markers={marker_status} "
            f"| marker count={len(package_markers)}"
        )
        if experiment == "package_markers" and package_markers:
            lines.append(f"  Package marker paths: {package_markers}")
    lines.append(
        f"ORIENT whole-repository language/file counts: "
        f"{inventory.get('languages', {})}; {inventory.get('file_counts', {})}. "
        "These whole-repository counts must not be assigned to individual services."
    )
    if experiment == "service_table":
        lines.append(
            "For counts or all/each claims, check every service row. "
            "Do not infer a package from pyproject or a source directory from Compose."
        )
    elif experiment == "package_markers":
        lines.append(
            "A pyproject manifest is dependency metadata, not a Python package marker. "
            "Only an observed __init__.py path establishes a traditional Python "
            "package here. Without one, say package presence is not established. "
            "The observed directory still exists when package markers are absent."
        )
    else:
        calls: dict[tuple[str, str], set[str]] = defaultdict(set)
        for caller, edges in graph.get("relationships", {}).items():
            source = caller.split("/", 1)[0]
            if source not in names:
                continue
            for edge in edges:
                if edge.get("relation_type") != "CALLS_SERVICE":
                    continue
                target = str(edge.get("to_canonical_id", "")).split("#")[-1]
                metadata = edge.get("relationship_metadata") or {}
                if (
                    target in names
                    and source != target
                    and source_by_service[source]
                    and source_by_service[target]
                    and "URL" in str(metadata.get("matched_identifier", ""))
                ):
                    calls[(source, target)].add(
                        str(metadata.get("matched_identifier", "unspecified"))
                    )
        lines.extend(
            [
                "RELATION TYPE application -> application HTTP candidates: "
                "CALLS_SERVICE graph edges are heuristic co-occurrence, not proof of "
                "every runtime request.",
                *(
                    f"HTTP candidate {source} -> {target} via {sorted(identifiers)}"
                    for (source, target), identifiers in sorted(calls.items())
                ),
                "RELATION TYPE service -> datastore: not established by ORIENT or "
                "CALLS_SERVICE. Do not reinterpret a Compose declaration "
                "as an HTTP edge.",
                "RELATION TYPE deployment/Compose: the per-service Compose "
                "fields above "
                "record declarations only; dependency edges are not established here.",
                "RELATION TYPE exposed host ports: not established by ORIENT or graph. "
                "Do not invent port values or use internal URLs as exposed host ports.",
            ]
        )
    return "\n".join(lines) + "\n"
