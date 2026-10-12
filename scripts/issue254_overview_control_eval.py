"""Matched, read-only development-corpus comparison for issue #254.

Freeze the contract before requesting any answers. Persist each full response,
and fail closed if runtime, corpus, response generation, or controls drift.
"""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from issue240_overview_eval import CASES, CONTROL_ARGS, fetch, generation


ARMS = {
    "overview_off": (True, False, False),
    "claim_only": (True, True, False),
    "candidate": (True, True, True),
    "normal": (False, False, False),
}
AGENT_RUN = "py_mono/agent/agent.py#Agent.run"
AGENT_CASES = (
    (
        "R1",
        "Using `py_mono/main.py#main`, `py_mono/ui/cli.py#start_cli`, and "
        "`py_mono/agent/agent.py#Agent.run`, trace a normal user prompt through "
        "a tool call and the tool result returning to the LLM.",
        10,
        ("py_mono/main.py#main", "py_mono/ui/cli.py#start_cli", AGENT_RUN),
    ),
    ("R1_method", "What does Agent.run do?", 10, (AGENT_RUN,)),
)


def request_for(case: tuple, repo_id: str, arm: str) -> dict:
    overview, claims, structured = ARMS[arm]
    request = {
        "query": case[1], "repo_id": repo_id, "top_k": case[2],
        "rerank": False, "trace_canonical_ids": list(case[3]),
        CONTROL_ARGS["claim_selection"]: claims,
        CONTROL_ARGS["structured_answers"]: structured,
        CONTROL_ARGS["canonical_selection"]: False,
    }
    if overview:
        request["claim_type"] = "repository_overview"
    return request


def validate_response(response: dict, request: dict, generation_id: str) -> None:
    plan = response["retrieval_plan"]
    if (response["repo_id"] != request["repo_id"]
            or plan.get("generation_id") != generation_id):
        raise RuntimeError("Response corpus does not match frozen contract")
    expected = {
        "claim_selection_enabled": request[CONTROL_ARGS["claim_selection"]],
        "structured_answers_enabled": request[CONTROL_ARGS["structured_answers"]],
        "canonical_selection_enabled": False,
    }
    observed = plan.get("repository_overview_controls", {})
    if any(observed.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"Effective controls differ: {observed}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orchestrator", required=True)
    parser.add_argument("--ingestion", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing comparison")
    corpora = (
        ("frozen240", "f7641840-ba13-5f9d-9ae6-87e1f924709d", CASES,
         ("overview_off", "candidate")),
        ("agent", "863e770d-651e-5bc5-83d1-a1409693e707", AGENT_CASES,
         ("normal", "overview_off", "claim_only", "candidate")),
    )
    versions = {
        name: fetch(f"{url}/version")
        for name, url in (("orchestrator", args.orchestrator),
                          ("ingestion", args.ingestion))
    }
    contract = []
    for name, repo_id, cases, arms in corpora:
        pin = fetch(f"{args.ingestion}/v1/repos/{repo_id}/generation")
        generation(args.ingestion, repo_id, pin["ingestion_id"], pin["commit_sha"])
        contract.append({
            "dataset": name, "repo_id": repo_id, "pin": pin,
            "cases": list(cases), "arms": list(arms),
        })
    result = {
        "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "development-regression; not held-out generalization",
        "local_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "main_sha": subprocess.check_output(
            ["git", "rev-parse", "origin/main"], text=True).strip(),
        "runtime_versions": versions, "contract": contract,
        "scoring": {
            "frozen240": "Unchanged 2026-10-03 frozen acceptance criteria",
            "R1": "Agent.run survives final context and is directly cited; "
                  "answer traces prompt, tool dispatch and result feedback "
                  "without claiming named code is absent",
            "R1_method": "Current Agent.run survives and is cited; answer "
                         "describes its LLM/tool loop",
            "gate": "Overview improvement AND no explicit-code regression "
                    "against matched overview_off and normal controls",
        },
        "results": [],
    }

    def save() -> None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for corpus in contract:
            pin = corpus["pin"]
            for case in corpus["cases"]:
                for arm in corpus["arms"]:
                    before_version = fetch(f"{args.orchestrator}/version")
                    if before_version != versions["orchestrator"]:
                        raise RuntimeError("Orchestrator runtime changed")
                    before = generation(args.ingestion, corpus["repo_id"],
                                        pin["ingestion_id"], pin["commit_sha"])
                    request = request_for(case, corpus["repo_id"], arm)
                    started = time.monotonic()
                    response = fetch(
                        f"{args.orchestrator}/v1/rag", request, timeout=600
                    )
                    elapsed = round(time.monotonic() - started, 2)
                    after = generation(args.ingestion, corpus["repo_id"],
                                       pin["ingestion_id"], pin["commit_sha"])
                    after_versions = {
                        name: fetch(f"{url}/version")
                        for name, url in (("orchestrator", args.orchestrator),
                                          ("ingestion", args.ingestion))
                    }
                    validate_response(response, request, pin["ingestion_id"])
                    if after_versions != versions:
                        raise RuntimeError("Runtime changed during request")
                    result["results"].append({
                        "dataset": corpus["dataset"], "case": case[0], "arm": arm,
                        "request": request, "generation_before": before,
                        "generation_after": after, "runtime_after": after_versions,
                        "elapsed_seconds": elapsed, "response": response,
                    })
                    save()
                    print(
                        f'{corpus["dataset"]} {case[0]} {arm}: {elapsed}s', flush=True
                    )
        result["status"] = "complete"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    main()
