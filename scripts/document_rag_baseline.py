"""Prepare and run the frozen D0 baseline on loopback-only isolated services."""

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from issue240_overview_eval import fetch


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_local(base):
    if (urlparse(base).scheme not in {"http", "https"}
            or urlparse(base).hostname not in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("Document uploads and evaluation must use loopback services")


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class DocumentIngestionFailed(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__(f"Document failed: {record['filename']} / "
                         f"{record['ingestion_id']}")


def inventory(endpoints, uploads):
    documents = []
    for upload in uploads:
        ingestion_id = upload["ingestion_id"]
        status = fetch(endpoints["ingestion"] + f"/v1/ingest/{ingestion_id}")
        if status["status"] != "completed":
            raise ValueError("Document ingestion is not completed")
        graph = fetch(endpoints["ingestion"] + f"/v1/graph/repos/{ingestion_id}")
        chunks = []
        for node in sorted(graph["nodes"], key=lambda n: n["canonical_id"]):
            records = fetch(endpoints["vector"] + "/v1/vectors/search-by-doc", {
                "document_id": node["document_id"], "k": 100,
                "ingestion_id": ingestion_id,
            })["results"]
            for record in records:
                if record["metadata"]["source_metadata"]["source_type"] == "code":
                    raise ValueError("Uploaded document incorrectly tagged code")
            chunks.extend(records)
        documents.append({"upload": upload, "status": status, "graph": graph,
                          "chunks": chunks})
    return documents


def upload_one(endpoints, path):
    started = time.monotonic()
    for _ in range(120):
        with path.open("rb") as handle:
            response = requests.post(
                endpoints["ingestion"] + "/v1/ingest/file",
                files={"file": (path.name, handle, "text/markdown")}, timeout=30)
        if response.status_code != 503:
            response.raise_for_status()
            break
        time.sleep(2)
    else:
        raise RuntimeError("Local document admission stayed busy")
    admitted = response.json()
    ingestion_id = admitted["ingestion_id"]
    for _ in range(150):
        status = fetch(endpoints["ingestion"] + f"/v1/ingest/{ingestion_id}")
        if status["status"] == "completed":
            return {"filename": path.name, "ingestion_id": ingestion_id,
                    "source_sha256": digest(path.read_bytes()),
                    "admission": admitted, "terminal": status,
                    "elapsed_seconds": round(time.monotonic() - started, 2)}
        if status["status"] == "failed":
            raise DocumentIngestionFailed({
                "filename": path.name, "ingestion_id": ingestion_id,
                "source_sha256": digest(path.read_bytes()),
                "admission": admitted, "terminal": status,
                "elapsed_seconds": round(time.monotonic() - started, 2)})
        time.sleep(2)
    raise TimeoutError(f"Document ingestion did not finish: {path.name}")


def prepare(args, endpoints):
    if args.prepared.exists():
        raise ValueError("Refusing to overwrite prepared corpus")
    manifest = json.loads((args.corpus / "manifest.json").read_text())
    for item in manifest["inputs"]:
        if digest(Path(item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError("Frozen corpus changed")
    if fetch(endpoints["ingestion"] + "/v1/repos"):
        raise ValueError("Isolated corpus is not empty")
    versions = {name: fetch(base + "/version") for name, base in endpoints.items()}
    data = {"status": "preparing", "versions": versions, "endpoints": endpoints,
            "local_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True).strip(),
            "manifest": manifest, "uploads": [], "answers_requested": 0}
    save(args.prepared, data)
    for path in sorted(args.corpus.glob("*.md")):
        try:
            data["uploads"].append(upload_one(endpoints, path))
        except DocumentIngestionFailed as exc:
            data["status"] = "failed-ingestion"
            data["failed_ingestion"] = exc.record
            save(args.prepared, data)
            raise
        save(args.prepared, data)
        print("Uploaded", path.name, flush=True)
    data["inventory"] = inventory(endpoints, data["uploads"])
    repos = fetch(endpoints["ingestion"] + "/v1/repos")
    if {r["ingestion_id"] for r in repos} != {
            u["ingestion_id"] for u in data["uploads"]}:
        raise ValueError("Unexpected corpus content")
    data["status"] = "prepared"
    save(args.prepared, data)


def run(args, endpoints):
    if args.output.exists():
        raise ValueError("Refusing to overwrite baseline run")
    prepared = json.loads(args.prepared.read_text())
    if prepared["status"] != "prepared" or prepared["endpoints"] != endpoints:
        raise ValueError("Prepared corpus unavailable or endpoints changed")
    current = inventory(endpoints, prepared["uploads"])
    if current != prepared["inventory"]:
        raise ValueError("Corpus changed since preparation")
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    versions = prepared["versions"]
    if any(fetch(base + "/version") != versions[name]
           for name, base in endpoints.items()):
        raise ValueError("Runtime differs from prepared corpus")
    data = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
            "prepared_sha256": digest(args.prepared.read_bytes()),
            "contract": contract, "versions": versions, "results": [],
            "request_settings": {"top_k": 5, "rerank": False},
            "observability": "Final manifest matched to stored chunk hashes; "
                             "intermediate retrieval stages not exposed by HTTP"}
    # Persist the full question/scoring/run contract before the first answer.
    save(args.output, data)
    try:
        for case in contract["cases"]:
            started = time.monotonic()
            request = {"query": case["query"], "top_k": 5, "rerank": False}
            response = requests.post(endpoints["orchestrator"] + "/v1/rag/simple",
                                     json=request, timeout=180)
            result = {"id": case["id"], "request": request,
                      "http_status": response.status_code, "response": response.json(),
                      "elapsed_seconds": round(time.monotonic() - started, 2)}
            data["results"].append(result)
            save(args.output, data)
            if response.ok and (result["response"].get("fallback_from")
                                or result["response"].get("reranked")
                                or result["response"].get("model_used")
                                != contract["model_identity"]["model"]
                                or result["response"].get("model_alias")
                                != contract["model_identity"]["alias"]):
                raise ValueError("Model fallback or reranking invalidates run")
            if any(fetch(base + "/version") != versions[name]
                   for name, base in endpoints.items()):
                raise ValueError("Runtime changed during evaluation")
            print(case["id"], response.status_code, flush=True)
        if inventory(endpoints, prepared["uploads"]) != current:
            raise ValueError("Corpus changed during evaluation")
        data["status"] = "complete"
    except Exception as exc:
        data["status"] = "failed"
        data["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        data["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save(args.output, data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "run"))
    for service in ("ingestion", "vector", "llm", "orchestrator"):
        parser.add_argument(f"--{service}", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    endpoints = {name: getattr(args, name).rstrip("/") for name in
                 ("ingestion", "vector", "llm", "orchestrator")}
    for base in endpoints.values():
        require_local(base)
    (prepare if args.phase == "prepare" else run)(args, endpoints)


if __name__ == "__main__":
    main()
