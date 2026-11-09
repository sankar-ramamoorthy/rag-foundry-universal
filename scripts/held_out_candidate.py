"""E1 named-symbol-first candidate harness (issue #323).

Runs the 12 frozen held-out cases ONCE through the runtime with
named_symbol_first=True. It shares the control harness preflight, settings,
observers and validation (scripts/held_out_control.py) and differs only in the
one extra run_rag argument. Captures are `held-out-candidate-*`, created in
`x` mode (never overwriting, never touching the control files), and record
the candidate commit and the frozen mechanism-spec hash.

    python scripts/held_out_candidate.py plan --host H
    python scripts/held_out_candidate.py run --host H \
        --execute-frozen-questions --owner-authorization-ref <approval> \
        --approved-candidate-commit <full-sha>

`run` needs a separate, explicit owner approval (#323): exactly one execution,
no retries, no partial reruns, no fixing in place. It refuses a dirty tracked
tree (there is no --allow-dirty) and refuses to start if ANY candidate capture
already exists. The durable attempt marker must never be deleted to retry.
Untracked files are rejected except the two pre-existing, unused prototype
files listed below; their hashes are recorded. Ignored environment/cache files
are not source attestations. Dotenv loading is disabled, as in the control.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "held_out_control", ROOT / "scripts/held_out_control.py"
)
assert _spec and _spec.loader
hc = importlib.util.module_from_spec(_spec)
sys.modules["held_out_control"] = hc
_spec.loader.exec_module(hc)

SPEC_FILE = hc.HELD_OUT / "mechanism-spec-named-symbol-first.md"
SPEC_SHA_FILE = hc.HELD_OUT / "mechanism-spec-named-symbol-first.sha256"
ALLOWED_UNTRACKED = {
    "scripts/code_evidence_prototypes.py",
    "tests/test_code_evidence_prototypes.py",
}


class CandidateError(hc.HarnessError):
    pass


def spec_sha256() -> str:
    """Hash of the frozen spec's LF content, checked against the recorded one."""
    digest = hashlib.sha256(SPEC_FILE.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if digest != SPEC_SHA_FILE.read_text().strip():
        raise CandidateError("mechanism spec does not match its recorded sha256")
    return digest


def candidate_path(case_id: str) -> Path:
    return hc.RAW / f"held-out-candidate-{case_id}.json"


def incomplete_path(case_id: str) -> Path:
    return hc.RAW / f"held-out-candidate-incomplete-{case_id}.json"


def existing_candidate_captures() -> list[Path]:
    return sorted(hc.RAW.glob("held-out-candidate-*")) if hc.RAW.exists() else []


def candidate_arguments(case: dict, entry: dict) -> dict:
    """The control arguments plus the one candidate switch; no claim_type."""
    arguments = hc.rag_arguments(case, entry)
    if "claim_type" in arguments:
        raise CandidateError("claim_type must not be passed (spec section 3)")
    return {**arguments, "named_symbol_first": True}


def checked_runtime(approved_commit: str) -> dict:
    """Attest tracked sources and disclose the two unrelated prototype files."""
    if not re.fullmatch(r"[0-9a-f]{40}", approved_commit or ""):
        raise CandidateError("approved candidate commit must be a full lowercase SHA")
    state = hc.runtime_state()
    if state["tracked_changes"] or state["commit"] != approved_commit:
        raise CandidateError(
            "clean tracked HEAD must equal the approved candidate commit"
        )
    output = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode("utf-8")
    untracked = set(filter(None, output.split("\0")))
    if untracked - ALLOWED_UNTRACKED:
        raise CandidateError("unexpected untracked files: " + str(sorted(untracked)))
    state["untracked_files_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in sorted(untracked)
    }
    return state


def checked_settings(config: Any, contract: dict, host: str) -> Any:
    """Check every resolved field, including environment overrides, before use.

    Config defaults are unchanged from the control checkout. Explicit frozen
    contract values take precedence over those defaults. No dotenv is loaded.
    """
    endpoints = {
        "OLLAMA_BASE_URL": f"{host}:11434",
        "INGESTION_SERVICE_URL": f"{host}:8001",
        "VECTOR_STORE_URL": f"{host}:8002",
        "LLM_SERVICE_URL": f"{host}:8003",
    }
    settings = config.Settings(_env_file=None, **endpoints)
    expected = {
        name: field.get_default(call_default_factory=True)
        for name, field in config.Settings.model_fields.items()
    }
    expected.update(endpoints)
    expected.update(
        MAX_EXPANDED_DOCS=contract["max_expanded_docs"],
        EXPANDED_DOC_CHUNKS=contract["expanded_doc_chunks"],
        MAX_TOTAL_CHUNKS=contract["adapter_max_total_chunks"],
        OLLAMA_EMBED_MODEL="mxbai-embed-large:latest",
        EMBEDDING_PROVIDER="ollama",
    )
    if not any(m["name"] == expected["OLLAMA_EMBED_MODEL"] for m in contract["models"]):
        raise CandidateError("embedding model absent from the frozen contract")
    differing = [
        name for name, value in expected.items() if getattr(settings, name) != value
    ]
    if differing:
        raise CandidateError(
            "effective settings differ from E1: " + ", ".join(differing)
        )
    return settings


def reserve_attempt(evidence: dict) -> Path:
    """Exclusive durable reservation, retained even if the process is interrupted."""
    path = hc.RAW / "held-out-candidate-attempt.json"
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", relative], cwd=ROOT, check=False
    )
    if ignored.returncode != 0:
        raise CandidateError("attempt marker must be in git-ignored evidence storage")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise CandidateError("candidate attempt already reserved; no retry") from error
    if os.name == "posix":
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return path


def candidate_observers(service: Any) -> Any:
    # A separate module instance prevents altering the control observer's RAW.
    spec = importlib.util.spec_from_file_location(
        "candidate_observers", ROOT / "scripts/code_evidence_experiment.py"
    )
    assert spec and spec.loader
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RAW = hc.RAW / "held-out-candidate-events"
    return module.install_observers(service)


async def run_candidate(args: argparse.Namespace, inputs: Any) -> int:
    import httpx

    spec_hash = spec_sha256()
    state = checked_runtime(args.approved_candidate_commit)
    if existing_candidate_captures():
        raise CandidateError("candidate captures exist; this run is single-shot")
    hc.check_settings(inputs.contract, hc.RUN_SETTINGS)
    hc.check_all_generations(inputs, args.host)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    config: Any = importlib.import_module("src.core.config")
    from rag_orchestrator.src.core import config as package_config

    settings = checked_settings(config, inputs.contract, args.host)
    config.get_settings = lambda: settings
    package_config.get_settings = lambda: settings
    service: Any = importlib.import_module("src.core.service")
    # Finish read-only preflight before consuming the single attempt. No query
    # or observer output is allowed before the durable reservation succeeds.
    async with httpx.AsyncClient(timeout=30) as client:
        versions = await hc._experiment().fetch_versions(client, args.host)
    if checked_runtime(args.approved_candidate_commit) != state:
        raise CandidateError("runtime changed during preflight")
    evidence = {
        "candidate_commit": state["commit"],
        "approved_candidate_commit": args.approved_candidate_commit,
        "mechanism_spec_sha256": spec_hash,
        "owner_authorization_ref": args.owner_authorization_ref,
        "manifest_sha256": inputs.manifest_sha256,
        "effective_settings": settings.model_dump(mode="json"),
        "runtime": state,
        "versions": versions,
        "reserved_at": datetime.now(timezone.utc).isoformat(),
    }
    reserve_attempt(evidence)
    observed, checkpoint, restore = candidate_observers(service)
    logging.disable(logging.CRITICAL)
    summaries: dict[str, dict] = {}
    try:
        for case in inputs.cases:
            entry = inputs.pin["repositories"][case["repo"]]
            url = f"{args.host}:8001/v1/repos/{entry['repo_id']}/generation"
            observed.clear()
            observed.update(
                **evidence,
                case_id=case["id"],
                mode="candidate-named-symbol-first",
                captured_at=datetime.now(timezone.utc).isoformat(),
                run_settings=dict(hc.RUN_SETTINGS),
                model=hc.MODEL,
            )
            async with httpx.AsyncClient(timeout=30) as client:
                before = (await client.get(url)).json()
            hc.check_generation(entry, before)
            observed["generation_before"] = before
            print(f"candidate {case['id']}: capturing", flush=True)
            checkpoint("case_started", run=1)
            try:
                response = await service.run_rag(**candidate_arguments(case, entry))
                observed["response"] = response.model_dump(mode="json")
                async with httpx.AsyncClient(timeout=30) as client:
                    after = (await client.get(url)).json()
                if after != before:
                    raise hc.HarnessError(f"{case['id']}: generation changed mid-run")
                observed["generation_after"] = after
                hc.validate_record(observed, hc.RUN_SETTINGS["max_total_tokens"])
            except Exception as error:
                hc.write_capture(
                    incomplete_path(case["id"]),
                    {
                        **observed,
                        "status": "incomplete-no-summary",
                        "error": repr(error),
                    },
                )
                # No retry and no continuation: an incomplete execution is
                # reported as such; a re-run needs a new owner decision.
                raise CandidateError(f"{case['id']} failed: {error!r}") from error
            summary = hc.summarize_record(case, observed)
            observed["summary"] = summary
            hc.write_capture(candidate_path(case["id"]), observed)
            summaries[case["id"]] = summary
            print(case["id"], summary["context_sha256"])
    finally:
        restore()
    hc.write_capture(
        hc.RAW / "held-out-candidate-summary.json",
        {
            **evidence,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "cases": summaries,
        },
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "run"))
    parser.add_argument("--host", default=os.environ.get("E1_HOST"))
    parser.add_argument("--execute-frozen-questions", action="store_true")
    parser.add_argument("--owner-authorization-ref")
    parser.add_argument("--approved-candidate-commit")
    args = parser.parse_args(argv)
    try:
        inputs = hc.load_inputs()
        print("mechanism spec sha256", spec_sha256())
        if args.command == "plan":
            print("\n".join(hc.plan_lines(inputs, runs=1)))
            if args.host:
                hc.check_services(args.host)
                hc.check_all_generations(inputs, args.host)
                print("services up; all pinned generations ready and matching")
            return 0
        if not (
            args.execute_frozen_questions
            and args.owner_authorization_ref
            and args.owner_authorization_ref.strip()
            and args.approved_candidate_commit
        ):
            print(
                "run executes the held-out questions once; it needs "
                "--execute-frozen-questions, --owner-authorization-ref and "
                "--approved-candidate-commit",
                file=sys.stderr,
            )
            return 1
        if not args.host:
            parser.error("run needs --host or E1_HOST")
        return asyncio.run(run_candidate(args, inputs))
    except hc.HarnessError as error:
        print(f"preflight failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
