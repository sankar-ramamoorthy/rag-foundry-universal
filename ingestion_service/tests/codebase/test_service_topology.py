# ingestion_service/tests/codebase/test_service_topology.py
"""
Issue #221: mechanically derived endpoint/service/HTTP-call facts.
Small hand-built fixture trees reproducing the three real router-mount
patterns found across this repo's own services (2-level __init__.py
chain, prefix-at-include-site, module-attribute import) plus a
cross-service HTTP call site -- no DB/HTTP, pure text-pattern extraction.
"""

from pathlib import Path

import pytest

from src.core.codebase.structural_inventory import ServiceFact
from src.core.codebase.service_topology import (
    build_service_topology,
    service_topology_to_graph_dicts,
)

pytestmark = pytest.mark.unit


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _service_fact(name: str) -> ServiceFact:
    return ServiceFact(
        name=name,
        compose_file="docker-compose.yml",
        dockerfile=None,
        container_name=None,
        entry_point=None,
        entry_point_source=None,
    )


def test_two_level_mount_chain_resolves_full_path(tmp_path):
    # Mirrors ingestion_service's own __init__.py -> graph.py pattern.
    _write(
        tmp_path,
        "service_a/src/api/v1/graph.py",
        "from fastapi import APIRouter\n"
        'router = APIRouter(prefix="/graph")\n\n\n'
        '@router.get("/repos/{repo_id}")\n'
        "async def get_full_graph(repo_id: str):\n"
        "    pass\n",
    )
    _write(
        tmp_path,
        "service_a/src/api/v1/__init__.py",
        "from fastapi import APIRouter\n"
        "from src.api.v1.graph import router as graph_router\n"
        'router = APIRouter(prefix="/v1")\n'
        "router.include_router(graph_router)\n",
    )
    _write(
        tmp_path,
        "service_a/src/api/v1/main.py",
        "from fastapi import FastAPI\n"
        "from src.api.v1 import router as v1_router\n"
        "app = FastAPI()\n"
        "app.include_router(v1_router)\n",
    )

    all_files = [
        tmp_path / "service_a/src/api/v1/graph.py",
        tmp_path / "service_a/src/api/v1/__init__.py",
        tmp_path / "service_a/src/api/v1/main.py",
    ]
    known = {"service_a/src/api/v1/graph.py#get_full_graph"}

    topology = build_service_topology(tmp_path, all_files, [], known)

    assert len(topology.routes) == 1
    route = topology.routes[0]
    assert route.method == "GET"
    assert route.resolved_path == "/v1/graph/repos/{repo_id}"
    assert route.handler_canonical_id == "service_a/src/api/v1/graph.py#get_full_graph"
    assert topology.gaps == []


def test_prefix_at_include_site_resolves_full_path(tmp_path):
    # Mirrors rag_orchestrator's routes.py -> main.py pattern (prefix
    # applied at the include_router() call, not the router's own ctor).
    _write(
        tmp_path,
        "service_b/src/api/v1/routes.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n\n\n"
        '@router.post("/rag")\n'
        "async def rag_endpoint():\n"
        "    pass\n",
    )
    _write(
        tmp_path,
        "service_b/src/api/v1/main.py",
        "from fastapi import FastAPI\n"
        "from src.api.v1.routes import router\n"
        "app = FastAPI()\n"
        'app.include_router(router, prefix="/v1")\n',
    )

    all_files = [
        tmp_path / "service_b/src/api/v1/routes.py",
        tmp_path / "service_b/src/api/v1/main.py",
    ]
    known = {"service_b/src/api/v1/routes.py#rag_endpoint"}

    topology = build_service_topology(tmp_path, all_files, [], known)

    assert len(topology.routes) == 1
    assert topology.routes[0].resolved_path == "/v1/rag"


def test_module_attribute_import_and_bare_app_route(tmp_path):
    # Mirrors llm_service/vector_store_service's `from X import admin`
    # then `app.include_router(admin.router)` pattern, plus a route
    # declared directly on `app` (no router indirection at all).
    _write(
        tmp_path,
        "service_c/src/api/v1/admin.py",
        "from fastapi import APIRouter\n"
        'router = APIRouter(prefix="/v1/admin")\n\n\n'
        '@router.put("/policy/{slot}")\n'
        "async def set_slot(slot: str):\n"
        "    pass\n",
    )
    _write(
        tmp_path,
        "service_c/src/api/v1/main.py",
        "from fastapi import FastAPI\n"
        "from src.api.v1 import admin\n"
        "app = FastAPI()\n"
        "app.include_router(admin.router)\n\n\n"
        '@app.get("/health")\n'
        "def health_check():\n"
        "    pass\n",
    )

    all_files = [
        tmp_path / "service_c/src/api/v1/admin.py",
        tmp_path / "service_c/src/api/v1/main.py",
    ]
    known = {
        "service_c/src/api/v1/admin.py#set_slot",
        "service_c/src/api/v1/main.py#health_check",
    }

    topology = build_service_topology(tmp_path, all_files, [], known)
    by_handler = {r.handler_canonical_id: r for r in topology.routes}

    assert by_handler["service_c/src/api/v1/admin.py#set_slot"].resolved_path == (
        "/v1/admin/policy/{slot}"
    )
    assert (
        by_handler["service_c/src/api/v1/main.py#health_check"].resolved_path
        == "/health"
    )
    assert by_handler["service_c/src/api/v1/main.py#health_check"].method == "GET"


def test_unmounted_router_produces_a_gap_not_silent_omission(tmp_path):
    _write(
        tmp_path,
        "service_d/src/api/v1/orphan.py",
        "from fastapi import APIRouter\n"
        'router = APIRouter(prefix="/orphan")\n\n\n'
        '@router.get("/thing")\n'
        "async def get_thing():\n"
        "    pass\n",
    )

    all_files = [tmp_path / "service_d/src/api/v1/orphan.py"]
    known = {"service_d/src/api/v1/orphan.py#get_thing"}

    topology = build_service_topology(tmp_path, all_files, [], known)

    assert len(topology.routes) == 1
    assert topology.routes[0].resolved_path is None
    assert any(g.category == "route_prefix" for g in topology.gaps)


def test_decorator_with_unresolved_handler_produces_a_gap(tmp_path):
    _write(
        tmp_path,
        "service_e/src/api/v1/main.py",
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n\n\n"
        '@app.get("/health")\n'
        "def health_check():\n"
        "    pass\n",
    )
    all_files = [tmp_path / "service_e/src/api/v1/main.py"]
    known: set[str] = set()  # handler deliberately absent from the symbol graph

    topology = build_service_topology(tmp_path, all_files, [], known)

    assert topology.routes == []
    assert any(g.category == "route_handler" for g in topology.gaps)


def test_commented_out_decorator_is_not_registered(tmp_path):
    _write(
        tmp_path,
        "service_f/src/api/v1/routes.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n\n"
        '# @router.post("/search")\n'
        "# async def search_endpoint(query):\n"
        "#     pass\n",
    )
    all_files = [tmp_path / "service_f/src/api/v1/routes.py"]

    topology = build_service_topology(tmp_path, all_files, [], set())

    assert topology.routes == []


def test_commented_out_apirouter_prefix_is_not_used(tmp_path):
    """Real bug caught live against this repo's own repos.py, which has
    a dead `#router = APIRouter(prefix="/v1", tags=["repos"])` line above
    the real, uncommented `router = APIRouter(tags=["repos"])` -- a
    whole-text regex search finds the commented line first and would
    wrongly extract "/v1" from it (compounding into a real "/v1/v1/..."
    double-prefix once the mount chain's own "/v1" is added on top)."""
    _write(
        tmp_path,
        "service_i/src/api/v1/repos.py",
        "from fastapi import APIRouter\n"
        '#router = APIRouter(prefix="/v1", tags=["repos"])\n'
        'router = APIRouter(tags=["repos"])\n\n\n'
        '@router.get("/repos")\n'
        "async def list_repos():\n"
        "    pass\n",
    )
    _write(
        tmp_path,
        "service_i/src/api/v1/main.py",
        "from fastapi import FastAPI\n"
        "from src.api.v1.repos import router\n"
        "app = FastAPI()\n"
        'app.include_router(router, prefix="/v1")\n',
    )
    all_files = [
        tmp_path / "service_i/src/api/v1/repos.py",
        tmp_path / "service_i/src/api/v1/main.py",
    ]
    known = {"service_i/src/api/v1/repos.py#list_repos"}

    topology = build_service_topology(tmp_path, all_files, [], known)

    assert topology.routes[0].resolved_path == "/v1/repos"


def test_test_directory_files_are_excluded_from_extraction(tmp_path):
    """Real bug caught live: a test file that mounts a real router
    directly on its own throwaway `app = FastAPI()` for isolated route
    testing -- an established pattern in this repo's own test suite
    (test_orient_integration.py, test_orient_passthrough.py,
    test_trace_impact_routes.py) -- is a syntactically valid mount
    registration by every signal this module looks for, and would
    silently override the real application's actual mount chain for
    whatever router it re-mounts, since dict iteration order lets
    whichever file is processed last win."""
    _write(
        tmp_path,
        "service_j/src/api/v1/orient.py",
        "from fastapi import APIRouter\n"
        'router = APIRouter(tags=["orient"])\n\n\n'
        '@router.get("/orient")\n'
        "async def get_orient():\n"
        "    pass\n",
    )
    _write(
        tmp_path,
        "service_j/src/api/v1/__init__.py",
        "from fastapi import APIRouter\n"
        "from src.api.v1.orient import router as orient_router\n"
        'router = APIRouter(prefix="/v1")\n'
        "router.include_router(orient_router)\n",
    )
    _write(
        tmp_path,
        "service_j/src/api/v1/main.py",
        "from fastapi import FastAPI\n"
        "from src.api.v1 import router as v1_router\n"
        "app = FastAPI()\n"
        "app.include_router(v1_router)\n",
    )
    # A throwaway test-only app mounting orient.router directly, with no
    # prefix -- exactly the shape of this repo's own real test fixtures.
    _write(
        tmp_path,
        "service_j/tests/api/test_orient_integration.py",
        "from fastapi import FastAPI\n"
        "from src.api.v1 import orient as orient_module\n"
        "app = FastAPI()\n"
        "app.include_router(orient_module.router)\n",
    )
    all_files = [
        tmp_path / "service_j/src/api/v1/orient.py",
        tmp_path / "service_j/src/api/v1/__init__.py",
        tmp_path / "service_j/src/api/v1/main.py",
        tmp_path / "service_j/tests/api/test_orient_integration.py",
    ]
    known = {"service_j/src/api/v1/orient.py#get_orient"}

    topology = build_service_topology(tmp_path, all_files, [], known)

    assert len(topology.routes) == 1
    assert topology.routes[0].resolved_path == "/v1/orient"


def test_cross_service_call_site_resolves_to_service_node(tmp_path):
    _write(
        tmp_path,
        "service_g/src/core/config.py",
        "class Settings:\n"
        '    INGESTION_SERVICE_URL: str = "http://ingestion_service:8000"\n',
    )
    _write(
        tmp_path,
        "service_g/src/core/service.py",
        "import httpx\n\n\n"
        "async def resolve_repo_id_http(repo_id):\n"
        "    settings = get_settings()\n"
        '    repos_url = f"{settings.INGESTION_SERVICE_URL}/v1/repos"\n'
        "    async with httpx.AsyncClient() as client:\n"
        "        resp = await client.get(repos_url)\n"
        "    return resp\n",
    )

    all_files = [
        tmp_path / "service_g/src/core/config.py",
        tmp_path / "service_g/src/core/service.py",
    ]
    compose_services = [_service_fact("ingestion_service")]

    topology = build_service_topology(tmp_path, all_files, compose_services, set())

    assert len(topology.service_calls) == 1
    call = topology.service_calls[0]
    assert (
        call.caller_canonical_id == "service_g/src/core/service.py#resolve_repo_id_http"
    )
    assert call.target_service_name == "ingestion_service"


def test_call_site_without_http_verb_call_is_not_flagged(tmp_path):
    _write(
        tmp_path,
        "service_h/src/core/config.py",
        'INGESTION_SERVICE_URL = "http://ingestion_service:8000"\n',
    )
    _write(
        tmp_path,
        "service_h/src/core/other.py",
        'def just_builds_a_string():\n    return f"{INGESTION_SERVICE_URL}/v1/repos"\n',
    )
    all_files = [
        tmp_path / "service_h/src/core/config.py",
        tmp_path / "service_h/src/core/other.py",
    ]
    compose_services = [_service_fact("ingestion_service")]

    topology = build_service_topology(tmp_path, all_files, compose_services, set())

    assert topology.service_calls == []


def test_service_topology_to_graph_dicts_shapes(tmp_path):
    _write(
        tmp_path,
        "service_b/src/api/v1/routes.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n\n\n"
        '@router.post("/rag")\n'
        "async def rag_endpoint():\n"
        "    pass\n",
    )
    _write(
        tmp_path,
        "service_b/src/api/v1/main.py",
        "from fastapi import FastAPI\n"
        "from src.api.v1.routes import router\n"
        "app = FastAPI()\n"
        'app.include_router(router, prefix="/v1")\n',
    )
    all_files = [
        tmp_path / "service_b/src/api/v1/routes.py",
        tmp_path / "service_b/src/api/v1/main.py",
    ]
    known = {"service_b/src/api/v1/routes.py#rag_endpoint"}
    compose_services = [_service_fact("service_b")]

    topology = build_service_topology(tmp_path, all_files, compose_services, known)
    nodes, relationships = service_topology_to_graph_dicts(
        "ing-1",
        topology,
        compose_services,
    )

    route_nodes = [n for n in nodes if n["doc_type"] == "route"]
    assert len(route_nodes) == 1
    route_node = route_nodes[0]
    assert route_node["canonical_id"] == "route:service_b:POST:/v1/rag"
    assert route_node["text"] == ""  # never embedded

    handled_by = [r for r in relationships if r["relation_type"] == "HANDLED_BY"]
    assert handled_by == [
        {
            "from_canonical_id": "route:service_b:POST:/v1/rag",
            "to_canonical_id": "service_b/src/api/v1/routes.py#rag_endpoint",
            "relation_type": "HANDLED_BY",
            "relationship_metadata": {},
        }
    ]

    exposes = [r for r in relationships if r["relation_type"] == "EXPOSES_ENDPOINT"]
    assert exposes[0]["from_canonical_id"] == "compose:docker-compose.yml#service_b"
    assert exposes[0]["to_canonical_id"] == "route:service_b:POST:/v1/rag"


def test_service_topology_to_graph_dicts_skips_calls_service_edge_for_unknown_target():
    from src.core.codebase.service_topology import ServiceCallFact, ServiceTopology

    topology = ServiceTopology(
        routes=[],
        service_calls=[
            ServiceCallFact(
                caller_canonical_id="a.py#foo",
                target_service_name="not_a_compose_service",
                matched_url="SOME_URL",
            )
        ],
        gaps=[],
    )
    nodes, relationships = service_topology_to_graph_dicts("ing-1", topology, [])
    assert nodes == []
    assert relationships == []
