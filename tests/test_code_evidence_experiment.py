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
