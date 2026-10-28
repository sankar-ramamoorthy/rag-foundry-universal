"""Read-only eligibility checks for the frozen D0 document baseline."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from issue240_overview_eval import fetch


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_frozen_inputs(manifest):
    for entry in manifest["inputs"]:
        if sha(Path(entry["path"]).read_bytes()) != entry["sha256"]:
            raise ValueError("Frozen local input changed")


def inspect_document(entry, node, args, endpoints, pin):
    path = entry["path"]
    url = ("https://raw.githubusercontent.com/sankar-ramamoorthy/"
           f"rag-foundry-universal/{args.source_sha}/{path}")
    with urlopen(url, timeout=30) as response:
        source_hash = sha(response.read())
    if source_hash != entry["sha256"]:
        raise ValueError(f"Pinned Git source differs from fixture: {path}")
    chunks = fetch(endpoints["vector"] + "/v1/vectors/search-by-doc", {
        "document_id": node["document_id"], "k": 100,
        "repo_id": args.repo_id, "ingestion_id": pin["ingestion_id"],
    })["results"]
    if not chunks:
        raise ValueError(f"No stored fixture chunks: {path}")
    types = sorted({chunk["metadata"]["source_metadata"]["source_type"]
                    for chunk in chunks})
    return {"node": node, "source_url": url,
            "source_sha256": source_hash, "chunks": chunks,
            "source_types": types,
            "noncode_eligible_chunks": sum(
                chunk["metadata"]["source_metadata"]["source_type"]
                != "code" for chunk in chunks)}


def main():
    parser = argparse.ArgumentParser()
    for service in ("ingestion", "vector", "llm", "orchestrator"):
        parser.add_argument(f"--{service}", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a preflight snapshot")
    manifest = json.loads((args.corpus / "manifest.json").read_text())
    check_frozen_inputs(manifest)
    endpoints = {name: getattr(args, name).rstrip("/") for name in
                 ("ingestion", "vector", "llm", "orchestrator")}
    versions = {name: fetch(base + "/version") for name, base in endpoints.items()}
    if any(version["git_sha"] != args.source_sha for version in versions.values()):
        raise ValueError("Runtime revision differs from requested pin")
    generation_url = endpoints["ingestion"] + f"/v1/repos/{args.repo_id}/generation"
    pin = fetch(generation_url)
    if pin["generation_status"] != "ready" or pin["commit_sha"] != args.source_sha:
        raise ValueError("Indexed generation is not ready at requested source")
    sources = [entry for entry in manifest["inputs"] if entry["path"].endswith(".md")]
    lookup = fetch(endpoints["ingestion"] +
                   f"/v1/graph/repos/{args.repo_id}/nodes/lookup",
                   {"canonical_ids": [entry["path"] for entry in sources]})
    nodes = {node["canonical_id"]: node for node in lookup["nodes"]}
    documents = []
    for entry in sources:
        path = entry["path"]
        if path not in nodes:
            raise ValueError(f"Expected fixture not indexed: {path}")
        documents.append(inspect_document(entry, nodes[path], args, endpoints, pin))
    if fetch(generation_url) != pin:
        raise ValueError("Generation changed during preflight")
    if any(fetch(base + "/version") != versions[name]
           for name, base in endpoints.items()):
        raise ValueError("Runtime changed during preflight")
    result = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "status": "execution-blocked" if any(
            doc["noncode_eligible_chunks"] == 0 for doc in documents)
            else "eligibility-only-verified",
        "versions": versions, "generation": pin, "documents": documents,
        "document_path_filter": {"source_type": {"ne": "code"}},
        "isolation": "No corpus filter forwarded by simple endpoint; "
                     "full production corpus isolation not established",
        "interpretation": "Repository-ingested Markdown is not uploaded-document "
                          "ingestion. Source-type exclusion is intentional; no "
                          "claim of a retrieval regression or parser failure.",
        "answers_requested": 0, "production_mutations": 0,
        "next_requirement": "Isolated document stack with uploaded fixtures; "
                            "do not change source-type filtering for this baseline",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["status"], "; documents:", len(documents), "; stored chunks:",
          sum(len(doc["chunks"]) for doc in documents), "; eligible:",
          sum(doc["noncode_eligible_chunks"] for doc in documents))


if __name__ == "__main__":
    main()
