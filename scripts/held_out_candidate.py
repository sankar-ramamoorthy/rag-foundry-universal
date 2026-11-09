"""E1 named-symbol-first candidate harness (issue #323).

Runs the 12 frozen held-out cases ONCE through the runtime with
named_symbol_first=True. It shares the control harness preflight, settings,
observers and validation (scripts/held_out_control.py) and differs only in the
one extra run_rag argument. Captures are `held-out-candidate-*`, created in
`x` mode (never overwriting, never touching the control files), and record
the candidate commit and the frozen mechanism-spec hash.

    python scripts/held_out_candidate.py plan --host H
    python scripts/held_out_candidate.py run --host H \
        --execute-frozen-questions --owner-authorization-ref <approval>

`run` needs a separate, explicit owner approval (#323): exactly one execution,
no retries, no partial reruns, no fixing in place. It refuses a dirty tracked
tree (there is no --allow-dirty) and refuses to start if ANY candidate capture
already exists.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.util
import logging
import os
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


async def run_candidate(args: argparse.Namespace, inputs: Any) -> int:
    import httpx

    spec_hash = spec_sha256()
    state = hc.runtime_state()
    if state["tracked_changes"]:
        raise CandidateError("tracked files are modified; commit before the run")
    if existing_candidate_captures():
        raise CandidateError("candidate captures exist; this run is single-shot")
    hc.check_settings(inputs.contract, hc.RUN_SETTINGS)
    hc.check_all_generations(inputs, args.host)
    ce = hc._experiment()
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    config: Any = importlib.import_module("src.core.config")
    from rag_orchestrator.src.core import config as package_config

    settings = config.Settings(
        _env_file=None,
        OLLAMA_BASE_URL=f"{args.host}:11434",
        INGESTION_SERVICE_URL=f"{args.host}:8001",
        VECTOR_STORE_URL=f"{args.host}:8002",
        LLM_SERVICE_URL=f"{args.host}:8003",
    )
    config.get_settings = lambda: settings
    package_config.get_settings = lambda: settings
    service: Any = importlib.import_module("src.core.service")
    observed, checkpoint, restore = ce.install_observers(service)
    logging.disable(logging.CRITICAL)
    summaries: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            versions = await ce.fetch_versions(client, args.host)
        for case in inputs.cases:
            entry = inputs.pin["repositories"][case["repo"]]
            url = f"{args.host}:8001/v1/repos/{entry['repo_id']}/generation"
            observed.clear()
            observed.update(
                case_id=case["id"],
                mode="candidate-named-symbol-first",
                captured_at=datetime.now(timezone.utc).isoformat(),
                run_settings=dict(hc.RUN_SETTINGS),
                model=hc.MODEL,
                runtime=state,
                candidate_commit=state["commit"],
                mechanism_spec_sha256=spec_hash,
                owner_authorization_ref=args.owner_authorization_ref,
                versions=versions,
                manifest_sha256=inputs.manifest_sha256,
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
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "candidate_commit": state["commit"],
            "mechanism_spec_sha256": spec_hash,
            "manifest_sha256": inputs.manifest_sha256,
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
        if not args.execute_frozen_questions or not args.owner_authorization_ref:
            print(
                "run executes the held-out questions once; it needs "
                "--execute-frozen-questions and --owner-authorization-ref",
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
