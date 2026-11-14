"""Issue #359: structural eligibility check for held-out repository candidates.

Runs this checkout's ingestion extraction (structural inventory, service
topology and RepoGraphBuilder) in memory over a local clone, and reports
**counts only**: compose services, routes, routes with a resolved path and
handler, cross-service calls, and per-handler reach over resolved CALL edges.
It does not print source text, function names or chains, so the candidate's
evaluation answers are not exposed to the person choosing it (ADR-054 §3).
Nothing is persisted and no service is contacted.

    python scripts/heldout_eligibility_359.py CLONE_DIR [CLONE_DIR ...]
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _imports():
    os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
    sys.path.insert(0, str(ROOT / "ingestion_service"))
    cwd = os.getcwd()
    os.chdir(ROOT / "ingestion_service")
    try:
        from src.core.codebase.repo_graph_builder import RepoGraphBuilder
        from src.core.codebase.service_topology import build_service_topology
        from src.core.codebase.structural_inventory import (
            build_structural_inventory,
            walk_all_files,
        )
    finally:
        os.chdir(cwd)
    return (
        RepoGraphBuilder,
        build_service_topology,
        build_structural_inventory,
        walk_all_files,
    )


def reach(out: dict, start: str, depth: int = 6) -> int:
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        cur, d = queue.popleft()
        if d >= depth:
            continue
        for nxt in out[cur]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, d + 1))
    return len(seen) - 1


def check(clone: Path) -> dict:
    RepoGraphBuilder, build_topology, build_inventory, walk_all = _imports()
    cwd = os.getcwd()
    os.chdir(ROOT / "ingestion_service")
    try:
        graph = RepoGraphBuilder(clone, ingestion_id="eligibility-359").build()
        inventory = build_inventory(clone, set(graph.files.keys()))
        topology = build_topology(
            clone, walk_all(clone), inventory.services, set(graph.entities.keys())
        )
    finally:
        os.chdir(cwd)
    out = defaultdict(list)
    for r in graph.relationships:
        t = r["to_canonical_id"]
        if r["relation_type"] == "CALL" and not t.startswith("EXTERNAL_"):
            out[r["from_canonical_id"]].append(t)
    routes = topology.routes
    handled = [r for r in routes if r.handler_canonical_id in graph.entities]
    reaches = sorted(reach(out, r.handler_canonical_id) for r in handled)
    head = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    return {
        "clone": clone.name,
        "head": head,
        "python_files": sum(1 for f in graph.files if f.endswith(".py")),
        "compose_services": len(inventory.services),
        "routes": len(routes),
        "routes_with_handler_node": len(handled),
        "routes_with_resolved_full_path": sum(1 for r in routes if r.resolved_path),
        "service_calls": len(getattr(topology, "service_calls", []) or []),
        "handlers_reaching_ge3_functions": sum(1 for x in reaches if x >= 3),
        "handler_reach_median": statistics.median(reaches) if reaches else 0,
        "handler_reach_max": max(reaches) if reaches else 0,
    }


def main(argv: list[str]) -> int:
    for arg in argv:
        try:
            print(json.dumps(check(Path(arg).resolve())))
        except Exception as exc:  # report and continue with other candidates
            print(
                json.dumps(
                    {
                        "clone": Path(arg).name,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    }
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
