"""E1 held-out control harness (issue #317).

Replays the 12 frozen held-out cases through the UNCHANGED local orchestrator
runtime against the pinned corpora, twice, and reports whether every final
context reproduces (pre-registration, Run discipline 1). It implements no
candidate and changes no retrieval policy. It is a sibling of
code_evidence_experiment.py (whose F1-F3 `control` mode is untouched) and reuses
that script's observers so the capture shape is the same.

Commands (endpoints come from --host or E1_HOST, e.g. http://<host>; there is
no default address):

    python scripts/held_out_control.py plan              # offline preflight + plan
    python scripts/held_out_control.py plan --host H     # also checks generations
    python scripts/held_out_control.py run --host H      # the two control runs

`run` refuses to start unless the manifest checksum, the corpus pin, the
execution-contract settings and every pinned generation (ready, ingestion id,
commit, not incremental) check out, and never overwrites a completed capture.
Raw captures go under DOCS/test_results/_raw/code-evidence-held-out/ (git
ignored; list them with scripts/raw_index.py).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
CONTRACT = ROOT / "DOCS/evaluations/code-evidence-e1/execution-contract.json"
RAW = ROOT / "DOCS/test_results/_raw/code-evidence-held-out"

# The unchanged runtime's query settings (execution contract, pre-registration).
RUN_SETTINGS = {
    "top_k": 20,
    "max_chunks_per_doc": 5,
    "max_total_tokens": 4096,
    "rerank": False,
    "overview_flags": False,
}
MODEL = "ollama/Qwen3:4b"
EXPECTED_CASES = 12


class HarnessError(RuntimeError):
    """A preflight or consistency check failed; nothing was queried."""


@dataclass
class Inputs:
    manifest: dict
    cases: list[dict]
    pin: dict
    contract: dict
    manifest_sha256: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_inputs(
    held_out_dir: Path = HELD_OUT, contract_path: Path = CONTRACT
) -> Inputs:
    """Load the frozen inputs and run every offline preflight check."""
    raw = (held_out_dir / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    recorded = (held_out_dir / "manifest.sha256").read_text().strip()
    if digest != recorded:
        raise HarnessError("manifest.json does not match manifest.sha256")
    manifest = _read(held_out_dir / "manifest.json")
    pin = _read(held_out_dir / "held-out-corpus-pin.json")
    contract = _read(contract_path)
    if pin["manifest_sha256"] != digest:
        raise HarnessError("the corpus pin records a different manifest checksum")
    cases = manifest["cases"]
    if len(cases) != EXPECTED_CASES:
        raise HarnessError(f"expected {EXPECTED_CASES} cases, found {len(cases)}")
    if {c["repo"] for c in cases} != set(pin["repositories"]):
        raise HarnessError("cases and corpus pin cover different repositories")
    if not any(m["name"] == "Qwen3:4b" for m in contract["models"]):
        raise HarnessError("the execution contract does not name the Qwen3:4b model")
    check_settings(contract, RUN_SETTINGS)
    return Inputs(manifest, cases, pin, contract, digest)


def check_settings(contract: dict, settings: dict) -> None:
    expected = {
        "top_k": contract["top_k"],
        "max_chunks_per_doc": contract["adapter_max_chunks_per_doc"],
        "max_total_tokens": contract["context_cap_bytes"],
        "rerank": contract["rerank"],
        "overview_flags": contract["overview_flags"],
    }
    for key, value in expected.items():
        if settings.get(key) != value:
            raise HarnessError(
                f"setting {key}={settings.get(key)!r} differs from the contract "
                f"({value!r})"
            )


def check_generation(entry: dict, response: dict) -> None:
    """The current generation must be the pinned one, ready and not incremental."""
    gen = entry["generation"]
    problems = []
    if response.get("generation_status") != "ready":
        problems.append(f"status {response.get('generation_status')!r} is not ready")
    if str(response.get("ingestion_id")) != str(entry["ingestion_id"]):
        problems.append("ingestion_id differs from the pin")
    if response.get("commit_sha") != gen["ingested_commit_sha"]["value"]:
        problems.append("commit_sha differs from the pin")
    if response.get("is_incremental") is not False:
        problems.append("generation is incremental")
    if problems:
        raise HarnessError(f"{entry['repo_id']}: " + "; ".join(problems))


def primary_name(case: dict) -> str:
    return case["primary_function"].split("#", 1)[1]


def is_named(case: dict) -> bool:
    """Pre-registration rule: the query contains the primary function's name as a
    whole identifier token."""
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(primary_name(case))}(?![A-Za-z0-9_])"
    return re.search(pattern, case["query"]) is not None


def chunk_label(chunk: dict) -> str:
    metadata = chunk.get("metadata") or {}
    return str(
        chunk.get("canonical_id")
        or metadata.get("canonical_id")
        or metadata.get("source_metadata", {}).get("canonical_id")
        or ""
    )


def case_ids(case: dict) -> set[str]:
    return {case["primary_function"]} | {
        o["canonical_id"] for o in case["operations"] + case["dependencies"]
    }


def summarize_record(case: dict, record: dict) -> dict:
    """What the pre-registered predictions are about, from one captured record."""
    primary = case["primary_function"]
    final = record.get("final_chunks") or []
    pool = record.get("pre_budget_chunks")
    context = record.get("assembled_context") or ""
    final_labels = [chunk_label(c) for c in final]
    pool_labels = None if pool is None else [chunk_label(c) for c in pool]
    return {
        "case_id": case["id"],
        "named": is_named(case),
        "primary_function": primary,
        "primary_delivered": primary in final_labels,
        "primary_in_pool": None if pool_labels is None else primary in pool_labels,
        "primary_pool_rank": (
            pool_labels.index(primary)
            if pool_labels is not None and primary in pool_labels
            else None
        ),
        "delivered_labels": final_labels,
        "context_bytes": len(context.encode("utf-8")),
        "context_sha256": sha256_text(context),
    }


def compare_runs(run1: dict[str, dict], run2: dict[str, dict]) -> dict:
    if set(run1) != set(run2):
        raise HarnessError("the two runs cover different cases")
    per_case = {
        cid: run1[cid]["context_sha256"] == run2[cid]["context_sha256"]
        for cid in sorted(run1)
    }
    return {
        "reproduced": all(per_case.values()),
        "per_case": per_case,
        "differing_cases": [cid for cid, same in per_case.items() if not same],
    }


def write_capture(path: Path, data: Any) -> None:
    """Create a capture file; never overwrite a completed one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")


def capture_path(run: int, case_id: str) -> Path:
    return RAW / f"held-out-control-run{run}-{case_id}.json"


def write_incomplete(run: int, case_id: str, data: dict, error: str) -> Path:
    """Preserve what was observed for a case that did not complete, without a
    summary and without overwriting anything."""
    path = RAW / f"held-out-control-incomplete-run{run}-{case_id}.json"
    write_capture(path, {**data, "status": "incomplete-no-summary", "error": error})
    return path


def validate_record(record: dict, cap: int) -> None:
    """A case that did not produce a complete, self-consistent capture is an
    explicit failure, never a silent continuation."""
    for key in ("final_chunks", "pre_budget_chunks", "assembled_context"):
        if record.get(key) is None:
            raise HarnessError(f"capture is missing {key}")
    context = record["assembled_context"]
    if not context:
        raise HarnessError("the delivered context is empty")
    size = len(context.encode("utf-8"))
    if size > cap:
        raise HarnessError(f"delivered context is {size} bytes, over the {cap} cap")
    try:
        reported = record["response"]["retrieval_plan"]["tokens_after_budget"]
    except (KeyError, TypeError):
        raise HarnessError("the response carries no retrieval_plan bytes") from None
    if reported != size:
        raise HarnessError(
            f"retrieval_plan reports {reported} bytes, the context has {size}"
        )


def rag_arguments(case: dict, entry: dict) -> dict:
    """The only arguments the control passes to the unchanged runtime. Beyond the
    question and the pinned repo id, the sole manifest-derived value is
    trace_canonical_ids, which the orchestrator uses only to add a diagnostic
    entry to the retrieval plan after retrieval is done."""
    off = RUN_SETTINGS["overview_flags"]
    return {
        "query": case["query"],
        "repo_id": entry["repo_id"],
        "top_k": RUN_SETTINGS["top_k"],
        "max_chunks_per_doc": RUN_SETTINGS["max_chunks_per_doc"],
        "max_total_tokens": RUN_SETTINGS["max_total_tokens"],
        "model": MODEL,
        "rerank": RUN_SETTINGS["rerank"],
        "trace_canonical_ids": case_ids(case),
        "repository_overview_claim_selection_enabled": off,
        "repository_overview_canonical_selection_enabled": off,
        "repository_overview_structured_answers_enabled": off,
    }


def plan_lines(inputs: Inputs, runs: int = 2) -> list[str]:
    lines = []
    for run in range(1, runs + 1):
        for case in inputs.cases:
            kind = "named" if is_named(case) else "not-named"
            lines.append(
                f"run{run} {case['id']} {case['repo']} {kind} "
                f"primary={case['primary_function']}"
            )
    return lines


def fetch_generation(host: str, repo_id: str) -> dict:
    import urllib.request

    url = f"{host}:8001/v1/repos/{repo_id}/generation"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        return json.load(response)


def check_services(host: str) -> dict:
    """Read-only health: each application service's /version, nothing else."""
    import urllib.request

    versions = {}
    for port in (8001, 8002, 8003, 8004):
        url = f"{host}:{port}/version"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310
                versions[str(port)] = json.load(response)
        except OSError as error:
            raise HarnessError(
                f"service on port {port} unavailable: {error}"
            ) from error
    return versions


def check_all_generations(inputs: Inputs, host: str) -> dict:
    seen = {}
    for name, entry in inputs.pin["repositories"].items():
        response = fetch_generation(host, entry["repo_id"])
        check_generation(entry, response)
        seen[name] = response
    return seen


def runtime_state() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()

    return {
        "commit": git("rev-parse", "HEAD"),
        "tracked_changes": bool(git("status", "--porcelain", "--untracked-files=no")),
    }


def _experiment() -> Any:
    sys.path.insert(0, str(ROOT / "scripts"))
    module = importlib.import_module("code_evidence_experiment")
    module.RAW = RAW  # its observers log under RAW; keep held-out output separate
    return module


async def run_control(args: argparse.Namespace, inputs: Inputs) -> int:
    import httpx

    state = runtime_state()
    if state["tracked_changes"] and not args.allow_dirty:
        raise HarnessError("tracked files are modified; the runtime must be unchanged")
    check_settings(inputs.contract, RUN_SETTINGS)
    check_all_generations(inputs, args.host)
    ce = _experiment()
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
    summaries: dict[int, dict[str, dict]] = {1: {}, 2: {}}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            versions = await ce.fetch_versions(client, args.host)
        for run in (1, 2):
            for case in inputs.cases:
                path = capture_path(run, case["id"])
                if path.exists():
                    raise HarnessError(f"{path.name} exists; refusing to overwrite")
                entry = inputs.pin["repositories"][case["repo"]]
                url = f"{args.host}:8001/v1/repos/{entry['repo_id']}/generation"
                observed.clear()
                observed.update(
                    case_id=case["id"],
                    run=run,
                    captured_at=datetime.now(timezone.utc).isoformat(),
                    scope=(
                        "Local unchanged orchestrator with remote read-only HTTP "
                        "services; not the original UI or production wire"
                    ),
                    run_settings=dict(RUN_SETTINGS),
                    model=MODEL,
                    runtime=state,
                    versions=versions,
                    manifest_sha256=inputs.manifest_sha256,
                )
                async with httpx.AsyncClient(timeout=30) as client:
                    before = (await client.get(url)).json()
                check_generation(entry, before)
                observed["generation_before"] = before
                print(f"run{run} {case['id']}: capturing", flush=True)
                checkpoint("case_started", run=run)
                try:
                    response = await service.run_rag(**rag_arguments(case, entry))
                    observed["response"] = response.model_dump(mode="json")
                    async with httpx.AsyncClient(timeout=30) as client:
                        after = (await client.get(url)).json()
                    if after != before:
                        raise HarnessError(f"{case['id']}: generation changed mid-run")
                    observed["generation_after"] = after
                    validate_record(observed, RUN_SETTINGS["max_total_tokens"])
                except Exception as error:
                    write_incomplete(run, case["id"], dict(observed), repr(error))
                    if isinstance(error, HarnessError):
                        raise
                    raise HarnessError(
                        f"{case['id']} run{run} failed: {error!r}"
                    ) from error
                summary = summarize_record(case, observed)
                observed["summary"] = summary
                write_capture(path, observed)
                summaries[run][case["id"]] = summary
                print(json.dumps(summary["case_id"]) + " " + summary["context_sha256"])
                observed.pop("case_id", None)
    finally:
        restore()
    comparison = compare_runs(summaries[1], summaries[2])
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": inputs.manifest_sha256,
        "runtime": state,
        "run_settings": dict(RUN_SETTINGS),
        "reproduction": comparison,
        "cases": summaries[1],
    }
    write_capture(RAW / "held-out-control-summary.json", report)
    print(json.dumps(comparison["reproduced"]), comparison["differing_cases"])
    return 0 if comparison["reproduced"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "run"))
    parser.add_argument("--host", default=os.environ.get("E1_HOST"))
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--execute-frozen-questions",
        action="store_true",
        help="required by `run`: this executes the preregistered held-out questions",
    )
    args = parser.parse_args(argv)
    try:
        inputs = load_inputs()
        if args.command == "plan":
            print("\n".join(plan_lines(inputs)))
            if args.host:
                check_services(args.host)
                check_all_generations(inputs, args.host)
                print("services up; all pinned generations ready and matching")
            return 0
        if not args.execute_frozen_questions:
            print(
                "run executes the preregistered held-out questions; add "
                "--execute-frozen-questions to confirm (use `plan` for preflight)",
                file=sys.stderr,
            )
            return 1
        if not args.host:
            parser.error("run needs --host or E1_HOST (e.g. http://<host>)")
        return asyncio.run(run_control(args, inputs))
    except HarnessError as error:
        print(f"preflight failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
