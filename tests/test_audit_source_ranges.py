"""Issue #416 WP6: the source-range audit script.

A fake source reader and a fake database stand in for the real ones, so these
tests check the audit's logic: that it recognizes exact correspondence and every
way a range can be wrong, that sampling is deterministic, that it pins and checks
the generation, that it is read-only and leaks no address, and that its exit
status and result record what an acceptance run needs.
"""

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_source_ranges.py"
SPEC = importlib.util.spec_from_file_location("audit_source_ranges", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit_mod = importlib.util.module_from_spec(SPEC)
sys.modules["audit_source_ranges"] = audit_mod  # dataclasses resolve annotations here
SPEC.loader.exec_module(audit_mod)

Passage = audit_mod.Passage
pytestmark = pytest.mark.unit

GEN = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"
REPO = "00000000-0000-4000-8000-0000000000aa"

FILE = "".join(f"line {i:03d} of the module\n" for i in range(1, 1301))
FILE_LINES = audit_mod.split_lf(FILE)


def lines(start, end):
    return "".join(FILE_LINES[start - 1 : end])


class FakeSource:
    """A source reader over one file, with the real API's 500-line page cap."""

    def __init__(self, generation=GEN, corrupt_digest=False, change_after=None):
        self.generation = generation
        self.corrupt_digest = corrupt_digest
        self.change_after = change_after
        self.calls = []

    def __call__(self, path, start, end):
        self.calls.append((path, start, end))
        assert path == "m.py"
        assert end - start + 1 <= 500, "reader must page at 500 lines"
        text = lines(start, end)
        eof = end >= len(FILE_LINES)
        generation = self.generation
        if self.change_after is not None and len(self.calls) > self.change_after:
            generation = OTHER
        digest = "0" * 64 if self.corrupt_digest else hashlib.sha256(
            text.encode()).hexdigest()
        return {
            "generation_id": generation,
            "start_line": start,
            "end_line": min(end, len(FILE_LINES)),
            "next_start_line": None if eof else end + 1,
            "text": text,
            "returned_text_sha256": digest,
        }


def passage(i, start, end, text=None, reason=None, path="m.py"):
    return Passage(
        document_id=f"d{i:04d}", chunk_index=i, path=path, start_line=start,
        end_line=end, range_reason=reason,
        text=lines(start, end) if text is None and start else text,
    )


def good(n):
    return [passage(i, 1 + i, 3 + i) for i in range(n)]


# --- exact correspondence ---


def test_a_passage_equal_to_its_lines_resolves():
    outcome = audit_mod.verify_passage(FakeSource(), passage(0, 10, 14), GEN)
    assert outcome == ("ok", "")


def test_a_window_that_starts_and_ends_inside_its_lines_resolves():
    full = lines(10, 12)
    inside = full[5:-7]  # starts mid first line, ends mid last line
    assert audit_mod.verify_passage(
        FakeSource(), passage(0, 10, 12, text=inside), GEN) == ("ok", "")


def test_an_off_by_one_range_is_a_mismatch():
    # The text is lines 10-12, but the cited range is 11-13.
    p = passage(0, 11, 13, text=lines(10, 12))
    assert audit_mod.verify_passage(FakeSource(), p, GEN)[0] == "mismatch"


def test_a_range_that_is_too_wide_still_has_to_contain_the_text_at_its_edges():
    # Text of lines 10-12 cited as 9-13: the text is inside but does not start on
    # the first cited line or end on the last, so it is not that passage's range.
    p = passage(0, 9, 13, text=lines(10, 12))
    assert audit_mod.verify_passage(FakeSource(), p, GEN)[0] == "mismatch"


def test_text_from_elsewhere_in_the_file_is_a_mismatch():
    p = passage(0, 10, 12, text=lines(200, 202))
    assert audit_mod.verify_passage(FakeSource(), p, GEN)[0] == "mismatch"


def test_a_passage_without_text_cannot_be_verified():
    p = Passage("d", 0, "m.py", 1, 2, None, None)
    assert audit_mod.verify_passage(FakeSource(), p, GEN)[0] == "no_text"


# --- the reader's own checks ---


def test_a_range_over_500_lines_is_read_in_pages_and_joined():
    source = FakeSource()
    p = passage(0, 100, 899)  # 800 lines
    assert audit_mod.verify_passage(source, p, GEN) == ("ok", "")
    assert [(s, e) for _, s, e in source.calls] == [(100, 599), (600, 899)]


def test_a_returned_text_digest_mismatch_is_an_error():
    outcome = audit_mod.verify_passage(
        FakeSource(corrupt_digest=True), passage(0, 1, 3), GEN)
    assert outcome[0] == "read_error" and "digest" in outcome[1]


def test_a_generation_that_differs_from_the_pinned_one_is_reported():
    outcome = audit_mod.verify_passage(FakeSource(generation=OTHER), passage(0, 1, 3), GEN)  # noqa: E501
    assert outcome[0] == "generation_changed"


def test_a_generation_change_part_way_through_a_run_is_caught():
    source = FakeSource(change_after=3)
    result = audit_mod.audit(good(10), [], source, GEN, seed=1, sample_size=10,
                             acceptance=False)
    assert result["outcomes"]["ok"] == 3
    assert result["outcomes"]["generation_changed"] == 7
    assert result["passed"] is False


def test_a_range_past_the_end_of_the_file_is_out_of_bounds():
    p = Passage("d", 0, "m.py", 1299, 1305, None, lines(1299, 1300))
    assert audit_mod.verify_passage(FakeSource(), p, GEN)[0] == "range_out_of_bounds"


def test_a_reader_error_is_an_outcome_not_a_crash():
    def broken(path, start, end):
        raise audit_mod.ReadError("read_error", "HTTP 500")

    assert audit_mod.verify_passage(broken, passage(0, 1, 3), GEN)[0] == "read_error"


# --- deterministic sampling ---


def test_the_same_seed_gives_the_same_sample_regardless_of_input_order():
    population = good(300)
    a, _ = audit_mod.sample_passages(population, seed=416, size=40)
    b, _ = audit_mod.sample_passages(list(reversed(population)), seed=416, size=40)
    assert [p.key for p in a] == [p.key for p in b]
    assert len({p.key for p in a}) == 40


def test_a_different_seed_gives_a_different_sample():
    population = good(300)
    a, _ = audit_mod.sample_passages(population, 1, 40)
    b, _ = audit_mod.sample_passages(population, 2, 40)
    assert [p.key for p in a] != [p.key for p in b]


def test_a_sample_larger_than_the_population_is_the_whole_population_and_flagged():
    sample, short = audit_mod.sample_passages(good(25), 1, 1000)
    assert len(sample) == 25 and short is True


# --- the audit result ---


def passing_population(n=1200):
    return [passage(i, 1 + (i % 300), 3 + (i % 300)) for i in range(n)]


def test_a_clean_acceptance_run_passes_and_records_everything_needed_to_repeat_it():
    unranged = [passage(5000 + i, None, None, text="x",
                        reason="artifact range not verified") for i in range(50)]
    result = audit_mod.audit(passing_population(), unranged, FakeSource(), GEN,
                             seed=416, sample_size=1000, acceptance=True)
    assert result["passed"] is True
    assert result["sample_size_checked"] == 1000
    assert result["acceptance_floor_met"] is True
    assert result["incorrect_ranges"] == 0
    assert result["generation_id"] == GEN and result["seed"] == 416
    assert result["passages_total"] == 1250 and result["passages_with_range"] == 1200
    assert result["null_reasons"] == {"artifact range not verified": 50}
    # Eligible excludes artifacts whose range was never verified.
    assert result["range_share_of_eligible"] == 1.0
    assert result["range_share_of_all"] == round(1200 / 1250, 6)


def test_the_same_inputs_give_the_same_result():
    args = (passing_population(), [], FakeSource(), GEN)
    first = audit_mod.audit(*args, seed=7, sample_size=1000, acceptance=True)
    second = audit_mod.audit(passing_population(), [], FakeSource(), GEN,
                             seed=7, sample_size=1000, acceptance=True)
    assert first == second


def test_one_wrong_range_fails_the_run_and_is_listed():
    population = passing_population()
    population[3] = passage(3, 40, 42, text=lines(10, 12))  # off by 30 lines
    result = audit_mod.audit(population, [], FakeSource(), GEN, seed=1,
                             sample_size=len(population), acceptance=False)
    assert result["incorrect_ranges"] == 1 and result["passed"] is False
    failure = result["failures_first_50"][0]
    assert failure["outcome"] == "mismatch" and failure["chunk_index"] == 3


def test_an_acceptance_run_below_the_floor_does_not_pass():
    result = audit_mod.audit(good(200), [], FakeSource(), GEN, seed=1,
                             sample_size=1000, acceptance=True)
    assert result["sample_size_checked"] == 200
    assert result["acceptance_floor_met"] is False and result["passed"] is False


def test_a_null_without_a_reason_or_with_an_unknown_one_fails():
    for reason in (None, "", "because"):
        bad = [passage(1, None, None, text="x", reason=reason)]
        result = audit_mod.audit(good(5), bad, FakeSource(), GEN, seed=1,
                                 sample_size=5, acceptance=False)
        assert result["null_without_reason_or_unknown"] == 1
        assert result["passed"] is False


def test_legacy_and_current_reasons_are_both_accepted():
    reasons = sorted(audit_mod.KNOWN_REASONS)
    unranged = [passage(i, None, None, text="x", reason=r)
                for i, r in enumerate(reasons)]
    result = audit_mod.audit(good(5), unranged, FakeSource(), GEN, seed=1,
                             sample_size=5, acceptance=False)
    assert result["null_without_reason_or_unknown"] == 0 and result["passed"] is True


def test_a_range_that_also_carries_a_reason_fails():
    both = passage(0, 1, 3, reason="artifact range not verified")
    result = audit_mod.audit([both] + good(4)[1:], [], FakeSource(), GEN, seed=1,
                             sample_size=5, acceptance=False)
    assert result["ranged_passages_that_also_carry_a_reason"] == 1
    assert result["passed"] is False


# --- the command line, with the database and the network replaced ---


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.statements.append(" ".join(sql.split()))
        self.sql = sql

    def fetchall(self):
        if "chunk_text" in self.sql:
            return [(p.document_id, p.chunk_index, p.text) for p in self.conn.passages]
        return [(p.document_id, p.chunk_index, p.path, p.start_line, p.end_line,
                 p.range_reason) for p in self.conn.passages]


class FakeConn:
    def __init__(self, passages):
        self.passages = passages
        self.statements = []
        self.read_only = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return FakeCursor(self)


def run_cli(monkeypatch, tmp_path, passages, extra=(), source=None):
    conn = FakeConn(passages)
    source = source or FakeSource()
    monkeypatch.setattr(audit_mod, "discover", lambda *a, **k: {
        "generation_id": GEN, "commit_sha": "c" * 40,
        "orchestrator_version": {"git_sha": "d" * 40}})
    monkeypatch.setattr(audit_mod, "http_reader", lambda *a, **k: source)
    out = tmp_path / "result.json"
    args = audit_mod.build_parser().parse_args([
        "--base-url", "http://foundry.test:8004", "--repo-id", REPO,
        "--dsn", "postgresql://auditor@db.test/x", "--seed", "416",
        "--out", str(out), *extra])
    code = audit_mod.run(args, connect=lambda dsn: conn)
    return code, conn, json.loads(out.read_text()) if out.exists() else None


def test_cli_database_path_is_read_only_selects_and_passes(monkeypatch, tmp_path):
    code, conn, result = run_cli(monkeypatch, tmp_path, passing_population(1200),
                                 ["--sample-size", "1000", "--acceptance"])
    assert code == 0 and result["passed"] is True
    assert conn.read_only is True
    assert conn.statements and all(s.upper().startswith("SELECT") for s in conn.statements)  # noqa: E501
    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", re.I)  # noqa: E501
    assert not any(forbidden.search(s) for s in conn.statements)


def test_cli_result_records_generation_commit_versions_and_hides_the_address(
        monkeypatch, tmp_path):
    code, _, result = run_cli(monkeypatch, tmp_path, passing_population(1200),
                              ["--sample-size", "1000", "--acceptance"])
    assert result["generation_id"] == GEN and result["commit_sha"] == "c" * 40
    assert result["orchestrator_version"] == {"git_sha": "d" * 40}
    assert result["seed"] == 416 and result["sample_size_checked"] == 1000
    text = json.dumps(result)
    assert "foundry.test" not in text and "8004" not in text
    assert "auditor" not in text and "db.test" not in text
    assert result["base_url"].startswith("sha256:")


def test_cli_exit_status_is_one_for_a_wrong_range(monkeypatch, tmp_path):
    population = passing_population(1200)
    population[0] = passage(0, 40, 42, text=lines(10, 12))
    code, _, result = run_cli(monkeypatch, tmp_path, population,
                              ["--sample-size", "1200"])
    assert code == 1 and result["incorrect_ranges"] == 1


def test_cli_passages_json_needs_no_database(monkeypatch, tmp_path):
    rows = [{"document_id": p.document_id, "chunk_index": p.chunk_index,
             "path": p.path, "start_line": p.start_line, "end_line": p.end_line,
             "text": p.text} for p in good(30)]
    path = tmp_path / "passages.json"
    path.write_text(json.dumps(rows))
    code, conn, result = run_cli(monkeypatch, tmp_path, [],
                                 ["--passages-json", str(path), "--sample-size", "30"])
    assert code == 0 and result["passage_source"] == "passages-json"
    assert conn.statements == []  # the database was never touched


def test_cli_refuses_a_small_acceptance_sample_before_doing_anything(
        monkeypatch, tmp_path, capsys):
    args = audit_mod.build_parser().parse_args([
        "--base-url", "http://foundry.test", "--repo-id", REPO, "--seed", "1",
        "--sample-size", "10", "--acceptance"])
    assert audit_mod.run(args) == 2
    assert "1000" in capsys.readouterr().err


def test_cli_needs_an_address_it_does_not_default_one(monkeypatch, capsys):
    monkeypatch.delenv("FOUNDRY_ORCHESTRATOR_URL", raising=False)
    args = audit_mod.build_parser().parse_args(["--repo-id", REPO, "--seed", "1"])
    assert args.base_url is None
    assert audit_mod.run(args) == 2


def test_cli_needs_a_database_setting_when_no_passages_file(monkeypatch, tmp_path):
    for key in ("PGHOST", "PGSERVICE", "FOUNDRY_AUDIT_DSN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(audit_mod, "discover", lambda *a, **k: {
        "generation_id": GEN, "commit_sha": None, "orchestrator_version": None})
    args = audit_mod.build_parser().parse_args([
        "--base-url", "http://foundry.test", "--repo-id", REPO, "--seed", "1"])
    assert audit_mod.run(args, connect=lambda dsn: FakeConn([])) == 2


def test_the_script_contains_no_private_address_or_credentials():
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}",  # noqa: E501
                         source)
    assert ".ts.net" not in source
    assert not re.search(r"postgres(?:ql)?://\w+:\w+@", source)
    assert "password" not in source.lower()


def test_the_script_has_no_write_statement():
    source = SCRIPT.read_text(encoding="utf-8")
    sql_blocks = re.findall(r'"""\s*(SELECT.*?)"""', source, re.S)
    assert len(sql_blocks) == 2  # the two read queries
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b",
                         " ".join(sql_blocks), re.I)
