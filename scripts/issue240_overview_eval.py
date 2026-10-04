"""Capture the frozen issue #240 overview evaluation through public APIs.

The script only makes GET and RAG POST requests. It never ingests or changes a
repository. Results are written after each case so an interrupted run can be
inspected without silently claiming completion.
"""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ID = "f7641840-ba13-5f9d-9ae6-87e1f924709d"
GENERATION_ID = "d3ecfaea-23a1-4067-8f1a-0010c3158004"
SOURCE_SHA = "00e0cc9bf268a90ac85ed3b78ff7a8ba0afaf4bb"
PURPOSE_ID = "CLAUDE.md#claude_md.what_this_project_is"
ARCHITECTURE_ID = "CLAUDE.md#claude_md.architecture_independent_services_over_http"
CASES = (
    ("Q1", "I need information about the repo structure.", 10, ()),
    (
        "Q2",
        "Describe the actual directory, service, and package structure of "
        "this repository.",
        10,
        (),
    ),
    (
        "Q3",
        "Describe the actual directory, service, and package structure of "
        "rag-foundry-universal.",
        10,
        (),
    ),
    ("Q4", "Give me an architectural map of this repository.", 10, (ARCHITECTURE_ID,)),
    ("Q5", "What is this repository about?", 10, (PURPOSE_ID,)),
    ("Q5k20", "What is this repository about?", 20, (PURPOSE_ID,)),
    ("Q6", "What does rag-foundry-universal do?", 10, (PURPOSE_ID,)),
    (
        "Q7",
        "Describe this project's purpose and the kinds of source it analyzes.",
        10,
        (PURPOSE_ID,),
    ),
    (
        "C1",
        "According to the repository-understanding note, what went wrong "
        "with the my_test_repo answer?",
        10,
        (),
    ),
    ("C2", "What is shared/smoke_repo used for?", 10, ()),
    (
        "C3",
        "What does GraphAssembler.assemble do?",
        10,
        ("ingestion_service/src/core/codebase/graph_assembler.py#GraphAssembler.assemble",),
    ),
)


def fetch(url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=270) as response:
        return json.load(response)


def generation(ingestion_url: str) -> dict:
    result = fetch(f"{ingestion_url}/v1/repos/{REPO_ID}/generation")
    if result.get("generation_status") != "ready":
        raise RuntimeError(f"Repository is not ready: {result}")
    if result.get("ingestion_id") != GENERATION_ID:
        raise RuntimeError(f"Generation changed: {result}")
    if result.get("commit_sha") != SOURCE_SHA:
        raise RuntimeError(f"Source snapshot changed: {result}")
    return result


def run_case(orchestrator_url: str, ingestion_url: str, case: tuple) -> dict:
    name, query, top_k, targets = case
    before = generation(ingestion_url)
    request = {
        "query": query,
        "repo_id": REPO_ID,
        "top_k": top_k,
        "claim_type": "repository_overview",
        "rerank": False,
        "trace_canonical_ids": list(targets),
    }
    started = time.monotonic()
    response = fetch(f"{orchestrator_url}/v1/rag", request)
    elapsed = round(time.monotonic() - started, 2)
    after = generation(ingestion_url)
    plan = response["retrieval_plan"]
    if response["repo_id"] != REPO_ID or plan.get("generation_id") != GENERATION_ID:
        raise RuntimeError(f"Response not pinned for {name}: {response['repo_id']}")
    return {
        "case": name,
        "request": request,
        "generation_before": before,
        "generation_after": after,
        "elapsed_seconds": elapsed,
        "trace_id": response.get("trace_id"),
        "model_used": response.get("model_used"),
        "model_alias": response.get("model_alias"),
        "fallback_from": response.get("fallback_from"),
        "reranked": response.get("reranked"),
        "answer": response.get("answer"),
        "sources": response.get("sources"),
        "retrieval_plan": {
            key: plan.get(key)
            for key in (
                "generation_id",
                "seed_canonical_ids",
                "expanded_canonical_ids",
                "evidence_trace",
                "final_context_manifest",
                "provenance_diagnostics",
                "repository_overview_policy",
                "policy_selected_canonical_ids",
                "context_budget",
                "tokens_before_budget",
                "tokens_after_budget",
            )
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orchestrator", required=True)
    parser.add_argument("--ingestion", default="http://100.105.24.12:8001")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="*", default=[])
    args = parser.parse_args()
    selected = [case for case in CASES if not args.cases or case[0] in args.cases]
    if not selected:
        raise SystemExit("No matching cases")
    results = {
        "orchestrator": args.orchestrator,
        "ingestion": args.ingestion,
        "runtime_version": fetch(f"{args.orchestrator}/version"),
        "orient_response": fetch(f"{args.ingestion}/v1/repos/{REPO_ID}/orient"),
        "expected_generation": GENERATION_ID,
        "expected_source_sha": SOURCE_SHA,
        "expected_cases": [case[0] for case in selected],
        "results": [],
    }
    for case in selected:
        result = run_case(args.orchestrator, args.ingestion, case)
        results["results"].append(result)
        args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(
            f"{case[0]}: {result['trace_id']} ({result['elapsed_seconds']}s)",
            flush=True,
        )


if __name__ == "__main__":
    main()
