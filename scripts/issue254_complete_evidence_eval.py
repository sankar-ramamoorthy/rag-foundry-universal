"""Controlled generation experiment: captured versus source-complete R1 evidence.

Manual source excerpts are an offline oracle, not a retrieval implementation.
Freeze both contexts and scoring before six unchanged-model generation calls.
"""

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from issue240_overview_eval import fetch, generation


ROOT = Path(__file__).resolve().parents[1]
BUDGET = 4096
EXCERPTS = (
    ("py_mono/main.py", "main", 132, 148),
    ("py_mono/ui/cli.py", "start_cli", 37, 58),
    ("py_mono/agent/agent.py", "Agent.run", 638, 650),
    ("py_mono/agent/agent.py", "Agent.run", 675, 702),
    ("py_mono/agent/agent.py", "Agent.run", 723, 738),
    ("py_mono/agent/agent.py", "Agent.run", 740, 764),
)
FACTS = {
    "input": "Prompt passes to run and is appended as user-role memory",
    "provider": "Active provider generate receives messages/memory and tools",
    "extraction": "Tool name/args come from the provider's returned tool_call",
    "dispatch": "Tool lookup and tool.run(**args) execute the requested tool",
    "feedback": "Role-tool result is appended to memory and loop continues; "
                "next generate receives that memory",
}
ATTRIBUTION = {
    "startup_owner": "main constructs session manager/Agent and starts CLI",
    "input_owner": "start_cli reads/passes input; Agent.run owns user memory",
    "decision_owner": "Provider generates tool_call; Agent reads its name/args",
    "dispatch_owner": "Agent executes tool; provider does not access self.tools",
    "feedback_owner": "Agent owns role-tool memory update and next provider call",
}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_evidence(sources: dict, excerpts=EXCERPTS, budget=BUDGET) -> tuple[str, list]:
    parts, manifest = [], []
    for path, symbol, first, last in excerpts:
        lines = sources[path]["text"].splitlines()
        if not 1 <= first <= last <= len(lines):
            raise ValueError(f"Invalid pinned source range: {path}:{first}-{last}")
        text = "\n".join(lines[first - 1:last])
        canonical_id = f"{path}#{symbol}"
        part = f"[Source: {canonical_id}]\n{text}"
        parts.append(part)
        manifest.append({
            "canonical_id": canonical_id, "first_line": first, "last_line": last,
            "text": text, "text_sha256": digest(text),
            "source_sha256": digest(sources[path]["text"]),
            "labeled_bytes": len(part.encode("utf-8")),
        })
    evidence = "\n\n".join(parts)
    if len(evidence.encode("utf-8")) > budget:
        raise ValueError("Source-complete evidence exceeds cap; refuse to truncate")
    return evidence, manifest


def replace_evidence(payload: dict, previous: str, replacement: str) -> dict:
    if not previous or not payload["context"].endswith(previous):
        raise ValueError("Captured evidence is not the exact payload suffix")
    return {**payload, "context": payload["context"][:-len(previous)] + replacement}


def main() -> None:  # noqa: C901 - one frozen experiment with fail-closed checks
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--source-context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a frozen experiment")
    diagnostic = json.loads(args.diagnostic.read_text(encoding="utf-8"))
    if diagnostic["status"] != "complete":
        raise ValueError("Diagnostic input is incomplete")
    sources = json.loads(
        args.source_context.read_text(encoding="utf-8")
    )["pinned_source"]
    # Verify exact pinned source bytes before constructing/fixing the oracle.
    for source in sources.values():
        with urlopen(source["url"], timeout=30) as response:
            if response.read().decode("utf-8") != source["text"]:
                raise ValueError("Pinned source bytes differ from captured snapshot")
    case = next(c for c in diagnostic["cases"] if c["arm"] == "candidate")
    wire = next(w for w in case["wire"] if w["url"].endswith("/generate"))
    assembly = next(s for s in reversed(case["stages"])
                    if s["stage"] == "assembly" and s["budget"] == BUDGET)
    baseline = "\n\n".join(
        f'[Source: {c["canonical_id"]}]\n{c["text"]}' for c in assembly["chunks"]
    )
    if len(baseline.encode("utf-8")) != assembly["consumed"]:
        raise ValueError("Captured baseline byte accounting differs")
    complete, manifest = build_evidence(sources)
    payloads = {
        "candidate": wire["request"],
        "complete_evidence": replace_evidence(wire["request"], baseline, complete),
    }
    prefix = wire["request"]["context"][:-len(baseline)]
    for payload in payloads.values():
        if (payload["query"] != case["request"]["query"]
                or not payload["context"].startswith(prefix)):
            raise ValueError("Question or fixed envelope changed")
    settings = diagnostic["settings"]
    pin = diagnostic["pin"]["pin"]
    repo_id = diagnostic["pin"]["repo_id"]
    order = (("candidate", "complete_evidence"),
             ("complete_evidence", "candidate"),
             ("candidate", "complete_evidence"))
    version = fetch(f'{settings["LLM_SERVICE_URL"]}/version')
    identity = {key: wire["response"][key] for key in
                ("model", "model_alias", "prompt_template")}
    result = {
        "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "manual oracle on development corpus; not retrieval policy",
        "local_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "pin": pin, "repo_id": repo_id, "runtime_version": version,
        "model_identity": identity, "evidence_cap": BUDGET,
        "candidate_evidence_bytes": len(baseline.encode("utf-8")),
        "complete_evidence_bytes": len(complete.encode("utf-8")),
        "fixed_envelope_bytes": len(prefix.encode("utf-8")),
        "fixed_envelope_sha256": digest(prefix), "source_manifest": manifest,
        "payloads": payloads,
        "payload_sha256": {arm: digest(payload["context"])
                           for arm, payload in payloads.items()},
        "source_coverage": {"candidate": {
            key: key == "dispatch" for key in FACTS
        }, "complete_evidence": dict.fromkeys(FACTS, True)},
        "scoring": {
            "factual": FACTS, "attribution": ATTRIBUTION,
            "rules": "Score each item 1 only for explicit, correct, uncontradicted "
                     "explanation; omissions/unsupported inventions score 0. "
                     "Record source citation accuracy separately. A full loop pass "
                     "requires factual 5/5 and attribution 5/5.",
            "scope": "Normal prompt -> tool call -> result feedback; not every "
                     "special command, playbook or error-handling branch",
            "citation_rules": "Record correct source-bound references for main, "
                              "start_cli and Agent.run separately from actor scores; "
                              "flag fabricated source labels or misplaced claims.",
        },
        "paired_order": order, "results": [],
    }

    def save() -> None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    # Persist all input bytes, order and scoring before requesting any answers.
    save()
    try:
        for pair, arms in enumerate(order, 1):
            for arm in arms:
                before = generation(settings["INGESTION_SERVICE_URL"], repo_id,
                                    pin["ingestion_id"], pin["commit_sha"])
                if fetch(f'{settings["LLM_SERVICE_URL"]}/version') != version:
                    raise ValueError("LLM runtime changed")
                started = time.monotonic()
                response = fetch(wire["url"], payloads[arm], timeout=600)
                elapsed = round(time.monotonic() - started, 2)
                after = generation(settings["INGESTION_SERVICE_URL"], repo_id,
                                   pin["ingestion_id"], pin["commit_sha"])
                if ({key: response.get(key) for key in identity} != identity
                        or response.get("fallback_from") is not None
                        or fetch(f'{settings["LLM_SERVICE_URL"]}/version') != version):
                    raise ValueError("Model/prompt/runtime/fallback differs")
                result["results"].append({
                    "pair": pair, "arm": arm, "response": response,
                    "generation_before": before, "generation_after": after,
                    "elapsed_seconds": elapsed,
                })
                save()
                print(f"Pair {pair} {arm}: {elapsed}s", flush=True)
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
