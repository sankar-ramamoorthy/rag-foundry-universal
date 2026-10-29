"""Self-consistency of the draft E1 held-out manifest (#281); no network, no clones.

The manifest is a draft until the independent review (declaration section 9). These
checks hold regardless: every expression is a verbatim line fragment of its stored
source text and occurs on exactly one line of that function, the stored hashes match,
and the declared shape and exclusions hold.
"""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "DOCS/evaluations/code-evidence-held-out/manifest.draft.json"
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
