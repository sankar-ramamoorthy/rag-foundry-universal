"""Run from rag_orchestrator with the repository root on PYTHONPATH."""

import argparse
import json
from collections import Counter
from pathlib import Path
from time import perf_counter

from .corpus import Corpus, matches
from .experiment import Scenarios, baseline, load_cases, replay
from .recognition import Captures, Recognizers, digest, request_pack


def summarize(rows):
    totals = {}
    calibration = {}
    for row in rows:
        group = "/".join((row["arm"], row["split"], row["scenario"]))
        counts = totals.setdefault(group, Counter())
        counts["scheduled"] += 1
        if row["status"] == "not_recorded":
            counts["not_recorded"] += 1
            continue
        counts["evaluated"] += 1
        counts["inventory_expected"] += int(
            row["expected_route"] in {"inventory", "inventory_then_rag"}
        )
        counts["deterministic_selected"] += int(
            row["route"] in {"inventory", "inventory_then_rag"}
        )
        counts["outages"] += int(row["status"] == "fallback")
        counts.update({key: int(value) for key, value in row["scores"].items()})
        counts["answer_" + row["answer_status"]] += 1
        if (
            row["arm"] == "embed"
            and row["scenario"] == "normal"
            and row["status"] == "ok"
        ):
            # Fixed diagnostic operating points. No threshold controls routing.
            for threshold in (0.0, 0.5, 0.7, 0.9):
                key = f"{row['split']}/{threshold:.1f}"
                bucket = calibration.setdefault(key, Counter())
                bucket["evaluated"] += 1
                if row["similarity"] >= threshold:
                    bucket["accepted"] += 1
                    bucket["intent_correct"] += int(row["scores"]["intent_correct"])
                    bucket["obligations_correct"] += int(
                        row["scores"]["obligations_correct"]
                    )
    return totals, calibration


def recognize(case, arm, models):
    if arm == "labels":
        return case.gold, "ok", None, None
    if arm == "regex":
        return baseline(case.question), "ok", None, None
    if f"{arm}/{case.id}" not in models.captures.records:
        return None, "not_recorded", None, None
    if arm == "embed" and models.missing_prototypes:
        return None, "not_recorded", "missing prototype capture", None
    try:
        frame, similarity = models.predict(arm, case.id, case.question)
        return frame, "ok", None, similarity
    except (ValueError, KeyError, TypeError) as exc:
        return baseline(case.question), "fallback", str(exc), None


def evaluate(cases, pack, records, judgments=None):
    corpus = Corpus()
    captures = Captures(pack, records)
    models = Recognizers(cases, captures)
    rows = []
    controls = {}
    judgments = dict(judgments or {})
    for case in cases:
        if case.split == "prototype":
            continue
        for arm in ("labels", "regex", "embed", "llm"):
            key = f"{arm}/{case.id}"
            start = perf_counter()
            frame, status, diagnostic, similarity = recognize(case, arm, models)
            local_ms = (perf_counter() - start) * 1000
            capture_hash = digest(records[key]) if key in records else None
            for name, scenario in Scenarios.items():
                row = {
                    "id": case.id,
                    "question": case.question,
                    "family": case.family,
                    "split": case.split,
                    "arm": arm,
                    "scenario": name,
                    "status": status,
                    "usage_key": key if key in records else None,
                    "local_recognition_ms": local_ms,
                    "diagnostic": diagnostic,
                    "similarity": similarity,
                }
                if frame is not None:
                    row.update(replay(case, frame, scenario, corpus))
                    row["retrieval_plan"] = {
                        "analysis": frame.record(),
                        "classifier_output": None if diagnostic else frame.record(),
                        "route": row["route"],
                        "diagnostic": diagnostic,
                    }
                    # Bind the independent answer judgment to this executed cell.
                    cell = digest(
                        [
                            case.question,
                            name,
                            scenario.__dict__,
                            arm,
                            capture_hash,
                            frame.record(),
                            case.gold.record(),
                            row["route"],
                            row["inventory_results"],
                            corpus.witness["sha256"],
                        ]
                    )
                    row["cell_sha256"] = cell
                    if arm == "labels":
                        controls[case.id, name] = set(row["satisfied"])
                    if cell in judgments:
                        apply_judgment(row, case, judgments.pop(cell), corpus)
                    feasible = controls[case.id, name]
                    row["verifiable_obligations"] = sorted(feasible)
                    row["scores"]["verifiable_cases"] = bool(feasible)
                    row["scores"]["delivered_all_verifiable"] = bool(
                        feasible
                    ) and feasible <= set(row["satisfied"])
                    row["scores"]["understood_and_delivered_verifiable"] = row[
                        "scores"
                    ]["delivered_all_verifiable"] and all(
                        row["scores"][field + "_correct"]
                        for field in (
                            "intent",
                            "entities",
                            "scope",
                            "obligations",
                            "strategy",
                        )
                    )
                    scores = row["scores"]
                    scores["understood_capabilities_and_delivered_verifiable"] = (
                        scores["delivered_all_verifiable"]
                        and scores["capabilities_correct"]
                        and scores["order_valid"]
                        and all(
                            scores[field + "_correct"]
                            for field in ("intent", "entities", "scope", "obligations")
                        )
                    )
                    row["obligation_status"] = obligation_status(row, case)
                rows.append(row)
    if judgments:
        raise ValueError("answer judgments do not match executed cells")
    totals, calibration = summarize(rows)
    return {
        "cases_sha256": digest(
            [case.__dict__ | {"gold": case.gold.record()} for case in cases]
        ),
        "request_pack_sha256": digest(pack),
        "source_sha256": corpus.witness["sha256"],
        "classifier_usage": {key: captures.usage(key) for key in pack},
        "counts": totals,
        "similarity_diagnostics": calibration,
        "rows": rows,
    }


def obligation_status(row, case):
    status = {}
    limited = any(
        r["completion"] == "budget_limited" for r in row["inventory_results"].values()
    )
    for obligation in sorted(case.gold.obligations):
        if obligation in row["satisfied"]:
            state = "satisfied"
        elif limited and obligation in {
            "definitions",
            "explanation_per_function",
            "source_evidence",
        }:
            state = "blocked_by_resource_limit"
        elif obligation == "source_evidence" or row["route"] == "missing":
            state = "unsupported_by_available_evidence"
        else:
            state = "unsatisfied"
        status[obligation] = state
    return status


def check_citations(corpus, judgment, witnesses, required):
    citations = judgment.get("per_function_citations", {})
    if set(citations) != required:
        raise ValueError("source evidence requires a citation for each definition")
    for path, rows in witnesses.items():
        lines = corpus.text[path].splitlines()
        for r in rows:
            citation = citations[f"{path}:{r['start']}:{r['name']}"]
            first, last = citation["start"], citation["end"]
            quote = citation["quote"]
            if not (
                r["start"] <= first <= last <= r["end"]
                and quote.strip()
                and quote == "\n".join(lines[first - 1 : last])
                and f"{path}:{first}-{last}" in judgment["answer"]
            ):
                raise ValueError("citation does not match delivered answer and source")


def check_inventory_judgment(case, corpus, judgment, obligation):
    witnesses = {}
    for entity in case.gold.files:
        paths = matches(entity)
        if len(paths) != 1:
            raise ValueError("inventory judgment has an unresolved entity")
        path = paths[0]
        witnesses[path] = [
            r
            for r in corpus.expected(path)
            if case.gold.scope == "all" or r["kind"] == case.gold.scope
        ]
    if not witnesses:
        raise ValueError("inventory judgment has no target")
    if obligation == "definitions":
        if judgment.get("definition_rows") != witnesses:
            raise ValueError("adjudicated definitions differ from the source witness")
        return
    required = {
        f"{path}:{r['start']}:{r['name']}"
        for path, rows in witnesses.items()
        for r in rows
    }
    if obligation == "source_evidence":
        check_citations(corpus, judgment, witnesses, required)
        return
    explanations = judgment.get("per_function_explanations", {})
    if set(explanations) != required or any(
        not quote.strip() or quote not in judgment["answer"]
        for quote in explanations.values()
    ):
        raise ValueError(
            "grounded explanations require a reviewed excerpt for each definition"
        )


def apply_judgment(row, case, judgment, corpus):
    """Accept separately reviewed answer evidence for synthesis routes only."""
    if row["route"] not in {"rag", "inventory_then_rag", "investigation"}:
        raise ValueError("unexpected synthesis judgment")
    if not judgment["reviewer"] or not judgment["answer"].strip():
        raise ValueError("a reviewer and captured answer are required")
    # Judge the delivered synthesis. It can omit definitions the executor found.
    satisfied = set()
    for requirement, evidence in judgment["supported"].items():
        if (
            requirement not in case.gold.obligations
            or not isinstance(evidence, str)
            or not evidence.strip()
        ):
            raise ValueError("unsupported judgment entry")
        if "inventory" in case.gold.intents and requirement in {
            "definitions",
            "explanation_per_function",
            "source_evidence",
        }:
            check_inventory_judgment(case, corpus, judgment, requirement)
        satisfied.add(requirement)
    row["answer_judgment"] = judgment
    row["satisfied"] = sorted(satisfied)
    complete = case.gold.obligations <= satisfied
    row["answer_status"] = (
        "complete" if complete else ("partial" if satisfied else "unresolved")
    )
    row["scores"]["demonstrated_complete"] = complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--request-pack", action="store_true", help="export label-free Ollama requests"
    )
    parser.add_argument(
        "--llm-model", help="exact local Ollama tag used for the LLM arm"
    )
    parser.add_argument("--embed-model", default="mxbai-embed-large:latest")
    parser.add_argument(
        "--captures",
        type=Path,
        help="JSON classifier response records keyed by request ID",
    )
    parser.add_argument(
        "--judgments",
        type=Path,
        help="independent answer adjudications keyed by cell SHA",
    )
    args = parser.parse_args()
    if (args.request_pack or args.captures) and not args.llm_model:
        parser.error(
            "--llm-model is required when exporting requests or replaying captures"
        )
    cases = load_cases()
    pack = request_pack(cases, args.embed_model, args.llm_model or "unselected")
    result = (
        pack
        if args.request_pack
        else evaluate(
            cases,
            pack,
            json.loads(args.captures.read_bytes()) if args.captures else {},
            json.loads(args.judgments.read_bytes()) if args.judgments else {},
        )
    )
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )


if __name__ == "__main__":
    main()
