"""Unit tests for the pure parts of scripts/discovery_diagnostic_342.py (#342)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import discovery_diagnostic_342 as d  # noqa: E402


@pytest.fixture(scope="module")
def cq():
    return d.import_orchestrator()[0]


def _graph(cq, edges, extra=()):
    graph = cq.CodebaseGraph()
    for cid in {c for e in edges for c in e[:2]} | set(extra):
        graph.add_node(cq.Node(cid, cid.split("#")[0]))
    for frm, to, rel in edges:
        graph.add_edge(frm, to, rel)
    return graph


def test_tokens_split_identifiers_like_the_orchestrator():
    assert d.tokens("hybrid_retrieve OllamaEmbedder /v1/rag") == [
        "hybrid",
        "retrieve",
        "ollama",
        "embedder",
        "v1",
        "rag",
    ]


def test_route_anchor_comes_from_question_text_only(cq):
    route = "route:svc:POST:/v1/rag"
    graph = _graph(cq, [], extra=[route, "route:svc:POST:/v1/rag/simple"])
    anchors = d.route_anchors("Trace the path from POST /v1/rag through it.", graph)
    assert anchors == [{"method": "POST", "path": "/v1/rag", "matches": [route]}]
    assert d.route_anchors("How does retrieval work?", graph) == []


def test_src_placeholder_rule_resolves_only_existing_service_local_symbols(cq):
    caller = "svc/src/api/routes.py#endpoint"
    target = "svc/src/core/service.py#run"
    graph = _graph(cq, [], extra=[caller, target])
    rule = d.resolve_src_placeholder
    assert rule(graph, caller, "EXTERNAL_SYMBOL:src.core.service.run") == target
    assert rule(graph, caller, "EXTERNAL_SYMBOL:src.core.service.missing") is None
    assert rule(graph, caller, "EXTERNAL_SYMBOL:logger.info") is None


def test_hop_representation_distinguishes_exact_placeholder_and_absent(cq):
    a, b, c = "p.py#a", "p.py#b", "p.py#c"
    graph = _graph(cq, [(a, b, "CALL"), (b, "EXTERNAL_SYMBOL:x.c", "CALL")], [c])
    assert d.hop_representation(graph, a, b, "direct") == {
        "graph": "exact",
        "relation": "CALL",
    }
    assert d.hop_representation(graph, b, c, "dispatch")["graph"] == "placeholder"
    assert d.hop_representation(graph, a, c, "indirect") == {"graph": "absent"}


def test_scoring_tables_are_consistent():
    for _, frm, to, kind, _ in d.HOPS:
        assert frm in d.TARGETS
        assert to is None or to in d.TARGETS
        assert kind in {"route", "direct", "indirect", "dispatch", "http", "sql"}
