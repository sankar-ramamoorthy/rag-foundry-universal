"""Fixed offline source transport and independent inventory witnesses for #398."""

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from src.core import execution_policy as policy

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "DOCS/evaluations/intent-obligations"
MODULE = "ingestion_service/src/api/v1/codebase_ingest.py"
PATHS = (MODULE, "api/ingest.py", "cli/ingest.py")
REPO = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def matches(entity):
    if "/" in entity:
        return [entity] if entity in PATHS else []
    return [path for path in PATHS if path.rsplit("/", 1)[-1] == entity]


class Corpus:
    def __init__(self):
        self.text = {MODULE: (ROOT / MODULE).read_text(encoding="utf8")}
        self.witness = json.loads((DATA / "inventory-witness.json").read_bytes())
        if sha(self.text[MODULE]) != self.witness["sha256"]:
            raise ValueError("corpus source differs from frozen inventory witness")
        for path in PATHS[1:]:
            name = path.split("/")[0]
            self.text[path] = f"def {name}():\n    pass\n"

    def expected(self, path):
        if path == MODULE:
            return self.witness["inventory"]
        return [{"name": path.split("/")[0], "kind": "sync", "start": 1, "end": 2}]

    async def dispatch(self, request, action):
        assert isinstance(action, policy.Read)
        source = self.text[action.path].splitlines(keepends=True)
        start, end = action.start_line, action.end_line
        assert start and end and 1 <= end - start + 1 <= 500
        end = min(end, len(source))
        text = "".join(source[start - 1 : end])
        eof = end == len(source)
        return {
            "repo_id": str(request.repo_id),
            "generation_id": str(request.generation_id),
            "path": action.path,
            "canonical_id": action.path,
            "document_id": action.path,
            "start_line": start,
            "end_line": end,
            "complete_file": eof and start == 1,
            "total_lines": end if eof else None,
            "next_start_line": None if eof else end + 1,
            "text": text,
            "returned_text_sha256": sha(text),
        }

    def inventories(self, entities, question, budget=8):
        results = {}
        with patch.object(policy, "dispatch", self.dispatch):
            for entity in entities:
                (path,) = matches(entity)
                if path in results:
                    continue
                req = policy.Request.model_validate(
                    {
                        "repo_id": REPO,
                        "generation_id": GEN,
                        "question": question,
                        "path": path,
                        "family": "python_inventory",
                        "maximum_strategy": "deterministic",
                        "tool_calls": budget,
                        "model_calls": 0,
                    }
                )
                result = asyncio.run(policy.run_execution_policy(req))
                budget -= result["tool_calls"]
                results[path] = {
                    k: v
                    for k, v in result.items()
                    if k
                    in (
                        "inventory",
                        "completion",
                        "termination_reason",
                        "returned_text_sha256",
                        "tool_calls",
                        "model_calls",
                    )
                }
        return results

    def verified(self, entities, results):
        paths = [matches(entity) for entity in entities]
        if not paths or any(len(candidates) != 1 for candidates in paths):
            return False
        expected = {candidates[0] for candidates in paths}
        return set(results) == expected and all(
            row["completion"] == "verified_complete"
            and row["inventory"] == self.expected(path)
            and row["returned_text_sha256"] == sha(self.text[path])
            for path, row in results.items()
        )
