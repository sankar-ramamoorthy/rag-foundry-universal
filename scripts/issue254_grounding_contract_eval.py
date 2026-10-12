"""Frozen-evidence answer-contract experiment; no runtime policy changes."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from issue240_overview_eval import fetch, generation
from issue254_complete_evidence_eval import digest


CONTRACT = """Answer contract for the requested execution trace:
Use a compact ordered table. Include startup, user input, provider invocation,
tool-call extraction, tool execution, and result feedback. For each row give:
(1) implementing component and canonical source identifier,
(2) exact operation or call, including its observed arguments/returned fields,
(3) input/state read and output/state written,
(4) the next component or loop handoff,
(5) a short literal source quote supporting the operation.
Distinguish creating a component, looking up an object, and executing a call.
Do not substitute a high-level paraphrase for a visible call or field extraction.
Describe how state connects the steps, including the next provider invocation.
Only attribute an operation to the component whose source implements it.
If an initializer or dependency is not shown, mark it unknown rather than
inventing its value or interpreting an index as a particular message role.
End with any evidence gaps. Use only the supplied source; do not infer behavior
from unrelated frameworks or historical descriptions.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite frozen experiment")
    original = json.loads(args.input.read_text(encoding="utf-8"))
    diagnostic = json.loads(args.diagnostic.read_text(encoding="utf-8"))
    baseline = original["payloads"]["complete_evidence"]
    # Insert the instruction before the fixed envelope; the evidence suffix,
    # original question, model alias and system template are unchanged.
    payloads = {
        "frozen": baseline,
        "contract": {**baseline, "context": CONTRACT + "\n" + baseline["context"]},
    }
    settings = diagnostic["settings"]
    endpoint = settings["LLM_SERVICE_URL"]
    version = fetch(endpoint + "/version")
    identity = original["model_identity"]
    if version != original["runtime_version"]:
        raise ValueError("Runtime changed since frozen evidence experiment")
    result = {
        "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_experiment_sha256": digest(args.input.read_text(encoding="utf-8")),
        "pin": original["pin"], "repo_id": original["repo_id"],
        "model_identity": identity, "runtime_version": version,
        "evidence_bytes": original["complete_evidence_bytes"],
        "evidence_manifest": original["source_manifest"],
        "contract": CONTRACT, "contract_bytes": len((CONTRACT + "\n").encode()),
        "payloads": payloads, "scoring": original["scoring"],
        "additional_review": "Record unsupported memory[1:] role inference, "
                             "explicit unknown initializer and quote accuracy. "
                             "No model-capability conclusion from this test alone.",
        "paired_order": [["frozen", "contract"], ["contract", "frozen"],
                         ["frozen", "contract"]], "results": [],
    }

    def save():
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for pair, arms in enumerate(result["paired_order"], 1):
            for arm in arms:
                pin = result["pin"]
                before = generation(settings["INGESTION_SERVICE_URL"],
                                    result["repo_id"], pin["ingestion_id"],
                                    pin["commit_sha"])
                if fetch(endpoint + "/version") != version:
                    raise ValueError("Runtime changed")
                started = time.monotonic()
                response = fetch(endpoint + "/generate", payloads[arm], timeout=600)
                after = generation(settings["INGESTION_SERVICE_URL"],
                                   result["repo_id"], pin["ingestion_id"],
                                   pin["commit_sha"])
                if ({key: response.get(key) for key in identity} != identity
                        or response.get("fallback_from") is not None
                        or fetch(endpoint + "/version") != version):
                    raise ValueError("Model/runtime/template changed")
                result["results"].append({
                    "pair": pair, "arm": arm, "response": response,
                    "generation_before": before, "generation_after": after,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                })
                save()
                print(f"Pair {pair} {arm} complete", flush=True)
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
