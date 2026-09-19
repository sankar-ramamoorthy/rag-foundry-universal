# ingestion_service/src/core/codebase/service_topology.py
"""
Mechanically derived endpoint/service/HTTP-call facts (issue #221, a
fast-follow to #197/#198/#220).

Regex/text-pattern based, deliberately NOT a full AST parse -- same MVP
discipline as structural_inventory.py (#197): deterministic, no LLM,
explicit GapNote disclosure whenever something can't be confidently
resolved rather than silent omission or a guessed answer.

Two families of additive graph facts:

- EXPOSES_ENDPOINT: SERVICE node (from #197's structural_inventory,
  reused by identity -- never duplicated) -> a synthetic ROUTE node,
  itself linked HANDLED_BY -> the existing handler function's canonical_id
  in the symbol graph. The ROUTE node's canonical_id/title encode
  method+path directly (DocumentNode has no generic metadata column, so
  there's nowhere else to put them -- same convention #197 already
  established for SERVICE/MANIFEST nodes).
- CALLS_SERVICE: an existing function's canonical_id -> the SERVICE node
  its source appears to call over HTTP, resolved by matching a same-file
  URL-constant/Settings-field literal's hostname against a known compose
  service name. A heuristic co-occurrence match (the identifier and an
  HTTP-verb call both appear in the same function body), not a confirmed
  data-flow trace -- disclosed as such in relationship_metadata.

Explicitly NOT attempted here (see issue #221's own non-goals): dynamic/
conditional route registration, cross-file argument tracing (e.g.
HttpVectorStore's base_url passed in from a different file), non-Python
services, or promoting any of this to a claim of confirmed runtime
behavior -- these are static, source-derived possible-call facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from src.core.codebase.structural_inventory import GapNote, ServiceFact
from src.core.codebase.structural_inventory import _TEST_DIR_NAMES

_ROUTE_DECORATOR_RE = re.compile(
    r'@(\w+)\.(get|post|put|delete|patch)\(\s*"([^"]*)"', re.MULTILINE
)
_DEF_AFTER_DECORATOR_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
_APIROUTER_PREFIX_RE = re.compile(r"APIRouter\(([^)]*)\)")
_PREFIX_KWARG_RE = re.compile(r'prefix\s*=\s*"([^"]*)"')
_INCLUDE_ROUTER_RE = re.compile(
    r'(\w+)\.include_router\(\s*([\w.]+)(?:[^)]*?prefix\s*=\s*"([^"]*)")?[^)]*\)'
)
_FASTAPI_APP_RE = re.compile(r"\bapp\s*=\s*FastAPI\(")
_IMPORT_LINE_RE = re.compile(r"^from\s+([\w.]+)\s+import\s+(.+?)\s*(?:#.*)?$")
_URL_CONSTANT_RE = re.compile(
    r"([A-Z][A-Z0-9_]*)\s*(?::\s*\w+)?\s*=\s*"
    r'(?:os\.getenv\([^,]*,\s*)?f?"(http://([a-z_][a-z0-9_]*)(?::\d+)?[^"]*)"'
)
_HTTP_VERB_CALL_RE = re.compile(r"\.(?:get|post|put|delete|patch)\(")
_DEF_LINE_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")
_CLASS_LINE_RE = re.compile(r"^(\s*)class\s+(\w+)")

_MAX_MOUNT_CHAIN_DEPTH = 5


@dataclass(frozen=True)
class RouteFact:
    method: str
    local_path: str
    resolved_path: str | None  # None -> prefix chain not resolved
    handler_canonical_id: str
    relative_path: str
    service_dir: str


@dataclass(frozen=True)
class ServiceCallFact:
    caller_canonical_id: str
    target_service_name: str
    matched_url: str


@dataclass(frozen=True)
class ServiceTopology:
    routes: list[RouteFact]
    service_calls: list[ServiceCallFact]
    gaps: list[GapNote]


def _service_dir(relative_path: str) -> str:
    return relative_path.split("/", 1)[0]


def _module_to_relpaths(dotted_module: str, service_dir: str) -> list[str]:
    parts = dotted_module.split(".")
    base = "/".join([service_dir, *parts])
    return [f"{base}.py", f"{base}/__init__.py"]


def _parse_import_aliases(text: str, service_dir: str) -> dict[str, str]:
    """local_alias -> dotted_module of the file that defines `.router`
    reachable via that alias, either directly (`from X import router as
    alias`) or via submodule attribute access (`from X import alias` then
    `alias.router`)."""
    aliases: dict[str, str] = {}
    for line in text.splitlines():
        match = _IMPORT_LINE_RE.match(line.strip())
        if not match:
            continue
        base_module, clause = match.groups()
        clause = clause.split("#", 1)[0].strip().strip("()")
        for part in clause.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                name, alias = (p.strip() for p in part.split(" as ", 1))
            else:
                name, alias = part, part
            if name == "router":
                aliases[alias] = base_module
            else:
                aliases[alias] = f"{base_module}.{name}"
    return aliases


def _own_router_prefix(text: str) -> str:
    """First `APIRouter(...)` call on a non-comment line. Confirmed live
    against this repo's own `repos.py`, which has a real, uncommented
    `router = APIRouter(tags=["repos"])` *and* a dead, commented-out
    `#router = APIRouter(prefix="/v1", tags=["repos"])` above it -- a
    whole-text `.search()` finds the commented line first regardless of
    the `#`, since regex has no concept of comments, and would wrongly
    extract "/v1" from dead code (compounding into a real "/v1/v1/..."
    double-prefix once the mount chain's own "/v1" is added on top)."""
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _APIROUTER_PREFIX_RE.search(line)
        if match:
            kwarg = _PREFIX_KWARG_RE.search(match.group(1))
            return kwarg.group(1) if kwarg else ""
    return ""


def _build_mount_graph(
    files: dict[str, str],
    service_dir: str,
) -> dict[str, tuple[str, str | None, bool]]:
    """relpath -> (mounting_file_relpath, extra_prefix_or_None, is_root)
    for every router file some other file in the service mounts.

    _INCLUDE_ROUTER_RE's `(\\w+)\\.include_router\\(` prefix is
    unanchored by any literal character before the `\\w+` -- run against
    a whole file's text (not pre-filtered), a long run of word
    characters with no `.` in it (e.g. a large embedded string literal in
    a fixture/test-data file) makes the engine backtrack `\\w+` one
    character at a time looking for a `.` that never appears, at every
    starting offset -- O(n^2) on such input. Pre-filtering to only the
    lines that contain the literal substring "include_router" first
    (a cheap O(n) scan) means the expensive regex only ever runs against
    short, real candidate lines.
    """
    mounted_by: dict[str, tuple[str, str | None, bool]] = {}
    for relpath, text in files.items():
        if "include_router" not in text:
            continue
        aliases = _parse_import_aliases(text, service_dir)
        candidate_lines = "\n".join(
            line for line in text.splitlines() if "include_router" in line
        )
        for receiver, ref, extra_prefix in _INCLUDE_ROUTER_RE.findall(candidate_lines):
            if "." in ref:
                alias, attr = ref.split(".", 1)
                if attr != "router":
                    continue
            else:
                alias = ref
            dotted_module = aliases.get(alias)
            if dotted_module is None:
                continue
            for candidate in _module_to_relpaths(dotted_module, service_dir):
                if candidate in files:
                    mounted_by[candidate] = (
                        relpath,
                        extra_prefix or None,
                        receiver == "app",
                    )
                    break
    return mounted_by


def _resolve_effective_prefix(
    relative_path: str,
    files: dict[str, str],
    mount_graph: dict[str, tuple[str, str | None, bool]],
) -> tuple[str | None, str | None]:
    """(resolved_prefix, gap_reason). A bare `@app.*` decorator's file has
    no router indirection at all -- resolved_prefix="" immediately."""
    if _FASTAPI_APP_RE.search(files[relative_path]):
        return "", None

    prefix_parts: list[str] = [_own_router_prefix(files[relative_path])]
    current = relative_path
    for _ in range(_MAX_MOUNT_CHAIN_DEPTH):
        entry = mount_graph.get(current)
        if entry is None:
            return None, f"no include_router() found that mounts {current}"
        mounting_file, extra_prefix, is_root = entry
        if extra_prefix:
            prefix_parts.append(extra_prefix)
        if is_root:
            # prefix_parts was built innermost-first (this file's own
            # prefix, then each mounting file's own prefix outward) --
            # the URL reads outermost-first, so reverse before joining.
            return "".join(reversed(prefix_parts)), None
        prefix_parts.append(_own_router_prefix(files[mounting_file]))
        current = mounting_file
    return (
        None,
        f"mount chain for {relative_path} exceeded depth {_MAX_MOUNT_CHAIN_DEPTH}",
    )


def _find_handler_name(lines: list[str], decorator_lineno: int) -> str | None:
    """The function name on the first non-comment, non-decorator line
    after a route decorator -- None if nothing def-shaped follows within
    a few lines (e.g. a decorator stack got interrupted by unrelated
    code)."""
    for candidate_line in lines[decorator_lineno + 1 : decorator_lineno + 6]:
        if candidate_line.lstrip().startswith("#"):
            continue
        def_match = _DEF_AFTER_DECORATOR_RE.match(candidate_line)
        if def_match:
            return def_match.group(1)
        if candidate_line.strip() and not candidate_line.lstrip().startswith("@"):
            return None
    return None


def _resolve_route_path(
    receiver: str,
    local_path: str,
    relative_path: str,
    files: dict[str, str],
    mount_graph: dict[str, tuple[str, str | None, bool]],
) -> tuple[str | None, str | None]:
    """(resolved_path, gap_reason). A decorator on `app` directly needs no
    prefix-chain walk at all -- its local path already is the full path."""
    if receiver == "app":
        return local_path, None
    prefix, gap_reason = _resolve_effective_prefix(relative_path, files, mount_graph)
    resolved_path = None if prefix is None else prefix.rstrip("/") + local_path
    return resolved_path, gap_reason


def _extract_one_route(
    relative_path: str,
    text: str,
    lines: list[str],
    lineno: int,
    line: str,
    service_dir: str,
    files: dict[str, str],
    mount_graph: dict[str, tuple[str, str | None, bool]],
    known_symbol_canonical_ids: set[str],
) -> tuple[RouteFact | None, list[GapNote]]:
    match = _ROUTE_DECORATOR_RE.search(line)
    if not match:
        return None, []
    receiver, method, local_path = match.groups()

    handler_name = _find_handler_name(lines, lineno)
    if handler_name is None:
        return None, [
            GapNote(
                category="route_handler",
                path=f"{relative_path}:{lineno + 1}",
                reason="no handler def found immediately after route decorator",
            )
        ]

    handler_canonical_id = f"{relative_path}#{handler_name}"
    if handler_canonical_id not in known_symbol_canonical_ids:
        return None, [
            GapNote(
                category="route_handler",
                path=handler_canonical_id,
                reason="decorator's handler function not found in the symbol graph",
            )
        ]

    resolved_path, gap_reason = _resolve_route_path(
        receiver,
        local_path,
        relative_path,
        files,
        mount_graph,
    )
    gaps = (
        [
            GapNote(
                category="route_prefix",
                path=f"{relative_path}:{lineno + 1}",
                reason=gap_reason,
            )
        ]
        if gap_reason
        else []
    )
    route = RouteFact(
        method=method.upper(),
        local_path=local_path,
        resolved_path=resolved_path,
        handler_canonical_id=handler_canonical_id,
        relative_path=relative_path,
        service_dir=service_dir,
    )
    return route, gaps


def _extract_routes(
    files: dict[str, str],
    service_dir: str,
    known_symbol_canonical_ids: set[str],
) -> tuple[list[RouteFact], list[GapNote]]:
    mount_graph = _build_mount_graph(files, service_dir)
    routes: list[RouteFact] = []
    gaps: list[GapNote] = []

    for relative_path, text in files.items():
        lines = text.splitlines()
        for lineno, line in enumerate(lines):
            if line.lstrip().startswith("#"):
                continue
            route, new_gaps = _extract_one_route(
                relative_path,
                text,
                lines,
                lineno,
                line,
                service_dir,
                files,
                mount_graph,
                known_symbol_canonical_ids,
            )
            gaps.extend(new_gaps)
            if route is not None:
                routes.append(route)
    return routes, gaps


def _function_spans(text: str, relative_path: str) -> list[tuple[str, int, int]]:
    """[(canonical_id, start_line_idx, end_line_idx_exclusive)] for every
    module-level function and one level of class-method nesting -- enough
    to cover every real call site found in this repo's services; deeper
    nesting is simply not attributed (no CALLS_SERVICE emitted from it,
    not a crash)."""
    lines = text.splitlines()
    spans: list[tuple[str, int, int]] = []
    current_class: tuple[str, int] | None = None  # (name, indent)
    open_def: tuple[str, int] | None = None  # (canonical_name, indent)
    start_idx = 0

    def close(end_idx: int) -> None:
        nonlocal open_def
        if open_def is not None:
            spans.append((f"{relative_path}#{open_def[0]}", start_idx, end_idx))
            open_def = None

    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        class_match = _CLASS_LINE_RE.match(line)
        if class_match and (
            current_class is None or len(class_match.group(1)) <= current_class[1]
        ):
            close(idx)
            current_class = (class_match.group(2), len(class_match.group(1)))
            continue
        def_match = _DEF_LINE_RE.match(line)
        if def_match:
            indent, name = len(def_match.group(1)), def_match.group(2)
            if current_class is not None and indent <= current_class[1]:
                current_class = None
            close(idx)
            qualified = (
                f"{current_class[0]}.{name}"
                if current_class and indent > current_class[1]
                else name
            )
            open_def = (qualified, indent)
            start_idx = idx
    close(len(lines))
    return spans


def _identifier_hosts_for_service(
    service_files: dict[str, str],
    known_service_names: set[str],
) -> dict[str, str]:
    identifier_hosts: dict[str, str] = {}
    for text in service_files.values():
        for name, _url, host in _URL_CONSTANT_RE.findall(text):
            if host in known_service_names:
                identifier_hosts[name] = host
    return identifier_hosts


def _calls_in_function(
    canonical_id: str,
    body: str,
    identifier_hosts: dict[str, str],
) -> list[ServiceCallFact]:
    if not _HTTP_VERB_CALL_RE.search(body):
        return []
    return [
        ServiceCallFact(
            caller_canonical_id=canonical_id,
            target_service_name=host,
            matched_url=name,
        )
        for name, host in identifier_hosts.items()
        if re.search(rf"\b{re.escape(name)}\b", body)
    ]


def _extract_service_calls(
    files: dict[str, str],
    compose_services: list[ServiceFact],
) -> list[ServiceCallFact]:
    """Cross-service call detection is deliberately service-dir-scoped,
    not per-file: the URL-constant/Settings-field definition
    (e.g. `INGESTION_SERVICE_URL` in config.py) and the call site that
    references it (e.g. `settings.INGESTION_SERVICE_URL` in service.py)
    are almost always in different files within the same service, per
    #221's own research into this repo's actual services."""
    known_service_names = {service.name for service in compose_services}

    by_service_dir: dict[str, dict[str, str]] = {}
    for relative_path, text in files.items():
        by_service_dir.setdefault(_service_dir(relative_path), {})[relative_path] = text

    calls: list[ServiceCallFact] = []
    for service_files in by_service_dir.values():
        identifier_hosts = _identifier_hosts_for_service(
            service_files, known_service_names
        )
        if not identifier_hosts:
            continue
        for relative_path, text in service_files.items():
            lines = text.splitlines()
            for canonical_id, start, end in _function_spans(text, relative_path):
                body = "\n".join(lines[start:end])
                calls.extend(_calls_in_function(canonical_id, body, identifier_hosts))
    return calls


def build_service_topology(
    repo_root: Path,
    all_files: list[Path],
    compose_services: list[ServiceFact],
    known_symbol_canonical_ids: set[str],
) -> ServiceTopology:
    """Orchestrates route + cross-service-call extraction. `all_files`
    should be the same unfiltered walk `structural_inventory.py` already
    performed (`walk_all_files`) -- passed in rather than re-walked, so
    this stays a pure function over data the caller already has.

    Test files are excluded from the Python file set entirely (same
    heuristic dir-name convention `structural_inventory.find_heuristic_dirs`
    already uses for `test_dirs`). This matters more here than it did for
    #197's inventory: a test file that spins up its own throwaway
    `app = FastAPI(); app.include_router(some_module.router)` to test one
    router in isolation -- an established pattern in this very repo's own
    test suite (`test_orient_integration.py`, `test_orient_passthrough.py`,
    `test_trace_impact_routes.py`) -- is a real, syntactically valid mount
    registration by every signal this module looks for, and would
    silently override the real application's actual mount chain for
    whichever router it re-mounts (confirmed live: a test file mounting
    `orient.router` directly on its own `app` with no prefix overwrote
    the real `/v1` prefix ingestion_service's actual `main.py` applies,
    because dict iteration order let the test file's entry win)."""
    python_files = {
        p.relative_to(repo_root).as_posix(): p.read_text(encoding="utf-8")
        for p in all_files
        if p.suffix == ".py"
        and not any(part.lower() in _TEST_DIR_NAMES for part in p.parts)
    }

    by_service_dir: dict[str, dict[str, str]] = {}
    for relative_path, text in python_files.items():
        by_service_dir.setdefault(_service_dir(relative_path), {})[relative_path] = text

    all_routes: list[RouteFact] = []
    all_gaps: list[GapNote] = []
    for service_dir, files in by_service_dir.items():
        routes, gaps = _extract_routes(files, service_dir, known_symbol_canonical_ids)
        all_routes.extend(routes)
        all_gaps.extend(gaps)

    service_calls = _extract_service_calls(python_files, compose_services)

    return ServiceTopology(
        routes=all_routes, service_calls=service_calls, gaps=all_gaps
    )


def service_topology_to_graph_dicts(
    ingestion_id: str,
    topology: ServiceTopology,
    compose_services: list[ServiceFact],
) -> tuple[list[dict], list[dict]]:
    """Convert extracted facts into the node/relationship dict shape
    CodebaseGraphPersistence.persist_graph already expects. ROUTE nodes
    use a namespaced synthetic canonical_id (never a bare relative_path),
    matching #197's SERVICE-node collision rule -- can't duplicate any
    real file/symbol identity. SERVICE nodes themselves are NOT created
    here -- they already exist from #197's structural_inventory pass;
    this only adds edges to them by the SAME canonical_id it uses."""
    service_canonical_id_by_name = {
        service.name: f"compose:{service.compose_file}#{service.name}"
        for service in compose_services
    }

    nodes: list[dict] = []
    relationships: list[dict] = []

    for route in topology.routes:
        display_path = route.resolved_path or route.local_path
        route_canonical_id = f"route:{route.service_dir}:{route.method}:{display_path}"
        nodes.append(
            {
                "relative_path": route.relative_path,
                "canonical_id": route_canonical_id,
                "doc_type": "route",
                "title": f"{route.method} {display_path}",
                "summary": "",
                "source": route.relative_path,
                "text": "",
                "ingestion_id": ingestion_id,
            }
        )
        relationships.append(
            {
                "from_canonical_id": route_canonical_id,
                "to_canonical_id": route.handler_canonical_id,
                "relation_type": "HANDLED_BY",
                "relationship_metadata": {},
            }
        )
        service_cid = service_canonical_id_by_name.get(route.service_dir)
        if service_cid is not None:
            relationships.append(
                {
                    "from_canonical_id": service_cid,
                    "to_canonical_id": route_canonical_id,
                    "relation_type": "EXPOSES_ENDPOINT",
                    "relationship_metadata": {
                        "resolved": route.resolved_path is not None,
                    },
                }
            )

    for call in topology.service_calls:
        service_cid = service_canonical_id_by_name.get(call.target_service_name)
        if service_cid is None:
            continue
        relationships.append(
            {
                "from_canonical_id": call.caller_canonical_id,
                "to_canonical_id": service_cid,
                "relation_type": "CALLS_SERVICE",
                "relationship_metadata": {
                    "evidence": "heuristic_co_occurrence",
                    "matched_identifier": call.matched_url,
                },
            }
        )

    return nodes, relationships
