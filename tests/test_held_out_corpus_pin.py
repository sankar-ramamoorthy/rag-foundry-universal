"""The held-out corpus pin record (#315) is consistent with the frozen manifest.

These tests read repository files only. They do NOT re-read production: the
measured values (counts, stored-text hashes, generation state) are what
scripts/held_out_corpus_pin.py recorded on the date in the pin, and nothing
here independently verifies them. What is checked is that the pin covers the
frozen manifest exactly, agrees with its commits and hashes, and does not
present unverified or inferred facts as measured.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
PIN = json.loads((HELD_OUT / "held-out-corpus-pin.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((HELD_OUT / "manifest.json").read_text(encoding="utf-8"))
STATUSES = set(PIN["status_vocabulary"])
# The werkzeug generation is a verified snapshot (#305): its commit differs
# from the upstream pin by design; its tree is recorded instead.
SNAPSHOT_COMMIT = "585fb463d91ea384ae35e4d13ecc9294d0c911f2"


def test_pin_records_the_current_frozen_manifest_checksum():
    raw = (HELD_OUT / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
    assert PIN["manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    assert PIN["manifest_sha256"] == (HELD_OUT / "manifest.sha256").read_text().strip()


def test_pin_covers_exactly_the_manifest_repositories():
    assert set(PIN["repositories"]) == set(MANIFEST["pins"])


def test_pinned_commits_match_the_manifest_or_the_verified_snapshot():
    for name, repo in PIN["repositories"].items():
        upstream = MANIFEST["pins"][name]["commit"]
        expected = SNAPSHOT_COMMIT if name == "pallets/werkzeug" else upstream
        assert repo["source"]["pinned_commit"] == upstream
        assert repo["source"]["recorded_commit"] == expected
        assert repo["generation"]["ingested_commit_sha"]["value"] == expected
    snap = PIN["repositories"]["pallets/werkzeug"]["snapshot"]
    werkzeug_pin = MANIFEST["pins"]["pallets/werkzeug"]["commit"]
    assert snap["upstream_pinned_commit"] == werkzeug_pin


def test_every_frozen_function_is_recorded_with_the_manifest_hash():
    for name, repo in PIN["repositories"].items():
        block = repo["function_text_sha256_vs_manifest"]
        recorded = {f["canonical_id"]: f for f in block["functions"]}
        expected = {
            f for c in MANIFEST["cases"] if c["repo"] == name for f in c["functions"]
        }
        assert set(recorded) == expected
        assert block["matched"] == block["of"] == len(expected)
        for cid, f in recorded.items():
            assert f["manifest_sha256"] == MANIFEST["sources"][cid]["sha256"]
            assert f["result"] == "MATCH"
            assert f["stored_text_sha256"] == f["manifest_sha256"]


def test_runbook_counts_are_recorded_as_measured_integers():
    for repo in PIN["repositories"].values():
        gen = repo["generation"]
        for key in ("node_count", "chunk_count"):
            assert gen[key]["status"] == "measured"
            assert isinstance(gen[key]["value"], int) and gen[key]["value"] > 0
        assert gen["generation_status"]["value"] == "ready"
        assert gen["generation_status"]["status"] == "fetched"
        assert gen["is_incremental"]["value"] is False


def test_every_fact_has_a_known_status_and_unverified_facts_carry_no_value():
    def walk(node):
        if isinstance(node, dict):
            if "status" in node and "source" in node:
                assert node["status"] in STATUSES
                if node["status"] == "unverified":
                    assert node.get("value") is None
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(PIN)


def test_historical_facts_are_not_presented_as_observed():
    for repo in PIN["repositories"].values():
        runtime = repo["generation"]["deployed_runtime_git_sha"]
        assert runtime["status"] == "unverified" and runtime["value"] is None
    embedder = PIN["embedder"]
    assert embedder["digest_used_for_each_ingestion"]["status"] == "unverified"
    assert embedder["digest_used_for_each_ingestion"]["value"] is None
    assert embedder["inference"]["status"] == "inferred"
    assert embedder["current_host_digest"]["status"] == "fetched"
