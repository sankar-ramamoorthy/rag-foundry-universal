# ingestion_service/src/core/codebase/structural_inventory.py
"""
Deterministic, ingestion-time repository structural inventory (issue #197,
ORIENT). Pure functions only -- no DB/session/HTTP -- so the entire walk/
classify/find pipeline is independently testable and independently auditable
for determinism (same bytes on disk -> same output, always).

This module answers "what does this repository actually contain" (languages,
manifests, Compose services, heuristic test/docs locations) mechanically, not
by inference -- see DOCS/audit/2026-09-07-repository-intelligence-
architecture-audit.md for why this must not become an LLM-authored summary.

Deliberately NOT attempted here (out of scope for #197, see issue text and
the audit's own judgment table): dependency parsing inside manifests,
package/service *ownership* inference, CALLS_SERVICE/DEPENDS_ON architecture
edges, "most important file" or "where to start reading" heuristics.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import os

import yaml

from src.core.codebase.repo_graph_builder import DEFAULT_IGNORED_DIRS, EXTRACTORS

# Exact-basename match only -- no dependency parsing, presence + path only
# (MVP scope, #197 acceptance criteria).
MANIFEST_BASENAMES = {
    "pyproject.toml": "pyproject.toml",
    "package.json": "package.json",
    "Cargo.toml": "Cargo.toml",
    "pom.xml": "pom.xml",
    "requirements.txt": "requirements.txt",
}

# Suffix -> friendly language name. Deliberately reuses EXTRACTORS' suffix
# set as the "indexed" vocabulary, plus a few common non-indexed suffixes
# worth naming rather than lumping into "other".
_LANGUAGE_NAMES = {
    ".py": "python",
    ".md": "markdown",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".java": "java",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".txt": "text",
}

_TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec"}
_DOCS_DIR_NAMES = {"docs", "doc", "documentation"}

_COMPOSE_BASENAME_PREFIXES = ("docker-compose", "compose")
_COMPOSE_SUFFIXES = {".yml", ".yaml"}


@dataclass(frozen=True)
class ManifestFact:
    kind: str
    path: str  # relative, POSIX-separated


@dataclass(frozen=True)
class ServiceFact:
    name: str
    compose_file: str  # relative, POSIX-separated
    dockerfile: str | None
    container_name: str | None
    entry_point: str | None
    entry_point_source: str | None  # "compose.command" | None


@dataclass(frozen=True)
class GapNote:
    category: str  # "entry_point" | "manifest_parse" | "compose_parse" | "other"
    path: str | None
    reason: str


@dataclass(frozen=True)
class StructuralInventory:
    languages: dict[str, int]
    indexed_file_count: int
    non_indexed_file_count: int
    manifests: list[ManifestFact]
    services: list[ServiceFact]
    test_dirs: list[str]
    docs_dirs: list[str]
    gaps: list[GapNote]

    def summary_dict(self) -> dict:
        """The JSON blob persisted onto IngestionRequest.structural_summary
        and read directly (no recomputation, no joins) by
        GET /v1/repos/{repo_id}/orient.

        Manifests and services are included here WITH their full detail,
        not just as aggregate counts -- DocumentNode has no generic
        per-node metadata column, so a SERVICE node's container_name/
        entry_point can't be reconstructed later from the graph alone
        without a fragile node/relationship reverse-join. This blob is the
        single read path for all of ORIENT's display detail; the
        FILE/MANIFEST/SERVICE nodes persisted separately by
        inventory_to_graph_dicts exist for graph traversal (future TRACE/
        IMPACT work), not as this endpoint's data source -- both are
        derived once from the same walk, not two competing authorities.
        """
        return {
            "languages": dict(sorted(self.languages.items())),
            "file_counts": {
                "indexed": self.indexed_file_count,
                "non_indexed": self.non_indexed_file_count,
                "total": self.indexed_file_count + self.non_indexed_file_count,
            },
            "manifests": [asdict(m) for m in self.manifests],
            "services": [asdict(s) for s in self.services],
            "test_dirs": sorted(self.test_dirs),
            "docs_dirs": sorted(self.docs_dirs),
            "heuristic_fields": ["test_dirs", "docs_dirs"],
            "gaps": [asdict(g) for g in self.gaps],
        }


def walk_all_files(repo_root: Path) -> list[Path]:
    """Unfiltered walk over every first-party file in the checkout --
    mirrors RepoGraphBuilder._discover_crate_roots's/`_walk_repo`'s own
    ignore-dir (DEFAULT_IGNORED_DIRS) and dot-dir/dotfile pruning
    convention exactly, but without EXTRACTORS' suffix filter, so it also
    sees Dockerfiles, Compose YAML, and manifest files that the
    symbol-extraction walk never visits. Deterministic sorted order."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".") and d not in DEFAULT_IGNORED_DIRS
        )
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            files.append(Path(dirpath) / filename)
    return files


def _relative(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def classify_languages(files: list[Path], repo_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in files:
        name = _LANGUAGE_NAMES.get(path.suffix, "other")
        counts[name] = counts.get(name, 0) + 1
    return counts


def find_manifests(files: list[Path], repo_root: Path) -> list[ManifestFact]:
    manifests = [
        ManifestFact(
            kind=MANIFEST_BASENAMES[path.name], path=_relative(path, repo_root)
        )
        for path in files
        if path.name in MANIFEST_BASENAMES
    ]
    return sorted(manifests, key=lambda m: m.path)


def _is_compose_file(path: Path) -> bool:
    if path.suffix not in _COMPOSE_SUFFIXES:
        return False
    stem = path.name[: -len(path.suffix)].lower()
    return stem.startswith(_COMPOSE_BASENAME_PREFIXES)


def _resolve_entry_point(service_def: dict) -> tuple[str | None, str | None]:
    command = service_def.get("command")
    if isinstance(command, str) and command.strip():
        return command.strip(), "compose.command"
    if isinstance(command, list) and command:
        joined = " ".join(str(part) for part in command)
        if joined.strip():
            return joined.strip(), "compose.command"
    return None, None


def find_compose_services(
    files: list[Path],
    repo_root: Path,
) -> tuple[list[ServiceFact], list[GapNote]]:
    services: list[ServiceFact] = []
    gaps: list[GapNote] = []

    for path in files:
        if not _is_compose_file(path):
            continue
        relative_path = _relative(path, repo_root)
        try:
            text = path.read_text(encoding="utf-8")
            doc = yaml.safe_load(text)
        except Exception as exc:
            gaps.append(
                GapNote(
                    category="compose_parse",
                    path=relative_path,
                    reason=f"could not parse Compose YAML: {exc}",
                )
            )
            continue

        if not isinstance(doc, dict):
            gaps.append(
                GapNote(
                    category="compose_parse",
                    path=relative_path,
                    reason="Compose file did not parse to a mapping",
                )
            )
            continue

        service_map = doc.get("services")
        if not isinstance(service_map, dict):
            gaps.append(
                GapNote(
                    category="compose_parse",
                    path=relative_path,
                    reason="no top-level 'services:' mapping found",
                )
            )
            continue

        for service_name, service_def in sorted(service_map.items()):
            if not isinstance(service_def, dict):
                gaps.append(
                    GapNote(
                        category="compose_parse",
                        path=relative_path,
                        reason=f"service '{service_name}' definition was not a mapping",
                    )
                )
                continue

            build = service_def.get("build")
            dockerfile = None
            if isinstance(build, dict):
                dockerfile = build.get("dockerfile")
            container_name = service_def.get("container_name")
            entry_point, entry_point_source = _resolve_entry_point(service_def)
            if entry_point is None:
                gaps.append(
                    GapNote(
                        category="entry_point",
                        path=f"{relative_path}#{service_name}",
                        reason="no explicit compose 'command:' -- entry point "
                        "not trivially resolvable without inspecting the "
                        "image/Dockerfile CMD (out of MVP scope)",
                    )
                )

            services.append(
                ServiceFact(
                    name=service_name,
                    compose_file=relative_path,
                    dockerfile=dockerfile,
                    container_name=container_name,
                    entry_point=entry_point,
                    entry_point_source=entry_point_source,
                )
            )

    return sorted(services, key=lambda s: (s.compose_file, s.name)), gaps


def find_heuristic_dirs(files: list[Path], repo_root: Path) -> dict[str, list[str]]:
    test_dirs: set[str] = set()
    docs_dirs: set[str] = set()
    for path in files:
        rel = _relative(path, repo_root)
        parent_parts = Path(rel).parts[:-1]
        for i, part in enumerate(parent_parts):
            if part.lower() in _TEST_DIR_NAMES:
                test_dirs.add("/".join(parent_parts[: i + 1]))
            if part.lower() in _DOCS_DIR_NAMES:
                docs_dirs.add("/".join(parent_parts[: i + 1]))
    return {
        "test_dirs": sorted(test_dirs),
        "docs_dirs": sorted(docs_dirs),
    }


def build_structural_inventory(
    repo_root: Path,
    indexed_paths: set[str] | None = None,
) -> StructuralInventory:
    """Orchestrates the pure walk/classify/find steps into one deterministic
    snapshot. No LLM call, no network I/O, no wall-clock dependency.

    `indexed_paths`, when supplied (the real ingestion flow passes
    `graph.files.keys()`), gives exact indexed/non-indexed counts by asking
    "did the symbol graph actually produce a node for this file" rather than
    the suffix-only approximation used when this is called standalone (e.g.
    from a unit test with no RepoGraph available) -- a file with an
    EXTRACTORS-supported suffix that nonetheless failed to parse would be
    mis-counted as indexed by the suffix heuristic alone.
    """
    files = walk_all_files(repo_root)
    if indexed_paths is not None:
        indexed_count = sum(
            1 for f in files if _relative(f, repo_root) in indexed_paths
        )
    else:
        indexed_suffixes = set(EXTRACTORS.keys())
        indexed_count = sum(1 for f in files if f.suffix in indexed_suffixes)
    non_indexed_count = len(files) - indexed_count

    languages = classify_languages(files, repo_root)
    manifests = find_manifests(files, repo_root)
    services, compose_gaps = find_compose_services(files, repo_root)
    heuristic_dirs = find_heuristic_dirs(files, repo_root)

    return StructuralInventory(
        languages=languages,
        indexed_file_count=indexed_count,
        non_indexed_file_count=non_indexed_count,
        manifests=manifests,
        services=services,
        test_dirs=heuristic_dirs["test_dirs"],
        docs_dirs=heuristic_dirs["docs_dirs"],
        gaps=compose_gaps,
    )


def inventory_to_graph_dicts(
    ingestion_id: str,
    inventory: StructuralInventory,
    indexed_paths: set,
    repo_root: Path,
) -> tuple[list[dict], list[dict]]:
    """Convert deterministic inventory facts into the node/relationship dict
    shape CodebaseGraphPersistence.persist_graph already expects.

    Canonical-ID collision rule (hard constraint -- see #197 plan's design-
    decision section): a FILE/MANIFEST node is only emitted for a walked
    relative_path that is NOT already a key in `indexed_paths` (i.e. not
    already represented by a MODULE/MARKDOWN_MODULE node from the symbol
    graph). This guarantees no duplicate (repo_id, canonical_id) identity --
    an indexed .py/.md/.ts file simply gets no second node; its existing
    symbol-graph node already *is* its file identity. SERVICE nodes use a
    synthetic, explicitly namespaced canonical_id
    ("compose:<path>#<service>") that can never collide with a bare
    relative-path identity.
    """
    nodes: list[dict] = []
    relationships: list[dict] = []

    all_files = walk_all_files(repo_root)
    all_relative_paths = {_relative(p, repo_root) for p in all_files}
    manifest_paths = {m.path for m in inventory.manifests}
    manifest_kind_by_path = {m.path: m.kind for m in inventory.manifests}

    for path in sorted(all_files, key=lambda p: _relative(p, repo_root)):
        relative_path = _relative(path, repo_root)
        if relative_path in indexed_paths:
            continue
        doc_type = "manifest" if relative_path in manifest_paths else "file"
        title = (
            manifest_kind_by_path[relative_path]
            if relative_path in manifest_paths
            else Path(relative_path).name
        )
        nodes.append(
            {
                "relative_path": relative_path,
                "canonical_id": relative_path,
                "doc_type": doc_type,
                "title": title,
                "summary": "",
                "source": relative_path,
                "text": "",
                "ingestion_id": ingestion_id,
            }
        )

    for service in inventory.services:
        service_canonical_id = f"compose:{service.compose_file}#{service.name}"
        nodes.append(
            {
                "relative_path": service.compose_file,
                "canonical_id": service_canonical_id,
                "doc_type": "service",
                "title": service.name,
                "summary": "",
                "source": service.compose_file,
                "text": "",
                "ingestion_id": ingestion_id,
            }
        )
        if service.dockerfile and (
            service.dockerfile in indexed_paths
            or service.dockerfile in all_relative_paths
        ):
            # Best-effort only: build.dockerfile is conventionally relative
            # to the repo root when build.context is "." (this repo's own
            # convention); a compose file using a non-root context would
            # simply fail this membership check and the edge is skipped,
            # not treated as an error -- DECLARES is a bonus link, not a
            # required fact.
            relationships.append(
                {
                    "from_canonical_id": service_canonical_id,
                    "to_canonical_id": service.dockerfile,
                    "relation_type": "DECLARES",
                    "relationship_metadata": {},
                }
            )

    return nodes, relationships
