"""Read-only, pinned Q2-Q4 structured-answer experiment for issue #240.

The exact source commit is checked through ingestion. Local Compose bytes are
accepted only if their Git blob hashes match GitHub's blobs at that commit.
"""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "rag_orchestrator/src/retrieval/repository_structured_results.py"
SPEC = importlib.util.spec_from_file_location("repository_structured_results", MODULE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load structured-result module")
structured = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(structured)

REPO_ID = "f7641840-ba13-5f9d-9ae6-87e1f924709d"
GENERATION_ID = "f873147c-a1d1-4891-bb98-972672db8e9a"
SOURCE_SHA = "7a805d5b3cee031c44fbe0d9b8048065ce8ef039"
GITHUB_REPO = "sankar-ramamoorthy/rag-foundry-universal"
INGESTION = "http://100.105.24.12:8001"
OUTPUT = ROOT / "DOCS/test_results/2026-10-04-issue-240-structured-answer.json"
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.test.yml")


def get_json(url: str) -> dict:
    with urlopen(url, timeout=60) as response:
        return json.load(response)


def pinned_generation() -> dict:
    result = get_json(f"{INGESTION}/v1/repos/{REPO_ID}/generation")
    if (
        result.get("generation_status") != "ready"
        or result.get("ingestion_id") != GENERATION_ID
        or result.get("commit_sha") != SOURCE_SHA
    ):
        raise RuntimeError(f"Repository generation changed: {result}")
    return result


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def pinned_compose(filename: str) -> tuple[dict, dict]:
    # Git checks out CRLF on Windows; blob identity uses normalized LF bytes.
    content = (ROOT / filename).read_bytes().replace(b"\r\n", b"\n")
    local_blob = git_blob_sha(content)
    remote_blob = subprocess.check_output(
        [
            "gh",
            "api",
            "-X",
            "GET",
            f"repos/{GITHUB_REPO}/contents/{filename}",
            "-f",
            f"ref={SOURCE_SHA}",
            "--jq",
            ".sha",
        ],
        text=True,
        timeout=30,
    ).strip()
    if local_blob != remote_blob:
        raise RuntimeError(f"Local {filename} differs from pinned source commit")
    document = yaml.safe_load(content)
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        raise RuntimeError(f"Invalid Compose source: {filename}")
    return document, {
        "path": filename,
        "git_blob_sha": local_blob,
        "checkout_normalization": "crlf_to_lf",
    }


def main() -> None:
    before = pinned_generation()
    inventory = get_json(f"{INGESTION}/v1/repos/{REPO_ID}/orient")
    if inventory.get("ingestion_id") != GENERATION_ID:
        raise RuntimeError("ORIENT generation mismatch")
    graph = get_json(f"{INGESTION}/v1/graph/repos/{REPO_ID}")
    if graph.get("generation_status") != "ready":
        raise RuntimeError("Graph is not ready")
    compose_files = {}
    blob_proofs = []
    for filename in COMPOSE_FILES:
        compose_files[filename], proof = pinned_compose(filename)
        blob_proofs.append(proof)
    services = structured.build_service_result(inventory, graph)
    service_errors = structured.validate_service_result(services, inventory, graph)
    architecture = structured.build_architecture_result(
        services, graph, compose_files
    )
    architecture_errors = structured.validate_architecture_result(
        architecture, services, graph, compose_files
    )
    after = pinned_generation()
    if service_errors or architecture_errors:
        raise RuntimeError(f"Validation failed: {service_errors + architecture_errors}")
    result = {
        "repository_id": REPO_ID,
        "generation_before": before,
        "generation_after": after,
        "source_sha": SOURCE_SHA,
        "compose_blob_proofs": blob_proofs,
        "graph_node_count": graph.get("total_nodes"),
        "validation": {
            "Q2": service_errors,
            "Q3": service_errors,
            "Q4": architecture_errors,
        },
        "structured_service_result": services,
        "structured_architecture_result": architecture,
        "answers": {
            "Q2": structured.render_service_answer(services, "q2"),
            "Q3": structured.render_service_answer(services, "q3"),
            "Q4": structured.render_architecture_answer(architecture),
        },
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    for case, answer in result["answers"].items():
        print(f"{case}: {len(answer)} characters, validation passed")


if __name__ == "__main__":
    main()
