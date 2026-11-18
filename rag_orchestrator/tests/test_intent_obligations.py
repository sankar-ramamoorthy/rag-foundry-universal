"""Offline software checks for #398."""

import json
from dataclasses import replace

import pytest

from experiments.intent_obligations import experiment as exp
from experiments.intent_obligations.__main__ import evaluate
from experiments.intent_obligations.collect import collect
from experiments.intent_obligations.corpus import Corpus, MODULE
from experiments.intent_obligations.recognition import (
    Captures,
    Recognizers,
    digest,
    request_pack,
)

pytestmark = pytest.mark.unit


def test_compound_obligations_and_authority():
    cases = exp.load_cases()
    compound = next(case for case in cases if case.id == "h05")
    assert exp.route(compound.gold, exp.Scenarios["normal"]) == "inventory_then_rag"
    trace = next(case.gold for case in cases if case.id == "h10")
    for name, scenario in exp.Scenarios.items():
        expected = "investigation" if name == "authorized_gap" else "rag"
        assert exp.route(trace, scenario) == expected


@pytest.fixture
def inputs():
    cases = exp.load_cases()
    pack = request_pack(cases, "mxbai-embed-large:latest", "unit-test:latest")
    return cases, pack


def select(report, arm, case, scenario="normal"):
    return next(
        row
        for row in report["rows"]
        if (row["arm"], row["id"], row["scenario"]) == (arm, case, scenario)
    )


def test_baseline_labels_and_completion(inputs):
    cases, pack = inputs
    report = evaluate(cases, pack, {})
    for case in cases:
        if case.split != "prototype":
            assert select(report, "labels", case.id)["scores"]["route_correct"]
    ctrl = select(report, "labels", "h01")
    inventory = ctrl["inventory_results"][MODULE]
    assert inventory["tool_calls"] == 2 and inventory["model_calls"] == 0
    assert len(inventory["inventory"]) == 15 and ctrl["answer_status"] == "complete"
    assert select(report, "regex", "h01")["scores"]["missed_inventory"]
    assert select(report, "regex", "h15")["answer_status"] == "complete"
    assert select(report, "labels", "h05")["satisfied"] == ["definitions"]
    assert select(report, "labels", "h09")["answer_status"] == "complete"
    assert "cli/ingest.py" in select(report, "labels", "h07")["response"]
    assert "ingrst.py" in select(report, "labels", "h08")["response"]
    assert (
        select(report, "labels", "h01", "explicit_rag")["answer_status"] == "unmeasured"
    )
    assert select(report, "embed", "h01")["status"] == "not_recorded"


def test_recorded_transport_and_permission_replay(inputs, tmp_path):
    cases, pack = inputs
    output = tmp_path / "captures.json"
    revisions = {p["body"]["model"]: "test-revision" for p in pack.values()}
    observed = []

    def send(endpoint, body):
        if body is None:
            return {
                "models": [{"name": m, "digest": rev} for m, rev in revisions.items()]
            }
        observed.append((endpoint, body))
        if endpoint == "/api/embed":
            # Deliberate tie: first prototype wins. No semantic model claim.
            return {
                "model": body["model"],
                "embeddings": [[1] + [0] * 1023],
                "prompt_eval_count": 7,
            }
        return {
            "model": body["model"],
            "done": True,
            "response": json.dumps(
                {
                    "intents": ["trace"],
                    "entities": [],
                    "proposed_strategy": ["inspect_dependencies"],
                    "scope": "file",
                    "obligations": ["trace"],
                }
            ),
            "prompt_eval_count": 19,
            "eval_count": 8,
        }

    collect(pack, revisions, send, output)
    records = json.loads(output.read_bytes())
    assert len(observed) == len(pack) == len(records)
    assert records["embed/h01"]["request_sha256"] == digest(pack["embed/h01"])
    report = evaluate(cases, pack, records)
    assert select(report, "embed", "h01")["answer_status"] == "complete"
    assert select(report, "embed", "h02")["scores"]["incorrect_deterministic"]
    for name in exp.Scenarios:
        row = select(report, "llm", "h01", name)
        assert (row["route"] == "investigation") == (name == "authorized_gap")
        assert row["scores"]["false_investigation"] == (name == "authorized_gap")
    assert report["classifier_usage"]["embed/h01"]["input_tokens"] == 7
    assert report["classifier_usage"]["llm/h01"]["output_tokens"] == 8
    assert report["classifier_usage"]["embed/p01"]["latency_ms"] >= 0
    assert report["similarity_diagnostics"]["holdout/0.9"]["accepted"] == 25
    assert not any("obligations" in req for req in pack.values())


def test_outage_invalid_schema_and_replay_binding(inputs):
    cases, pack = inputs
    records = {}
    for case in ("h15", "h01"):
        key = "llm/" + case
        records[key] = {
            "request_sha256": digest(pack[key]),
            "model_digest": "pinned",
            "latency_ms": 8,
            "error": "timeout",
        }
    records["llm/h01"].pop("error")
    records["llm/h01"]["response"] = {
        "model": "unit-test:latest",
        "done": True,
        "response": '{"route":"investigation"}',
    }
    report = evaluate(cases, pack, records)
    for case, route in (("h15", "inventory"), ("h01", "rag")):
        row = select(report, "llm", case)
        assert (
            row["diagnostic"] and row["status"] == "fallback" and row["route"] == route
        )
        assert row["retrieval_plan"]["classifier_output"] is None
    records["llm/h01"]["request_sha256"] = "wrong request"
    with pytest.raises(ValueError, match="capture request mismatch"):
        evaluate(cases, pack, records)


def test_compound_requires_explanation_of_every_definition(inputs):
    cases, pack = inputs
    # h05 does not ask for sources. Simulate a source-backed variant to exercise
    # the citation checks.
    cases = [
        replace(
            c,
            gold=c.gold.model_copy(
                update={"obligations": c.gold.obligations | {"source_evidence"}}
            ),
        )
        if c.id == "h05"
        else c
        for c in cases
    ]
    report = evaluate(cases, pack, {})
    row = select(report, "labels", "h05")
    cell = row["cell_sha256"]
    evidence = {
        "reviewer": "fixture",
        "answer": "only one",
        "supported": {
            "explanation_per_function": "reviewed against full stored source"
        },
    }
    with pytest.raises(ValueError, match="each definition"):
        evaluate(cases, pack, {}, {cell: evidence})
    rows = row["inventory_results"][MODULE]["inventory"]
    excerpts = {
        f"{MODULE}:{r['start']}:{r['name']}": f"Test explanation for {r['name']}."
        for r in rows
    }
    evidence.update(
        answer="\n".join(excerpts.values()), per_function_explanations=excerpts
    )
    partial = evaluate(cases, pack, {}, {cell: evidence})
    assert select(partial, "labels", "h05")["satisfied"] == ["explanation_per_function"]
    evidence["supported"]["definitions"] = "All witness rows appear in the answer."
    evidence["definition_rows"] = {MODULE: rows}
    evidence["answer"] += "\n" + "\n".join(
        f"{r['name']} ({r['kind']}, lines {r['start']}-{r['end']})" for r in rows
    )
    assert (
        select(evaluate(cases, pack, {}, {cell: evidence}), "labels", "h05")[
            "answer_status"
        ]
        == "partial"
    )
    evidence["supported"]["source_evidence"] = "Reviewer verified each citation."
    evidence["per_function_citations"] = {
        f"{MODULE}:{r['start']}:{r['name']}": {
            "start": r["start"],
            "end": r["start"],
            "quote": Corpus().text[MODULE].splitlines()[r["start"] - 1],
        }
        for r in rows
    }
    evidence["answer"] += "\n" + "\n".join(
        f"{MODULE}:{r['start']}-{r['start']}" for r in rows
    )
    result = evaluate(cases, pack, {}, {cell: evidence})
    assert select(result, "labels", "h05")["answer_status"] == "complete"
    with pytest.raises(ValueError, match="do not match"):
        evaluate(cases, pack, {}, {"unknown": evidence})


def test_executor_failure_with_correct_labels():
    corpus = Corpus()
    result = corpus.inventories(("codebase_ingest.py",), "inventory", budget=1)
    assert result[MODULE]["completion"] == "budget_limited"
    assert not corpus.verified(("codebase_ingest.py",), result)


def test_embedding_uses_nearest_prototype_without_copying_its_entity(inputs):
    cases, pack = inputs
    records = {}
    for key in [k for k in pack if k.startswith("embed/p")] + ["embed/h09"]:
        vector = [0.0] * 1024
        axis = 4 if key == "embed/h09" else int(key[-2:])
        vector[axis] = 11 if key == "embed/h09" else 2
        records[key] = {
            "request_sha256": digest(pack[key]),
            "latency_ms": 5,
            "model_digest": "test",
            "response": {"model": "mxbai-embed-large:latest", "embeddings": [vector]},
        }
    recognizers = Recognizers(cases, Captures(pack, records))
    case = next(c for c in cases if c.id == "h09")
    meaning, confidence = recognizers.predict("embed", case.id, case.question)
    assert meaning.intents == {"calls"} and confidence == pytest.approx(1)
    assert meaning.files == ("codebase_ingest.py", "api/ingest.py")
    records["embed/h09"]["response"]["embeddings"] = [[0] * 1024]
    report = evaluate(cases, pack, records)
    assert select(report, "embed", "h09")["status"] == "fallback"


def test_model_revision_preflight_blocks_inference(inputs, tmp_path):
    _, pack = inputs

    def send(endpoint, body):
        assert endpoint == "/api/tags" and body is None
        return {"models": []}

    with pytest.raises(ValueError, match="approved revisions"):
        collect(pack, {"unit-test:latest": "absent"}, send, tmp_path / "out.json")


def test_plan_and_obligations_are_scored_independently(inputs):
    cases, _ = inputs
    case = next(c for c in cases if c.id == "h22")
    assert case.gold.intents == {"inventory", "explain"}
    assert case.gold.obligations == {
        "definitions",
        "explanation_per_function",
        "source_evidence",
    }
    wrong = case.gold.model_copy(update={"proposed_strategy": ("ordinary_rag",)})
    row = exp.replay(case, wrong, exp.Scenarios["normal"], Corpus())
    assert row["scores"]["intent_correct"] and row["scores"]["obligations_correct"]
    assert not row["scores"]["strategy_correct"] and not row["inventory_results"]


def test_completion_reasons_and_plan_only_documents(inputs):
    cases, pack = inputs
    report = evaluate(cases, pack, {})
    assert select(report, "labels", "h01", "one_read")["obligation_status"] == {
        "definitions": "blocked_by_resource_limit"
    }
    assert select(report, "labels", "h05")["obligation_status"] == {
        "definitions": "satisfied",
        "explanation_per_function": "unsatisfied",
    }
    assert select(report, "labels", "h22")["obligation_status"] == {
        "definitions": "satisfied",
        "explanation_per_function": "unsatisfied",
        "source_evidence": "unsupported_by_available_evidence",
    }
    doc = select(report, "labels", "h20")
    assert doc["retrieval_plan"]["analysis"]["entities"] == [
        {"type": "document", "value": "policy-v1.pdf"},
        {"type": "document", "value": "policy-v2.pdf"},
    ]
    assert doc["scores"]["strategy_correct"] and doc["answer_status"] == "unmeasured"


def test_source_evidence_only_when_the_question_asks_for_it():
    asks = ("source", "cite", "quotation", "passages")
    for case in exp.load_cases():
        requested = any(word in case.question.lower() for word in asks)
        assert ("source_evidence" in case.gold.obligations) == requested, case.id


def test_capability_scoring_separates_dependencies_from_arbitrary_order(inputs):
    assert exp.order_valid(("source_navigation", "ast_inventory"))
    assert not exp.order_valid(("ast_inventory", "source_navigation"))
    assert not exp.order_valid(("ast_inventory",))
    assert not exp.order_valid(("grounded_synthesis", "find_callers"))
    # Navigation and caller lookup have no hard dependency in either direction.
    assert exp.order_valid(("find_callers", "source_navigation"))
    assert exp.order_valid(("source_navigation", "find_callers"))
    assert not exp.order_valid(("find_callers", "find_callers"))
    cases, _ = inputs
    assert all(exp.order_valid(c.gold.proposed_strategy) for c in cases)
    case = next(c for c in cases if c.id == "h18")
    swapped = case.gold.model_copy(
        update={"proposed_strategy": tuple(reversed(case.gold.proposed_strategy))}
    )
    scores = exp.replay(case, swapped, exp.Scenarios["normal"], Corpus())["scores"]
    assert not scores["strategy_correct"]
    assert scores["capabilities_correct"] and scores["order_valid"]
    inventory = next(c for c in cases if c.id == "h01")
    flipped = inventory.gold.model_copy(
        update={"proposed_strategy": ("ast_inventory", "source_navigation")}
    )
    row = exp.replay(inventory, flipped, exp.Scenarios["normal"], Corpus())
    assert row["scores"]["capabilities_correct"] and not row["scores"]["order_valid"]
    assert row["route"] == "rag"
