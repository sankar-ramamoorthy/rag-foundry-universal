"""The held-out corpus pin record (#315) agrees with the frozen manifest."""

import json
from pathlib import Path

HELD_OUT = (
    Path(__file__).resolve().parents[1] / "DOCS/evaluations/code-evidence-held-out"
)
PIN = json.loads((HELD_OUT / "held-out-corpus-pin.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((HELD_OUT / "manifest.json").read_text(encoding="utf-8"))
STATUSES = {"verified", "reported", "unverified"}
# The werkzeug generation is a verified snapshot (#305): its commit differs
# from the upstream pin by design; its tree is checked instead.
SNAPSHOT_COMMIT = "585fb463d91ea384ae35e4d13ecc9294d0c911f2"


def test_pin_covers_exactly_the_manifest_repositories():
    assert set(PIN["repositories"]) == set(MANIFEST["pins"])


def test_pinned_commits_match_the_manifest_or_the_verified_snapshot():
    for name, repo in PIN["repositories"].items():
        upstream = MANIFEST["pins"][name]["commit"]
        if name == "pallets/werkzeug":
            assert repo["pinned_commit"] == SNAPSHOT_COMMIT
            assert repo["snapshot"]["upstream_pinned_commit"] == upstream
        else:
            assert repo["pinned_commit"] == upstream
        assert repo["generation"]["commit_sha"]["value"] == repo["pinned_commit"]


def test_every_frozen_function_is_recorded_with_the_manifest_hash():
    for name, repo in PIN["repositories"].items():
        recorded = {f["canonical_id"]: f for f in repo["frozen_functions"]["functions"]}
        expected = {
            f for c in MANIFEST["cases"] if c["repo"] == name for f in c["functions"]
        }
        assert set(recorded) == expected
        for cid, f in recorded.items():
            assert f["manifest_sha256"] == MANIFEST["sources"][cid]["sha256"]
            assert f["result"] == "MATCH"
            assert f["stored_text_sha256"] == f["manifest_sha256"]


def test_every_fact_has_a_known_status_and_unverified_facts_carry_no_value():
    def walk(node):
        if isinstance(node, dict):
            if "status" in node:
                assert node["status"] in STATUSES
                if node["status"] == "unverified":
                    assert node.get("value") is None
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(PIN)
