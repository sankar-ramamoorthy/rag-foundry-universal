"""Offline intent/obligation contracts, policy replay and independent scoring."""

import csv
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.core import inventory_query

from .corpus import DATA, matches

Intent = Literal[
    "inventory", "explain", "calls", "imports", "trace", "unclear", "other"
]
Scope = Literal["all", "async", "file", "unspecified"]
Obligation = Literal[
    "definitions", "explanation", "callees", "imports", "trace", "clarification"
]


class Meaning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intent: Intent
    scope: Scope
    obligations: frozenset[Obligation] = Field(max_length=6)


class Frame(Meaning):
    entities: tuple[str, ...]


def entities(question):
    return tuple(
        dict.fromkeys(
            re.findall(r"(?<![\w./-])(?:[\w.-]+/)*[\w.-]+\.py(?![\w/-])", question)
        )
    )


def baseline(question):
    q = question.strip()
    match = inventory_query._INVENTORY.fullmatch(
        q
    ) or inventory_query._DOES_FILE_HAVE.fullmatch(q)
    if match:
        return Frame(
            intent="inventory",
            scope="all",
            obligations=frozenset({"definitions"}),
            entities=(match["path"],),
        )
    return Frame(
        intent="other",
        scope="unspecified",
        obligations=frozenset(),
        entities=entities(q),
    )


@dataclass(frozen=True)
class Case:
    id: str
    split: str
    family: str
    question: str
    gold: Frame
    expected_route: str


def load_cases():
    cases = []
    families = {}
    with (DATA / "cases.csv").open(encoding="utf8", newline="") as stream:
        for row in csv.DictReader(stream):
            if families.setdefault(row["family"], row["split"]) != row["split"]:
                raise ValueError("phrasing family appears in two splits")
            gold = Frame.model_validate(
                {
                    "intent": row["intent"],
                    "scope": row["scope"],
                    "obligations": row["obligations"].split("|"),
                    "entities": row["entities"].split("|") if row["entities"] else [],
                }
            )
            cases.append(
                Case(
                    row["id"],
                    row["split"],
                    row["family"],
                    row["question"],
                    gold,
                    row["route"],
                )
            )
    if len({c.id for c in cases}) != len(cases) or len(
        {c.question for c in cases}
    ) != len(cases):
        raise ValueError("duplicate case ID or question")
    return cases


@dataclass(frozen=True)
class Scenario:
    explicit_rag: bool = False
    authorized: bool = False
    material_gap: bool = False
    repair_available: bool = False
    budget_available: bool = True


Scenarios = {
    "normal": Scenario(),
    "authorized_gap": Scenario(False, True, True, True),
    "denied_gap": Scenario(False, False, True, True),
    "sufficient_evidence": Scenario(False, True, False, True),
    "no_repair": Scenario(False, True, True, False),
    "no_budget": Scenario(False, True, True, True, False),
    "explicit_rag": Scenario(True, True, True, True),
}


def route(frame, scenario):
    if scenario.explicit_rag:
        return "rag"
    if frame.intent == "unclear":
        return "clarify"
    if frame.intent == "trace" and all(
        (
            scenario.authorized,
            scenario.material_gap,
            scenario.repair_available,
            scenario.budget_available,
        )
    ):
        return "investigation"
    if frame.intent != "inventory":
        return "rag"
    candidates = [matches(entity) for entity in frame.entities]
    if not candidates or any(len(paths) > 1 for paths in candidates):
        return "clarify"
    if any(not paths for paths in candidates):
        return "missing"
    if frame.scope == "all" and frame.obligations == {"definitions"}:
        return "inventory"
    if frame.scope == "all" and frame.obligations == {"definitions", "explanation"}:
        return "inventory_then_rag"
    return "rag"


def expected_route(case, scenario):
    if scenario.explicit_rag:
        return "rag"
    if case.gold.intent == "trace" and scenario == Scenarios["authorized_gap"]:
        return "investigation"
    return case.expected_route


def replay(case, frame, scenario, corpus):
    actual = route(frame, scenario)
    expected = expected_route(case, scenario)
    inv = {"inventory", "inventory_then_rag"}
    results = corpus.inventories(frame.entities, case.question) if actual in inv else {}
    satisfied = set()
    if (
        actual in inv
        and case.gold.scope == "all"
        and corpus.verified(case.gold.entities, results)
    ):
        satisfied.add("definitions")
    response = None
    if actual == "clarify":
        candidates = [path for entity in frame.entities for path in matches(entity)]
        response = (
            "Which file and which information do you want? " + " ".join(candidates)
        ).strip()
    elif actual == "missing":
        response = "No indexed match for " + ", ".join(
            entity for entity in frame.entities if not matches(entity)
        )
    if response and actual == expected == "clarify" and case.gold.intent == "unclear":
        satisfied.add("clarification")
    # A route to synthesis is not evidence that the model produced a grounded answer.
    complete = case.gold.obligations <= satisfied
    return {
        "route": actual,
        "expected_route": expected,
        "response": response,
        "inventory_results": results,
        "satisfied": sorted(satisfied),
        "answer_status": "complete"
        if complete
        else (
            "partial"
            if satisfied
            else "unmeasured"
            if actual in {"rag", "investigation"}
            else "unresolved"
        ),
        "scores": {
            "intent_correct": frame.intent == case.gold.intent,
            "entities_correct": frame.entities == case.gold.entities,
            "scope_correct": frame.scope == case.gold.scope,
            "obligations_correct": frame.obligations == case.gold.obligations,
            "route_correct": actual == expected,
            "demonstrated_complete": complete,
            "incorrect_deterministic": actual in inv
            and (actual != expected or frame.entities != case.gold.entities),
            "missed_inventory": expected in inv and actual not in inv,
            "needless_clarification": actual == "clarify" and expected != "clarify",
            "needless_rag": actual == "rag" and expected != "rag",
            "false_investigation": actual == "investigation" and expected != actual,
        },
    }
