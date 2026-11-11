"""CI-01 investigation only: execute source definitions with synthetic seams.

Run from repository root with Python. No application import, network, database,
corpus access or source mutation. This models interleavings; it is not a live
PostgreSQL reproduction. AST selection executes unchanged current definitions.
"""

import ast
from collections import OrderedDict, defaultdict, deque
import json
import logging
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Dict, List, Optional, Set, Tuple
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[2]


def definitions(relative_path, names, namespace):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    selected = [node for node in tree.body if getattr(node, "name", None) in names]
    assert len(selected) == len(names), (relative_path, names)
    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(module, relative_path, "exec"), namespace)


def graph_namespace():
    ns = dict(globals())
    ns.update(Dict=Dict, List=List, Optional=Optional, Set=Set, Tuple=Tuple,
              defaultdict=defaultdict, deque=deque)
    ns["logger"] = logging.getLogger("ci01-probe")
    definitions(
        "rag_orchestrator/src/retrieval/codebase_queries.py",
        {"Node", "CodebaseGraph", "load_graph_for_repo"}, ns,
    )
    ns.update(_repo_graphs=OrderedDict(), _repo_graphs_lock=threading.Lock(),
              _CACHE_MAX_REPOS=32)
    definitions(
        "rag_orchestrator/src/retrieval/codebase_utils.py",
        {"get_cached_graph_with_generation"}, ns,
    )
    return ns


def cache_probe(payload):
    ns = graph_namespace()
    ns["get_repo_generation"] = lambda repo: ("generation-A", "ready")
    ns["get_full_graph_from_api"] = lambda repo: payload
    generation, graph = ns["get_cached_graph_with_generation"]("synthetic-repo")
    return {"returned_generation": generation, "nodes": sorted(graph.nodes),
            "cached_generation": ns["_repo_graphs"]["synthetic-repo"][0]}


def database_probe(nodes):
    # Query rows are already detached synthetic values. The second query models
    # a later committed edge set, while surviving document IDs stay unchanged.
    edge = SimpleNamespace(from_document_id="id-x", to_document_id="id-y",
                           relation_type="CALL", relationship_metadata={"probe": "B"})
    node_query = MagicMock()
    node_query.filter.return_value.all.return_value = nodes
    edge_query = MagicMock()
    edge_query.filter.return_value.all.return_value = [edge]
    session = MagicMock()
    session.query.side_effect = [node_query, edge_query]
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    ns = dict(globals())
    ns.update(logger=logging.getLogger("ci01-probe"), SessionLocal=factory,
              resolve_current_generation=lambda repo: "generation-A",
              generation_status=lambda repo: "building",
              DocumentNode=MagicMock(), DocumentRelationship=MagicMock())
    definitions("ingestion_service/src/core/db_utils.py",
                {"get_full_graph_for_repo"}, ns)
    result = ns["get_full_graph_for_repo"]("synthetic-repo")
    return {"status": result["generation_status"],
            "node_generations": sorted({
                n.ingestion_id for n in result["nodes"].values()}),
            "relationships": result["relationships"],
            "query_count": session.query.call_count}


def main():
    payload_b = {"generation_status": "ready", "nodes": [
        {"canonical_id": "B-only", "relative_path": "b.py"}], "relationships": {}}
    mislabeled = cache_probe(payload_b)
    assert mislabeled["returned_generation"] == "generation-A"
    assert mislabeled["nodes"] == ["B-only"]
    not_ready = cache_probe({"generation_status": "building", "nodes": [],
                             "relationships": {}})
    assert not_ready["cached_generation"] == "generation-A"
    nodes = [SimpleNamespace(canonical_id=cid, document_id=doc,
                             ingestion_id="generation-A")
             for cid, doc in [("x", "id-x"), ("y", "id-y")]]
    mixed = database_probe(nodes)
    assert mixed["node_generations"] == ["generation-A"]
    assert mixed["relationships"]["x"][0]["relationship_metadata"]["probe"] == "B"
    vanished = database_probe([])
    assert vanished["status"] == "ready" and vanished["query_count"] == 1
    print(json.dumps({"cache_A_label_B_content": mislabeled,
                      "building_export_cached_under_A": not_ready,
                      "A_nodes_B_edges_scripted": mixed,
                      "owner_A_then_no_nodes": vanished}, indent=2))


if __name__ == "__main__":
    main()
