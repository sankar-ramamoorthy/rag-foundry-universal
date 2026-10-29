"""The frozen E1 held-out manifest (#281); no network, no clones.

Frozen after the independent review (declaration section 9). It is pinned by its
recorded SHA-256, and these checks hold: every expression is a verbatim line fragment
of its stored source text and occurs on exactly one line of that function, the stored
hashes match, and the declared shape and exclusions hold.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
MANIFEST = HELD_OUT / "manifest.json"
EXCLUDED = {"HKUDS/LightRAG", "sankar-ramamoorthy/rag-foundry-universal",
            "sankar-ramamoorthy/py-coding-agent"}


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_declared_shape_and_exclusions(manifest):
    cases = manifest["cases"]
    assert len(cases) == 12
    repos = {c["repo"] for c in cases}
    assert len(repos) == 3 and not repos & EXCLUDED
    assert all(sum(c["repo"] == r for c in cases) == 4 for r in repos)
    assert repos == set(manifest["pins"])
    assert len({c["id"] for c in cases}) == 12


def test_operations_and_dependencies_are_in_the_declared_range(manifest):
    for c in manifest["cases"]:
        assert 4 <= len(c["operations"]) <= 5, c["id"]
        assert 3 <= len(c["dependencies"]) <= 4, c["id"]


def test_every_expression_is_verbatim_and_unique_in_its_function(manifest):
    checked = 0
    for c in manifest["cases"]:
        for entry in (*c["operations"], *c["dependencies"]):
            lines = manifest["sources"][entry["canonical_id"]]["text"].split("\n")
            for expr in entry["expressions"]:
                hits = [ln for ln in lines if expr in ln]
                assert len(hits) == 1, (c["id"], expr)
                checked += 1
    assert checked > 100


def test_source_hashes_match_and_functions_belong_to_a_case(manifest):
    used = {e["canonical_id"] for c in manifest["cases"]
            for e in (*c["operations"], *c["dependencies"])}
    assert set(manifest["sources"]) == used
    for cid, src in manifest["sources"].items():
        assert hashlib.sha256(src["text"].encode()).hexdigest() == src["sha256"], cid


def test_questions_do_not_quote_an_expression(manifest):
    for c in manifest["cases"]:
        query = c["query"]
        for entry in (*c["operations"], *c["dependencies"]):
            for expr in entry["expressions"]:
                if len(expr) > 25:
                    assert expr not in query, (c["id"], expr)


def test_natural_language_questions_name_neither_symbol_nor_file(manifest):
    """Natural-language questions use no backticks, no file path and no long identifier.

    Short names that are also ordinary words (for example `run`) are judged by the
    reviewer; the question must at least not present them as code or a command.
    """
    for c in manifest["cases"]:
        if c["style"] != "natural":
            continue
        assert "`" not in c["query"], c["id"]
        for cid in c["functions"]:
            path, name = cid.split("#")
            assert path not in c["query"], (c["id"], path)
            assert path.rsplit("/", 1)[-1] not in c["query"], (c["id"], path)
            if len(name) >= 5:
                assert name not in c["query"], (c["id"], name)


def test_known_limitations_record_the_reviewed_concentration_and_overlap(manifest):
    text = " ".join(manifest["known_limitations"])
    for needle in ("H1, H2, H4", "P2 and P4", "tools/dumppdf.py"):
        assert needle in text, needle
    # recorded as limitations, not acted on: the selected cases are all still present
    assert {"H1", "H2", "H4", "P2", "P4"} <= {c["id"] for c in manifest["cases"]}


def test_revised_cases_map_each_item_to_the_clause_that_needs_it(manifest):
    revised = [c for c in manifest["cases"]
               if any(r.get("round") == 1 for r in c.get("revisions", []))]
    assert {c["id"] for c in revised} == {"H1", "H3", "P1", "W2", "W3", "W4"}
    for c in revised:
        for entry in (*c["operations"], *c["dependencies"]):
            assert entry.get("needed_for"), (c["id"], entry["name"])


def _lf(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_manifest_matches_its_recorded_checksum():
    recorded = (HELD_OUT / "manifest.sha256").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", recorded)
    assert hashlib.sha256(_lf(MANIFEST).encode("utf-8")).hexdigest() == recorded, (
        "the frozen held-out manifest changed; supersede it with a new dated "
        "declaration instead of editing it"
    )


def test_manifest_is_frozen_and_bound_to_the_declarations_it_was_built_under(manifest):
    assert manifest["status"] == "frozen-before-any-run"
    d = manifest["declaration"]
    e1 = ROOT / "DOCS/evaluations/code-evidence-e1"
    strat = (HELD_OUT / "stratification.sha256").read_text().strip()
    assert d["stratification_sha256"] == strat
    assert d["go_rate_addendum_sha256"] == (
        e1 / "statement-level-contract-addendum-go-rate.sha256").read_text().strip()
    assert d["statement_level_contract_sha256"] == (
        e1 / "statement-level-contract.sha256").read_text().strip()


def test_manifest_matches_the_authored_case_specs(manifest):
    specs = {}
    for f in (HELD_OUT / "cases").glob("*.json"):
        spec = json.loads(f.read_text(encoding="utf-8"))
        specs[spec["id"]] = spec
    assert set(specs) == {c["id"] for c in manifest["cases"]}
    def core(items):
        return [(e["name"], e["canonical_id"], e["expressions"]) for e in items]
    for c in manifest["cases"]:
        spec = specs[c["id"]]
        assert c["query"] == spec["query"], c["id"]
        assert core(c["operations"]) == core(spec["operations"]), c["id"]
        assert core(c["dependencies"]) == core(spec["dependencies"]), c["id"]


def test_each_repository_has_its_license_text_and_attribution(manifest):
    readme = _lf(HELD_OUT / "README.md")
    for repo in manifest["pins"]:
        name = f"{repo.replace('/', '-')}.LICENSE.txt"
        assert (HELD_OUT / "licenses" / name).is_file()
        assert repo in readme and manifest["pins"][repo]["commit"] in readme
