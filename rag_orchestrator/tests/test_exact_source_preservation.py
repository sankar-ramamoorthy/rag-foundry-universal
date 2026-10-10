from src.retrieval.agent_adapter import assemble_context, build_sources
from src.retrieval.exact_source_preservation import prioritize_exact_sources


def _chunk(canonical_id: str, text: str, index: int = 0) -> dict:
    return {
        "canonical_id": canonical_id,
        "document_id": canonical_id,
        "chunk_id": f"{canonical_id}:{index}",
        "chunk_index": index,
        "text": text,
    }


def test_c2_fixture_readme_survives_final_budget():
    competing = _chunk("specs/plan.md#overview", "a" * 105)
    fixture = _chunk(
        "shared/smoke_repo/README.md#smoke_repo_live_smoke_test_fixture",
        "The smoke repository is a live smoke test fixture.",
    )
    chunks = [competing, fixture]
    assert fixture not in assemble_context(chunks, 160).chunks
    ordered, trace = prioritize_exact_sources(
        chunks, "What is `shared/smoke_repo` used for?", 160
    )
    final = assemble_context(ordered, 160)
    assert fixture in final.chunks
    assert fixture["canonical_id"] in build_sources(final.chunks)
    assert trace["exact_source_preservation"][0]["status"] == "preserved"


def test_c3_exact_method_precedes_containing_class():
    containing_class = _chunk(
        "ingestion_service/src/core/codebase/graph_assembler.py#GraphAssembler",
        "a" * 110,
    )
    method = _chunk(
        "ingestion_service/src/core/codebase/graph_assembler.py#GraphAssembler.assemble",
        "assemble resolves calls, imports, inheritance, and documentation links",
    )
    chunks = [containing_class, method]
    assert method not in assemble_context(chunks, 220).chunks
    ordered, trace = prioritize_exact_sources(
        chunks, "What does `GraphAssembler.assemble` do?", 220
    )
    final = assemble_context(ordered, 220)
    assert final.chunks[0] is method
    assert method["canonical_id"] in build_sources(final.chunks)
    assert trace["exact_source_preservation"][0]["status"] == "preserved"


def test_method_stays_first_when_question_also_names_its_file():
    containing_class = _chunk("src/graph.py#GraphAssembler", "class")
    method = _chunk("src/graph.py#GraphAssembler.assemble", "method")
    ordered, _ = prioritize_exact_sources(
        [containing_class, method],
        "What does `src/graph.py#GraphAssembler.assemble` do?",
        500,
    )
    assert ordered[0] is method


def test_unrelated_query_keeps_original_order():
    chunks = [_chunk("a.py#A", "A"), _chunk("b.py#B", "B")]
    ordered, trace = prioritize_exact_sources(chunks, "What is this repository?", 50)
    assert ordered is chunks
    assert trace == {}


def test_root_file_path_is_explicit_source():
    competing = _chunk("DOCS/notes.md#overview", "a" * 100)
    root_file = _chunk("docker-compose.yml", "services:")
    ordered, trace = prioritize_exact_sources(
        [competing, root_file], "Check `docker-compose.yml`", 150
    )
    assert ordered[0] is root_file
    assert trace["exact_source_preservation"][0]["status"] == "preserved"


def test_frozen_q1_to_q4_queries_keep_existing_context_selection():
    queries = [
        "I need information about the repo structure.",
        "Describe the actual directory, service, and package structure of "
        "this repository.",
        "Describe the actual directory, service, and package structure of "
        "rag-foundry-universal.",
        "Give me an architectural map of this repository.",
    ]
    chunks = [_chunk("a.py#A", "A"), _chunk("b.py#B", "B")]
    for query in queries:
        ordered, trace = prioritize_exact_sources(chunks, query, 50)
        assert ordered is chunks
        assert trace == {}


def test_multiple_targets_get_one_passage_each_before_extra_passages():
    a0 = _chunk("src/a.py#A.run", "a", 0)
    a1 = _chunk("src/a.py#A.run", "b", 1)
    b0 = _chunk("src/b.py#B.run", "c", 0)
    ordered, _ = prioritize_exact_sources(
        [a0, a1, b0], "Compare A.run and B.run", 500
    )
    assert ordered == [a0, b0, a1]
    budget = assemble_context([a0, b0], 500).token_count
    assert assemble_context(ordered, budget).chunks == [a0, b0]


def test_ambiguous_symbol_and_oversized_chunk_do_not_take_priority():
    other = _chunk("README.md#overview", "short")
    a = _chunk("src/a.py#A.run", "a")
    b = _chunk("src/b.py#A.run", "b")
    ordered, trace = prioritize_exact_sources(
        [other, a, b], "What does A.run do?", 100
    )
    assert ordered == [other, a, b]
    assert trace["exact_source_preservation"][0]["status"] == "ambiguous"

    huge = _chunk("src/a.py#A.run", "x" * 500)
    ordered, trace = prioritize_exact_sources(
        [other, huge], "What does A.run do?", 100
    )
    assert ordered == [other, huge]
    assert trace["exact_source_preservation"][0]["status"] == "too_large"


def test_unavailable_target_and_disabled_policy_leave_selection_unchanged():
    chunks = [_chunk("README.md#overview", "short")]
    ordered, trace = prioritize_exact_sources(chunks, "What does A.run do?", 100)
    assert ordered == chunks
    assert trace["exact_source_preservation"][0]["status"] == "unavailable"
    ordered, trace = prioritize_exact_sources(
        chunks, "What does A.run do?", 100, enabled=False
    )
    assert ordered is chunks
    assert trace == {}
