"""Verify frozen evidence, source manifests and matched grounding controls."""

import hashlib
import json
from pathlib import Path

from issue254_complete_evidence_eval import digest


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "DOCS/test_results"
PREFIX = "2026-10-12-issue-254-"


def read(name):
    return json.loads((RESULTS / (PREFIX + name + ".json")).read_text(
        encoding="utf-8"))


def main():
    original = read("complete-evidence-experiment")
    run = read("grounding-contract")
    automatic = read("automatic-coverage")
    selection = automatic["selection"]
    assert automatic["selector_sha256"] == digest(
        (ROOT / "scripts/issue254_automatic_coverage_eval.py").read_text(
            encoding="utf-8"))
    sources = read("overview-control-comparison-context")["pinned_source"]
    assert run["status"] == "complete" and len(run["results"]) == 6
    evidence = "\n\n".join(f'[Source: {e["canonical_id"]}]\n{e["text"]}'
                             for e in original["source_manifest"])
    assert len(evidence.encode()) == 4024
    assert run["payloads"]["frozen"] == original["payloads"]["complete_evidence"]
    assert run["payloads"]["contract"]["context"] == (
        run["contract"] + "\n" + run["payloads"]["frozen"]["context"])
    assert run["payloads"]["contract"]["query"] == run["payloads"]["frozen"]["query"]
    assert run["scoring"] == original["scoring"]
    for payload in run["payloads"].values():
        assert payload["context"].endswith(evidence)
    for entry in original["source_manifest"] + selection["manifest"]:
        source = sources[entry["canonical_id"].split("#")[0]]["text"]
        assert digest(source) == entry["source_sha256"]
        assert entry["text"] == "\n".join(source.splitlines()[
            entry["first_line"] - 1:entry["last_line"]])
        assert digest(entry["text"]) == entry["text_sha256"]
    assert selection["evidence_bytes"] == len(selection["evidence"].encode()) <= 4096
    identity = run["model_identity"]
    for result in run["results"]:
        assert {key: result["response"][key] for key in identity} == identity
        assert result["response"].get("fallback_from") is None
        assert result["generation_before"] == result["generation_after"]
        assert result["generation_before"]["ingestion_id"] == run["pin"]["ingestion_id"]
        assert result["generation_before"]["commit_sha"] == run["pin"]["commit_sha"]
    scores = read("grounding-scores")
    responses = {(r["pair"], r["arm"]): r["response"]["response"]
                 for r in run["results"]}
    for score in scores["results"]:
        assert score["response_sha256"] == digest(
            responses[(score["pair"], score["arm"])])
    for arm in ("frozen", "contract"):
        cases = [s for s in scores["results"] if s["arm"] == arm]
        assert len(cases) == scores["totals"][arm]["runs"] == 3
        for axis in ("factual", "attribution"):
            assert sum(sum(s[axis]) for s in cases) == scores["totals"][arm][axis]
        assert sum(sum(s["factual"]) == sum(s["attribution"]) == 5
                   for s in cases) == scores["totals"][arm]["full_loop"]
    runtime = read("policy-candidate-local-runtime")["changed_source_sha256"]
    assert all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
               for path, expected in runtime.items())
    audit = {
        "status": "verified", "requests_verified": 6,
        "original_question_and_evidence_unchanged": True,
        "same_scoring_model_template_pin_no_fallback": True,
        "manual_score_hashes_and_totals_verified": True,
        "contract_added_prompt_bytes": run["contract_bytes"],
        "evidence_bytes": 4024, "automatic_evidence_bytes": 3952,
        "literal_source_manifests_verified": True,
        "candidate_runtime_files_unchanged": runtime,
        "automatic_coverage_review": {
            "primary_statement_witnesses": {
                "input": True, "provider": True, "extraction": True,
                "dispatch": True, "feedback": False},
            "startup_handoff": False, "assistant_call_record": False,
            "memory_initializer": False,
            "branch_relationships_preserved": False,
            "full_behavioral_completeness": False,
            "judgment": "Statement witnesses manually reviewed after selection; "
                        "not an execution-path certification. No model requests "
                        "use this incomplete selector output.",
        },
        "limits": "Self-reported runtime identity; defaults stochastic; full "
                  "source supplied to offline selector; no held-out validation; "
                  "frozen evidence excludes system-memory initializer.",
    }
    output = RESULTS / (PREFIX + "separated-audit.json")
    output.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print("Verified six requests and both literal source manifests")


if __name__ == "__main__":
    main()
