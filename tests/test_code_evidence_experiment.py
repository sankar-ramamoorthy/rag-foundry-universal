"""Guard scoring against attribution errors, duplicate inflation and cap bypass."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "code_evidence", ROOT / "scripts/code_evidence_experiment.py"
)
assert SPEC is not None and SPEC.loader is not None
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)


def test_wrong_component_does_not_satisfy_operation():
    obligations = [experiment.obligation("Call", "real.py#run", "dispatch(x)")]
    wrong = [{"canonical_id": "tests/test_fake.py#run", "text": "dispatch(x)"}]
    assert experiment.coverage(obligations, wrong)["satisfied"] == 0


def test_file_passage_can_support_symbol_but_all_parts_are_required():
    obligations = [
        experiment.obligation("Branch", "real.py#run", "if ready:", "dispatch(x)")
    ]
    chunk = {"canonical_id": "real.py", "text": "dispatch(x)"}
    assert experiment.coverage(obligations, [chunk])["satisfied"] == 0
    chunk["text"] = "if ready:\n    dispatch(x)"
    assert experiment.coverage(obligations, [chunk])["satisfied"] == 1


def test_repeated_source_does_not_inflate_efficiency():
    source = 'result = dispatch("évidence")'
    case = {"target": "real.py#run", "operations": [], "dependencies": []}
    sources = {"real.py#run": {"text": source}}
    chunk = {"canonical_id": "real.py#run", "text": source}
    score = experiment.efficiency(case, sources, [chunk, chunk])
    assert score["unique_relevant_bytes_lower_bound"] == len(source.encode())
    assert score["repeated_relevant_bytes_lower_bound"] == len(source.encode())


def test_frozen_case_definitions_remain_unchanged():
    manifest = experiment.read(experiment.DIRECTORY / "manifest.json")
    assert experiment.definitions() == manifest["cases"]
    checksum = (experiment.DIRECTORY / "manifest.sha256").read_text().strip()
    assert (
        experiment.digest(
            (experiment.DIRECTORY / "manifest.json").read_text(encoding="utf-8")
        )
        == checksum
    )


@pytest.mark.parametrize("context", ["é" * 2049, "a" * 4097])
def test_context_cap_uses_bytes(context):
    case = {"target": "real.py#run"}
    manifest = {"sources": {"real.py#run": {"document_id": "document"}}}
    record = {
        "response": {
            "retrieval_plan": {
                "seed_canonical_ids": [],
                "expanded_canonical_ids": [],
                "seed_document_ids": [],
                "expanded_document_ids": [],
            }
        },
        "final_chunks": [],
        "generation_request": {"context": context},
    }
    with pytest.raises(AssertionError):
        experiment.score(case, manifest, record)


def test_observer_preserves_explicit_deadline_and_restores_methods(
    monkeypatch, tmp_path
):
    import requests

    calls = []

    def original_request(client, method, url, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(requests.sessions.Session, "request", original_request)
    monkeypatch.setattr(experiment, "RESULTS", tmp_path)
    monkeypatch.setattr(experiment, "RAW", tmp_path)
    service = SimpleNamespace(
        assemble_context=lambda chunks, budget: None,
        embed_query=lambda *args, **kwargs: [1.0],
    )
    observed, _, restore = experiment.install_observers(service)
    observed["case_id"] = "unit"
    try:
        client = requests.Session()
        client.request("GET", "http://example.invalid", timeout=(2, 3))
        client.request("GET", "http://example.invalid")
        assert calls == [{"timeout": (2, 3)}, {"timeout": (10, 120)}]
    finally:
        restore()
    assert requests.sessions.Session.request is original_request
    events = [
        json.loads(line)
        for line in (tmp_path / "capture-events.jsonl").read_text().splitlines()
    ]
    assert [event["event"] for event in events] == [
        "sync_http_started",
        "sync_http_completed",
        "sync_http_started",
        "sync_http_completed",
    ]


def test_observer_does_not_change_assembled_selection(monkeypatch, tmp_path):
    result = SimpleNamespace(chunks=[{"text": "original"}], text="original")
    service = SimpleNamespace(
        assemble_context=lambda chunks, budget: result,
        embed_query=lambda *args, **kwargs: [1.0],
    )
    monkeypatch.setattr(experiment, "RESULTS", tmp_path)
    monkeypatch.setattr(experiment, "RAW", tmp_path)
    observed, _, restore = experiment.install_observers(service)
    try:
        assert service.assemble_context([], 4096) is result
        assert observed["final_chunks"] is result.chunks
        assert observed["assembled_context"] == "original"
    finally:
        restore()


DEV_PIN = {
    "source": {"commit_sha": "109f12d83ab83a306318423be618c195f8c4e6ea"},
    "generation": {
        "repo_id": "new-repo",
        "ingestion_id": "new-ing",
        "ingested_commit_sha": "109f12d83ab83a306318423be618c195f8c4e6ea",
    },
}


def _manifest():
    return {
        "cases": [
            {"id": "L1", "repo": "lightrag", "target": "a.py#x"},
            {"id": "F1", "repo": "foundry", "target": "b.py#y"},
        ],
        "pins": {
            "lightrag": {"repo_id": "L", "ingestion_id": "li"},
            "foundry": {
                "repo_id": "old-repo",
                "ingestion_id": "old-ing",
                "commit_sha": "109f12d83ab83a306318423be618c195f8c4e6ea",
            },
        },
        "sources": {"b.py#y": {"document_id": "old-doc", "text": "t"}},
    }


def test_control_retargets_foundry_cases_to_the_clean_corpus():
    manifest = _manifest()
    cases, pins, sources = experiment.control_inputs(
        manifest, DEV_PIN, {"b.py#y": "new-doc"}
    )
    assert [c["id"] for c in cases] == ["F1"]  # L cases are out of scope
    assert pins["foundry"]["repo_id"] == "new-repo"
    assert pins["foundry"]["ingestion_id"] == "new-ing"
    assert sources["b.py#y"]["document_id"] == "new-doc"
    assert sources["b.py#y"]["text"] == "t"  # oracle text unchanged
    # the frozen manifest object is not mutated
    assert manifest["pins"]["foundry"]["repo_id"] == "old-repo"
    assert manifest["sources"]["b.py#y"]["document_id"] == "old-doc"


def test_control_refuses_a_pin_for_a_different_commit():
    bad = json.loads(json.dumps(DEV_PIN))
    bad["generation"]["ingested_commit_sha"] = "deadbeef"
    with pytest.raises(RuntimeError, match="commit"):
        experiment.control_inputs(_manifest(), bad, {"b.py#y": "new-doc"})


def test_control_refuses_when_a_target_is_missing_from_the_new_corpus():
    with pytest.raises(RuntimeError, match="b.py#y"):
        experiment.control_inputs(_manifest(), DEV_PIN, {})


def test_observer_records_the_pre_budget_chunks_and_stays_inert():
    result_big = SimpleNamespace(chunks=["all"], text="big", token_count=9)
    result_cap = SimpleNamespace(chunks=["final"], text="ctx", token_count=3)

    def assemble(chunks, budget):
        return result_big if budget > 4096 else result_cap

    service = SimpleNamespace(assemble_context=assemble, embed_query=lambda *a, **k: [])
    observed, _checkpoint, restore = experiment.install_observers(service)
    try:
        pool = [{"id": 1}, {"id": 2}]
        assert service.assemble_context(pool, 2**63) is result_big
        assert service.assemble_context(pool[:1], 4096) is result_cap
    finally:
        restore()
    assert observed["pre_budget_chunks"] == pool
    assert observed["final_chunks"] == ["final"]
    assert observed["assembled_context"] == "ctx"
