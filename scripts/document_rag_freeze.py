"""Validate document baseline references and freeze exact corpus input hashes."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a frozen manifest")
    questions = args.corpus / "questions.json"
    suite = json.loads(questions.read_text(encoding="utf-8"))
    paths = sorted(args.corpus.glob("*.md"))
    source_text = {path.name: path.read_text(encoding="utf-8") for path in paths}
    ids = [case["id"] for case in suite["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate question IDs")
    for case in suite["cases"]:
        if not case["query"] or not case["facts"] or not case["required_sources"]:
            raise ValueError("Incomplete case")
        for reference in case["required_sources"]:
            filename, heading = reference.split("#", 1)
            if filename not in source_text or (
                    f"## {heading}" not in source_text[filename].splitlines()):
                raise ValueError(f"Unresolved expected source section: {reference}")
    inputs = paths + [questions]
    manifest = {
        "status": "source-and-questions-frozen; not-executed",
        "dataset_class": suite["dataset_class"], "cases": ids,
        "documents": len(paths), "ingestion_ids": [],
        "runtime_model_and_effective_settings": "Must pin before first answer",
        "inputs": [{"path": path.as_posix(), "bytes": len(path.read_bytes()),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for path in inputs],
    }
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(paths)} source documents and {len(ids)} cases; "
          "all expected source sections resolve")


if __name__ == "__main__":
    main()
