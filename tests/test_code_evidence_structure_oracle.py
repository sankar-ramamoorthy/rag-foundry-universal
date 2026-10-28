"""Invariants for the offline structural-context oracle (#276); no network."""

import importlib.util
import re
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPT / "code_evidence_structure_oracle.py"
SPEC = importlib.util.spec_from_file_location("structure_oracle", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)

MARKER = re.compile(r"^\s*# \.\.\. lines? \d+(-\d+)? omitted$")


def _fs(source: str):
    return oracle.FunctionStructure(textwrap.dedent(source).strip("\n"))


def _t1(fs, items, reading="first"):
    witness, _, _ = oracle.witness_lines(fs, items, reading)
    sets, *_ = oracle.tier_sets(fs, witness)
    return sets, witness


def _text(fs, idxs):
    return "\n".join(fs.lines[i] for i in sorted(idxs))


BRANCHY = """
@decorator
def f(a, b):
    x = compute(a)
    if x > 1:
        first_branch(x)
    elif x > 0:
        second_branch(x)
    else:
        last_branch(x)
    return x
"""


def test_else_branch_keeps_every_condition_that_selects_it():
    fs = _fs(BRANCHY)
    sets, _ = _t1(fs, ["last_branch(x)"])
    text = _text(fs, sets["T1"])
    for needle in ("@decorator", "def f(a, b):", "if x > 1:", "elif x > 0:",
                   "else:", "last_branch(x)"):
        assert needle in text
    assert "first_branch" not in text and "second_branch" not in text


def test_try_handler_and_finally_keep_their_headers():
    fs = _fs("""
        def g():
            try:
                risky()
            except ValueError as err:
                recover(err)
            else:
                happy()
            finally:
                cleanup()
    """)
    for target, needles in {
        "recover(err)": ("try:", "except ValueError as err:"),
        "happy()": ("try:", "else:"),
        "cleanup()": ("try:", "finally:"),
    }.items():
        sets, _ = _t1(fs, [target])
        text = _text(fs, sets["T1"])
        assert all(n in text for n in needles), (target, text)


def test_loop_and_with_headers_are_kept():
    fs = _fs("""
        def h(rows):
            with lock:
                for row in rows:
                    emit(row)
    """)
    sets, _ = _t1(fs, ["emit(row)"])
    text = _text(fs, sets["T1"])
    assert "with lock:" in text and "for row in rows:" in text


def test_witness_in_the_middle_of_an_expression_gets_the_whole_statement():
    fs = _fs("""
        def k(cfg):
            limit = getattr(
                cfg,
                "max_tokens",
                default_limit,
            )
            return limit
    """)
    _, witness = _t1(fs, ['"max_tokens"'])
    text = _text(fs, witness)
    assert text.startswith("    limit = getattr(") and text.rstrip().endswith(")")


def test_blocks_hold_only_verbatim_lines_and_explicit_markers():
    fs = _fs(BRANCHY)
    sets, _ = _t1(fs, ["last_branch(x)"])
    for idxs in sets.values():
        block, markers, marker_bytes = oracle.render_block(fs.lines, sorted(idxs))
        real = [ln for ln in block.split("\n") if not MARKER.match(ln)]
        assert real == [fs.lines[i] for i in sorted(idxs)]
        assert markers == len(block.split("\n")) - len(real)
        assert marker_bytes >= markers * 10 or markers == 0


def test_marker_wording_and_blank_only_gaps():
    lines = ["a = 1", "", "b = 2", "c = 3", "d = 4", "e = 5"]
    block, markers, _ = oracle.render_block(lines, [0, 2, 5])
    assert markers == 1
    assert "# ... lines 4-5 omitted" in block
    assert "omitted" not in block.split("\n")[1]  # blank-only gap: no marker
    single, _, _ = oracle.render_block(lines, [0, 2, 3, 5])
    assert "# ... line 5 omitted" in single


def test_definitions_one_hop_versus_closure_and_external_names():
    fs = _fs("""
        def m(p):
            base = p + 1
            mid = base * 2
            out = mid + external_value
            use(out)
    """)
    witness, _, _ = oracle.witness_lines(fs, ["use(out)"], "first")
    t1 = witness | set(fs.structure(5))
    one, rep1 = oracle.DefinitionResolver(fs, t1, closure=False).run()
    full, rep3 = oracle.DefinitionResolver(fs, t1, closure=True).run()
    assert {fs.lines[i].strip() for i in one} == {"out = mid + external_value"}
    assert {fs.lines[i].strip() for i in full} == {
        "out = mid + external_value", "mid = base * 2", "base = p + 1"}
    assert "external_value" in rep3["external"] and "use" in rep3["external"]
    assert "print" not in rep3["external"]
    assert rep1["params"] == 0 and rep3["params"] == 1  # `p` read by `base = p + 1`


def test_conditional_redefinition_is_reported_not_hidden():
    fs = _fs("""
        def n(flag):
            if flag:
                value = 1
            else:
                value = 2
            consume(value)
    """)
    witness, _, _ = oracle.witness_lines(fs, ["consume(value)"], "first")
    _, rep = oracle.DefinitionResolver(fs, witness, closure=False).run()
    assert rep["multiple_candidate_definitions"] == ["value"]


def test_ambiguous_expressions_are_flagged_and_all_reading_is_a_superset():
    fs = _fs("""
        def p():
            step()
            other()
            step()
    """)
    first, _, amb = oracle.witness_lines(fs, ["step()"], "first")
    every, _, _ = oracle.witness_lines(fs, ["step()"], "all")
    assert amb and first < every and len(every) == 2


def test_unlocated_expression_is_a_failure():
    fs = _fs("""
        def q():
            pass
    """)
    _, failures, _ = oracle.witness_lines(fs, ["missing()"], "first")
    assert failures and failures[0].startswith("unlocated:")


@pytest.fixture(scope="module")
def result():
    return oracle.run()


def test_real_cases_are_monotonic_complete_and_labelled_as_an_oracle(result):
    assert "bounds feasibility only" in result["oracle_notice"]
    assert set(result["cases"]) == {"L1", "L2", "L3", "F1", "F2", "F3"}
    for case in result["cases"].values():
        for reading in oracle.READINGS:
            r = case[reading]
            assert r["failures"] == []
            sizes = [r["tiers"][t]["bytes"] for t in oracle.TIERS]
            assert sizes == sorted(sizes)
            for t in oracle.TIERS:
                tier = r["tiers"][t]
                assert tier["fits"] == (tier["bytes"] <= result["cap_bytes"])
                assert tier["slack"] == result["cap_bytes"] - tier["bytes"]


def test_all_reading_never_costs_less_than_first_reading(result):
    for case in result["cases"].values():
        for t in oracle.TIERS:
            first = case["first"]["tiers"][t]["bytes"]
            assert case["all"]["tiers"][t]["bytes"] >= first


def test_every_real_block_contains_only_verbatim_lines_and_markers():
    manifest = oracle.json.loads(oracle.base.MANIFEST.read_text(encoding="utf-8"))
    checked = 0
    for case in manifest["cases"]:
        by_doc: dict[str, list[str]] = {}
        for group in (case["operations"], case["dependencies"]):
            for w in group:
                by_doc.setdefault(w["canonical_id"], []).extend(w["expressions"])
        for cid, items in by_doc.items():
            fs = oracle.FunctionStructure(manifest["sources"][cid]["text"])
            witness, _, _ = oracle.witness_lines(fs, items, "all")
            sets, *_ = oracle.tier_sets(fs, witness)
            for idxs in sets.values():
                block, _, _ = oracle.render_block(fs.lines, sorted(idxs))
                real = [ln for ln in block.splitlines() if not MARKER.match(ln)]
                assert real == [fs.lines[i] for i in sorted(idxs)]
                checked += 1
    assert checked == 44
