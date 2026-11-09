"""Candidate harness (#323): offline checks only; nothing is executed."""

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "held_out_candidate", ROOT / "scripts/held_out_candidate.py"
)
assert SPEC and SPEC.loader
hcand = importlib.util.module_from_spec(SPEC)
sys.modules["held_out_candidate"] = hcand
SPEC.loader.exec_module(hcand)
hc = hcand.hc


def test_spec_hash_matches_recorded_file():
    text = hcand.SPEC_FILE.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == hcand.spec_sha256()


def test_candidate_arguments_are_control_plus_one_switch_and_no_claim_type():
    inputs = hc.load_inputs()
    case = inputs.cases[0]
    entry = inputs.pin["repositories"][case["repo"]]
    control = hc.rag_arguments(case, entry)
    cand = hcand.candidate_arguments(case, entry)
    assert cand == {**control, "named_symbol_first": True}
    assert "claim_type" not in cand
    assert cand["repository_overview_claim_selection_enabled"] is False


def test_candidate_paths_never_collide_with_control():
    assert hcand.candidate_path("H1").name == "held-out-candidate-H1.json"
    assert hcand.candidate_path("H1") != hc.capture_path(1, "H1")


def test_captures_refuse_overwrite(tmp_path):
    path = tmp_path / "held-out-candidate-H1.json"
    hc.write_capture(path, {"a": 1})
    with pytest.raises(FileExistsError):
        hc.write_capture(path, {"a": 2})


def test_run_requires_confirmation_and_authorization_ref(capsys):
    assert hcand.main(["run", "--host", "http://example.invalid"]) == 1
    assert (
        hcand.main(
            ["run", "--host", "http://example.invalid", "--execute-frozen-questions"]
        )
        == 1
    )
    assert "owner-authorization-ref" in capsys.readouterr().err


@pytest.fixture
def config(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "candidate_test_config", ROOT / "rag_orchestrator/src/core/config.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in list(os.environ):
        if name.upper() in module.Settings.model_fields:
            monkeypatch.delenv(name)
    return module


@pytest.fixture
def contract():
    return json.loads(hc.CONTRACT.read_text())


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MAX_EXPANDED_DOCS", "21"),
        ("EXPANDED_DOC_CHUNKS", "4"),
        ("MAX_TOTAL_CHUNKS", "51"),
        ("OLLAMA_EMBED_MODEL", "different-model"),
        ("EMBEDDING_PROVIDER", "openai"),
        ("DOC_TYPE_TIE_BREAK_ENABLED", "true"),
        ("CONTEXT_WINDOW_TOKENS", "16384"),
    ],
)
def test_effective_environment_drift_is_rejected(
    config, contract, monkeypatch, name, value
):
    monkeypatch.setenv(name, value)
    with pytest.raises(hcand.CandidateError, match=name):
        hcand.checked_settings(config, contract, "http://example.invalid")


def test_dotenv_is_disabled_as_in_control(config, contract, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MAX_EXPANDED_DOCS=99\nMAX_TOTAL_CHUNKS=99\n")
    settings = hcand.checked_settings(config, contract, "http://example.invalid")
    assert settings.MAX_EXPANDED_DOCS == contract["max_expanded_docs"]
    assert settings.MAX_TOTAL_CHUNKS == contract["adapter_max_total_chunks"]


def test_frozen_contract_caps_override_defaults_in_validation(config, contract):
    contract["adapter_max_total_chunks"] = 49
    with pytest.raises(hcand.CandidateError, match="MAX_TOTAL_CHUNKS"):
        hcand.checked_settings(config, contract, "http://example.invalid")


@pytest.fixture
def runtime(monkeypatch):
    state = {"commit": "a" * 40, "tracked_changes": False}
    monkeypatch.setattr(hc, "runtime_state", lambda: dict(state))
    monkeypatch.setattr(hcand.subprocess, "check_output", lambda *a, **k: b"")
    return state


@pytest.mark.parametrize("approved", ["", "a" * 7, "z" * 40, "b" * 40])
def test_invalid_or_wrong_approved_commit_is_rejected(runtime, approved):
    with pytest.raises(hcand.CandidateError):
        hcand.checked_runtime(approved)


def test_dirty_tracked_sources_are_rejected(runtime):
    runtime["tracked_changes"] = True
    with pytest.raises(hcand.CandidateError, match="clean tracked HEAD"):
        hcand.checked_runtime("a" * 40)


def test_unexpected_untracked_sources_are_rejected(runtime, monkeypatch):
    monkeypatch.setattr(
        hcand.subprocess, "check_output", lambda *a, **k: b"scripts/shadow.py\0"
    )
    with pytest.raises(hcand.CandidateError, match="unexpected untracked"):
        hcand.checked_runtime("a" * 40)


def test_known_prototypes_are_disclosed_and_preserved(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(hcand, "ROOT", tmp_path)
    for name in hcand.ALLOWED_UNTRACKED:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"synthetic prototype\n")
    output = "\0".join(sorted(hcand.ALLOWED_UNTRACKED)) + "\0"
    monkeypatch.setattr(
        hcand.subprocess, "check_output", lambda *a, **k: output.encode()
    )
    state = hcand.checked_runtime("a" * 40)
    for name in hcand.ALLOWED_UNTRACKED:
        assert (tmp_path / name).read_bytes() == b"synthetic prototype\n"
        assert (
            state["untracked_files_sha256"][name]
            == hashlib.sha256(b"synthetic prototype\n").hexdigest()
        )


@pytest.fixture
def evidence_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(hcand, "ROOT", tmp_path)
    monkeypatch.setattr(hc, "RAW", tmp_path / "ignored-evidence")
    monkeypatch.setattr(
        hcand.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0)
    )
    return hc.RAW


def test_attempt_is_exclusive_and_survives_interruption(evidence_dir, monkeypatch):
    synced = []
    monkeypatch.setattr(hcand.os, "fsync", lambda fd: synced.append(fd))
    evidence = {
        "approved_candidate_commit": "a" * 40,
        "mechanism_spec_sha256": "b" * 64,
    }
    path = hcand.reserve_attempt(evidence)
    assert json.loads(path.read_text()) == evidence
    assert synced
    # No case capture exists yet: even an immediate interruption consumes it.
    with pytest.raises(KeyboardInterrupt):
        raise KeyboardInterrupt
    with pytest.raises(hcand.CandidateError, match="no retry"):
        hcand.reserve_attempt(evidence)
    assert json.loads(path.read_text()) == evidence
    assert path in hcand.existing_candidate_captures()


def test_attempt_survives_failed_durable_write(evidence_dir, monkeypatch):
    def fail(fd):
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(hcand.os, "fsync", fail)
    with pytest.raises(OSError, match="fsync"):
        hcand.reserve_attempt({"synthetic": True})
    with pytest.raises(hcand.CandidateError, match="no retry"):
        hcand.reserve_attempt({})


def test_attempt_refuses_nonignored_storage(evidence_dir, monkeypatch):
    monkeypatch.setattr(
        hcand.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1)
    )
    with pytest.raises(hcand.CandidateError, match="git-ignored"):
        hcand.reserve_attempt({})
    assert not evidence_dir.exists()


def test_concurrent_attempts_have_exactly_one_winner(evidence_dir):
    from concurrent.futures import ThreadPoolExecutor

    def reserve():
        try:
            hcand.reserve_attempt({"synthetic": True})
            return "reserved"
        except hcand.CandidateError:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(results) == ["refused", "reserved"]


def test_candidate_events_and_captures_leave_control_evidence_untouched(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(hc, "RAW", tmp_path)
    controls = [
        tmp_path / "capture-events.jsonl",
        hc.capture_path(1, "synthetic"),
        hc.capture_path(2, "synthetic"),
        tmp_path / "held-out-control-summary.json",
    ]
    for path in controls:
        path.write_bytes(b"original control evidence\n")
    service = SimpleNamespace(
        assemble_context=lambda *a: None, embed_query=lambda *a: None
    )
    observed, checkpoint, restore = hcand.candidate_observers(service)
    try:
        observed["case_id"] = "synthetic"
        checkpoint("case_started", run=1)
        hc.write_capture(hcand.candidate_path("synthetic"), {"synthetic": True})
    finally:
        restore()
    assert all(p.read_bytes() == b"original control evidence\n" for p in controls)
    event = json.loads(
        (tmp_path / "held-out-candidate-events/capture-events.jsonl").read_text()
    )
    assert event["case"] == "synthetic"


def test_cli_requires_approved_sha_even_with_authorization(capsys):
    assert (
        hcand.main(
            [
                "run",
                "--host",
                "http://example.invalid",
                "--execute-frozen-questions",
                "--owner-authorization-ref",
                "synthetic approval",
            ]
        )
        == 1
    )
    assert "approved-candidate-commit" in capsys.readouterr().err


@pytest.fixture
def synthetic_run(config, contract, tmp_path, monkeypatch):
    """A fully fake runtime: no held-out questions, pools or network access."""
    import httpx

    monkeypatch.setattr(hc, "RAW", tmp_path)
    state = {"commit": "a" * 40, "tracked_changes": False}
    monkeypatch.setattr(hcand, "checked_runtime", lambda approved: dict(state))
    generation = {
        "generation_status": "ready",
        "ingestion_id": "synthetic-ingestion",
        "commit_sha": "b" * 40,
        "is_incremental": False,
    }
    entry = {
        "repo_id": "synthetic-repo",
        "ingestion_id": generation["ingestion_id"],
        "generation": {"ingested_commit_sha": {"value": generation["commit_sha"]}},
    }
    case = {
        "id": "synthetic",
        "repo": "demo",
        "query": "explain f",
        "primary_function": "demo.py#f",
        "operations": [],
        "dependencies": [],
    }
    inputs = SimpleNamespace(
        contract=contract,
        cases=[case],
        pin={"repositories": {"demo": entry}},
        manifest_sha256="c" * 64,
    )
    calls = []

    async def run_rag(**kwargs):
        assert (tmp_path / "held-out-candidate-attempt.json").exists()
        calls.append(kwargs)
        if service.interrupt:
            raise KeyboardInterrupt
        chunks = [{"canonical_id": "demo.py#f", "text": "ctx"}]
        service.assemble_context(chunks, 2**63)
        service.assemble_context(chunks, 4096)
        return SimpleNamespace(
            model_dump=lambda **k: {
                "retrieval_plan": {"tokens_after_budget": 3},
            }
        )

    service: Any = SimpleNamespace(
        run_rag=run_rag,
        interrupt=False,
        assemble_context=lambda chunks, budget: SimpleNamespace(
            chunks=chunks, text="ctx"
        ),
        embed_query=lambda *a: None,
    )
    # Inject only fake service/config modules; from-import uses this alias too.
    monkeypatch.setitem(sys.modules, "src.core.config", config)
    monkeypatch.setitem(sys.modules, "src.core.service", service)
    monkeypatch.setitem(
        sys.modules, "rag_orchestrator.src.core", SimpleNamespace(config=config)
    )
    monkeypatch.setattr(hc, "check_all_generations", lambda *a: {})

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            assert url.endswith("/generation")
            return SimpleNamespace(json=lambda: dict(generation))

    async def versions(*args):
        return {"synthetic-service": "synthetic-version"}

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    # Real observers require this attribute, but no post may be called.
    monkeypatch.setattr(Client, "post", None, raising=False)
    monkeypatch.setattr(
        hc, "_experiment", lambda: SimpleNamespace(fetch_versions=versions)
    )
    monkeypatch.setattr(
        hcand.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0)
    )
    # Use a real exclusive/fsynced reservation in temporary evidence storage.
    original_reserve = hcand.reserve_attempt

    def reserve(evidence):
        with monkeypatch.context() as context:
            context.setattr(hcand, "ROOT", tmp_path)
            return original_reserve(evidence)

    monkeypatch.setattr(hcand, "reserve_attempt", reserve)
    # Restore global logging and sys.path even when simulating an interruption.
    monkeypatch.setattr(hcand.logging, "disable", lambda *a: None)
    monkeypatch.setattr(sys, "path", list(sys.path))
    args = SimpleNamespace(
        host="http://example.invalid",
        approved_candidate_commit="a" * 40,
        owner_authorization_ref="synthetic approval",
    )
    return SimpleNamespace(
        args=args,
        inputs=inputs,
        calls=calls,
        service=service,
        path=tmp_path,
    )


def test_synthetic_execution_records_identity_and_configuration(synthetic_run):
    import asyncio

    run = synthetic_run
    assert asyncio.run(hcand.run_candidate(run.args, run.inputs)) == 0
    assert len(run.calls) == 1
    for name in (
        "held-out-candidate-attempt.json",
        "held-out-candidate-synthetic.json",
        "held-out-candidate-summary.json",
    ):
        evidence = json.loads((run.path / name).read_text())
        assert evidence["approved_candidate_commit"] == "a" * 40
        assert evidence["candidate_commit"] == "a" * 40
        assert evidence["mechanism_spec_sha256"] == hcand.spec_sha256()
        assert evidence["owner_authorization_ref"] == "synthetic approval"
        assert evidence["effective_settings"]["MAX_TOTAL_CHUNKS"] == 50


def test_interrupted_synthetic_query_blocks_second_execution(synthetic_run):
    import asyncio

    run = synthetic_run
    run.service.interrupt = True
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(hcand.run_candidate(run.args, run.inputs))
    assert (run.path / "held-out-candidate-attempt.json").exists()
    with pytest.raises(hcand.CandidateError, match="single-shot"):
        asyncio.run(hcand.run_candidate(run.args, run.inputs))
    assert len(run.calls) == 1


def test_conflicting_environment_stops_before_attempt_or_query(
    synthetic_run, monkeypatch
):
    import asyncio

    run = synthetic_run
    monkeypatch.setenv("MAX_TOTAL_CHUNKS", "99")
    with pytest.raises(hcand.CandidateError, match="MAX_TOTAL_CHUNKS"):
        asyncio.run(hcand.run_candidate(run.args, run.inputs))
    assert not list(run.path.iterdir())
    assert not run.calls
