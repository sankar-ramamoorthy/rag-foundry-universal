import ast
import inspect
import re
from pathlib import Path

from src.retrieval import named_symbol_first as nsf
from src.retrieval.agent_adapter import assemble_context
from src.retrieval.exact_source_preservation import prioritize_exact_sources
from src.retrieval.named_symbol_first import promote_named_symbol_chunks

SERVICE = Path(__file__).resolve().parents[1] / "src/core/service.py"


def _c(label: str, text: str = "body", i: int = 0) -> dict:
    return {
        "canonical_id": label,
        "document_id": label,
        "chunk_id": f"{label}:{i}",
        "chunk_index": i,
        "text": text,
    }


POOL = [
    _c("a/x.py#helper"),
    _c("a/y.py#run_rag"),
    _c("docs/guide.md#run_rag"),
    _c("a/z.py#other"),
    _c("a/y.py#run_rag", "second", 1),
]


def test_named_symbol_chunks_come_first_and_only_order_changes():
    out, trace = promote_named_symbol_chunks(POOL, "What does run_rag do?")
    assert [c["chunk_id"] for c in out[:2]] == [
        "a/y.py#run_rag:0",
        "a/y.py#run_rag:1",
    ]
    assert sorted(map(id, out)) == sorted(map(id, POOL))
    # stable within the rest
    assert [c["chunk_id"] for c in out[2:]] == [
        "a/x.py#helper:0",
        "docs/guide.md#run_rag:0",
        "a/z.py#other:0",
    ]
    assert trace["promoted_chunk_count"] == 2
    assert trace["promoted_labels"] == ["a/y.py#run_rag"]


def test_nothing_named_returns_same_list_object():
    out, trace = promote_named_symbol_chunks(POOL, "how does the pipeline work")
    assert out is POOL
    assert trace["promoted_chunk_count"] == 0


def test_whole_token_case_sensitive_and_method_names():
    pool = [_c("a.py#Agent.run"), _c("b.py#run"), _c("c.py#get")]
    first = promote_named_symbol_chunks(pool, "call run now")[0][0]
    assert first["canonical_id"] == "b.py#run"
    first = promote_named_symbol_chunks(pool, "Agent.run")[0][0]
    assert first["canonical_id"] == "a.py#Agent.run"
    assert promote_named_symbol_chunks(pool, "RUN")[0] is pool
    assert promote_named_symbol_chunks(pool, "running gets")[0] is pool
    assert promote_named_symbol_chunks(pool, "xrun_")[0] is pool


def test_several_named_symbols_promoted_in_pool_order():
    pool = [_c("a.py#z"), _c("b.py#alpha"), _c("c.py#beta"), _c("d.py#q")]
    out, _ = promote_named_symbol_chunks(pool, "beta then alpha")
    assert [c["canonical_id"] for c in out] == [
        "b.py#alpha", "c.py#beta", "a.py#z", "d.py#q",
    ]


def test_labels_without_hash_or_non_python_never_promoted():
    pool = [_c("README.md#run"), _c("a.rs#run"), _c("plain"), _c("a.py#")]
    assert promote_named_symbol_chunks(pool, "run plain")[0] is pool


def test_label_read_from_metadata_like_the_capture_code():
    chunk = {"metadata": {"source_metadata": {"canonical_id": "a.py#f"}}, "text": "t"}
    other = {"canonical_id": "b.py#g", "text": "t"}
    assert promote_named_symbol_chunks([other, chunk], "f")[0][0] is chunk


def test_promotion_changes_what_the_budget_keeps_but_not_the_chunks():
    big = _c("a.py#other", "x" * 200)
    target = _c("b.py#target", "t" * 100)
    pool = [big, target]
    assert target not in assemble_context(pool, 250).chunks
    out, _ = promote_named_symbol_chunks(pool, "target")
    assert target in assemble_context(out, 250).chunks


def test_function_signature_takes_only_chunks_and_query():
    assert list(inspect.signature(promote_named_symbol_chunks).parameters) == [
        "chunks",
        "query",
    ]
    tree = ast.parse(inspect.getsource(nsf))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert {getattr(i, "module", None) or i.names[0].name for i in imports} == {
        "re",
        "typing",
    }
    for forbidden in ("manifest", "get_settings", "trace_canonical_ids", "case_id"):
        assert not any(forbidden in n for n in names)


def test_output_order_is_what_the_exact_source_stage_passes_through():
    # With the stage disabled (the experiment's configuration) it is a no-op,
    # so the allocator sees the mechanism's order.
    out, _ = promote_named_symbol_chunks(POOL, "run_rag")
    same, trace = prioritize_exact_sources(out, "run_rag", 100, enabled=False)
    assert same is out and trace == {}


def test_service_call_site_pins_the_integration_invariant():
    source = SERVICE.read_text(encoding="utf-8")
    assert "enabled=claim_type == \"repository_overview\" and claim_selection" in source
    assert "named_symbol_first: bool = False" in source
    flag = source.index("if named_symbol_first:")
    pool_call = source.index("assemble_context(agent_chunks, 2**63)")
    exact = source.index("agent_chunks, preservation_trace = prioritize_exact_sources(")
    budgeted = source.index("assemble_context(agent_chunks, context_budget)")
    assert pool_call < flag < exact < budgeted
    block = source[flag:exact]
    assert len(re.findall(r"agent_chunks", block)) == 2  # reassignment and call only
