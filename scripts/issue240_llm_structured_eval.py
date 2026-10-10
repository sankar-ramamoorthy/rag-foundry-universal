"""Check whether the pinned Qwen model preserves typed Q2-Q4 result objects.

The structured facts are already derived and validated. The model is asked to
serialize each compact claim object; exact validation rejects changed states,
omitted fields, and mixed edge types before any prose rendering.
"""

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "DOCS/test_results/2026-10-04-issue-240-structured-answer.json"
OUTPUT = ROOT / "DOCS/test_results/2026-10-04-issue-240-llm-structured.json"
INGESTION = "http://100.105.24.12:8001"
LLM = "http://100.105.24.12:8003/generate"


def fetch(url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=270) as response:
        return json.load(response)


def generation(source: dict) -> dict:
    repo_id = source["repository_id"]
    result = fetch(f"{INGESTION}/v1/repos/{repo_id}/generation")
    if (
        result.get("generation_status") != "ready"
        or result.get("ingestion_id") != source["generation_before"]["ingestion_id"]
        or result.get("commit_sha") != source["source_sha"]
    ):
        raise RuntimeError(f"Generation changed: {result}")
    return result


def expected_claims(source: dict, case: str) -> dict:
    services = source["structured_service_result"]
    if case == "Q2":
        return {
            "service_count": services["service_count"],
            "services": {
                name: {
                    "compose_declarations": row["compose_declarations"],
                    "repository_directory": row["repository_directory"],
                    "indexed_source_directory": row["indexed_source_directory"],
                    "dockerfiles": row["dockerfiles"],
                    "manifests": row["manifests"],
                    "test_directories": row["test_directories"],
                    "indexed_implementation_files_by_language": row[
                        "indexed_implementation_files_by_language"
                    ],
                }
                for name, row in services["services"].items()
            },
        }
    if case == "Q3":
        return {
            "services": {
                name: {
                    "package_status": row["package"]["status"],
                    "marker_count": len(row["package"]["markers"]),
                }
                for name, row in services["services"].items()
            }
        }
    if case == "Q4":
        architecture = source["structured_architecture_result"]
        return {
            key: architecture[key]
            for key in (
                "components",
                "http_edges",
                "datastore_edges",
                "deployment_edges",
                "ports",
            )
        }
    raise ValueError(case)


def parse_json_response(response: str) -> dict | None:
    candidate = response.strip()
    if candidate.startswith("```json") and candidate.endswith("```"):
        candidate = candidate[7:-3].strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    result = {
        "source_record": str(SOURCE.relative_to(ROOT)),
        "repository_id": source["repository_id"],
        "generation_id": source["generation_before"]["ingestion_id"],
        "source_sha": source["source_sha"],
        "cases": [],
    }
    for case in ("Q2", "Q3", "Q4"):
        expected = expected_claims(source, case)
        before = generation(source)
        started = time.monotonic()
        response = fetch(
            LLM,
            {
                "context": json.dumps(expected, separators=(",", ":")),
                "query": (
                    "Return the supplied repository claim object as valid JSON. "
                    "Preserve every key, value, enum, and relationship type. "
                    "Return JSON only; no markdown or explanation."
                ),
            },
        )
        elapsed = round(time.monotonic() - started, 2)
        after = generation(source)
        raw = str(response.get("response", ""))
        parsed = parse_json_response(raw)
        case_result = {
            "case": case,
            "generation_before": before,
            "generation_after": after,
            "model": response.get("model"),
            "elapsed_seconds": elapsed,
            "expected": expected,
            "raw_response": raw,
            "parsed": parsed,
            "valid": parsed == expected,
            "failure": (
                None
                if parsed == expected
                else "invalid_json"
                if parsed is None
                else "semantic_or_field_mismatch"
            ),
        }
        result["cases"].append(case_result)
        OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"{case}: valid={case_result['valid']} elapsed={elapsed}s", flush=True)


if __name__ == "__main__":
    main()
