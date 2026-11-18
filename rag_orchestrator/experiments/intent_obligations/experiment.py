"""Offline intent/obligation contracts, policy replay and independent scoring."""

import csv
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.core import inventory_query

from .corpus import DATA, matches

Intent = Literal[
    "inventory",
    "explain",
    "calls",
    "imports",
    "trace",
    "unclear",
    "other",
    "callers",
    "compare",
    "summary",
    "impact",
]
Scope = Literal["all", "async", "file", "unspecified"]
Obligation = Literal[
    "definitions",
    "explanation",
    "callees",
    "imports",
    "trace",
    "clarification",
    "callers",
    "changes",
    "summary",
    "dependencies",
    "source_evidence",
    "explanation_per_function",
]


Strategy = Literal[
    "source_navigation",
    "ast_inventory",
    "grounded_synthesis",
    "find_callers",
    "find_callees",
    "inspect_imports",
    "filter_async",
    "clarify",
    "ordinary_rag",
    "retrieve_sections",
    "compare_versions",
    "inspect_dependencies",
]


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["python_file", "symbol", "document"]
    value: str = Field(min_length=1)


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intents: frozenset[Intent] = Field(min_length=1)
    scope: Scope
    obligations: frozenset[Obligation]
    entities: tuple[Entity, ...]
    proposed_strategy: tuple[Strategy, ...] = Field(min_length=1)

    @property
    def files(self):
        return tuple(e.value for e in self.entities if e.type == "python_file")

    def record(self):
        return self.model_dump(mode="json") | {
            "intents": sorted(self.intents),
            "obligations": sorted(self.obligations),
        }


def entities(question):
    found = []
    for match in re.finditer(
        r"(?P<file>(?:[\w.-]+/)*[\w.-]+\.(?:py|pdf))|`(?P<symbol>[A-Za-z_]\w*)`",
        question,
    ):
        value = match.group(0).strip("`")
        kind = (
            "symbol"
            if match.lastgroup == "symbol"
            else ("python_file" if value.endswith(".py") else "document")
        )
        found.append(Entity(type=kind, value=value))
    return tuple(dict.fromkeys(found))


def baseline(question):
    q = question.strip()
    match = inventory_query._INVENTORY.fullmatch(
        q
    ) or inventory_query._DOES_FILE_HAVE.fullmatch(q)
    if match:
        return Frame(
            intents=frozenset({"inventory"}),
            scope="all",
            obligations=frozenset({"definitions"}),
            entities=(Entity(type="python_file", value=match["path"]),),
            proposed_strategy=("source_navigation", "ast_inventory"),
        )
    return Frame(
        intents=frozenset({"other"}),
        scope="unspecified",
        obligations=frozenset(),
        entities=entities(q),
        proposed_strategy=("ordinary_rag",),
    )

# Hard prerequisites only. A tool here cannot run before the tools it needs.
# Any other order (for example caller lookup before or after source navigation)
# is arbitrary and is not penalized by the capability metrics.
Requires = {
    "ast_inventory": {"source_navigation"},
    "filter_async": {"ast_inventory"},
    "compare_versions": {"retrieve_sections"},
}


def order_valid(strategy):
    """True when each tool follows its prerequisites and synthesis is last."""
    for index, tool in enumerate(strategy):
        if not Requires.get(tool, set()) <= set(strategy[:index]):
            return False
        if tool == "grounded_synthesis" and index != len(strategy) - 1:
            return False
    return len(set(strategy)) == len(strategy)


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
                    "intents": row["intents"].split("|"),
                    "proposed_strategy": row["strategy"].split("|"),
                    "scope": row["scope"],
                    "obligations": row["obligations"].split("|"),
                    "entities": [
                        dict(zip(("type", "value"), e.split(":", 1)))
                        for e in row["entities"].split("|")
                        if e
                    ],
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
    read_budget: int = 8


Scenarios = {
    "normal": Scenario(),
    "one_read": Scenario(read_budget=1),
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
    if "unclear" in frame.intents:
        return "clarify"
    if "trace" in frame.intents and all(
        (
            scenario.authorized,
            scenario.material_gap,
            scenario.repair_available,
            scenario.budget_available,
        )
    ):
        return "investigation"
    if "inventory" not in frame.intents:
        return "rag"
    candidates = [matches(entity) for entity in frame.files]
    if not candidates or any(len(paths) > 1 for paths in candidates):
        return "clarify"
    if any(not paths for paths in candidates):
        return "missing"
    if len(frame.files) != len(frame.entities):
        return "rag"
    if (
        frame.scope == "all"
        and frame.obligations == {"definitions"}
        and set(frame.proposed_strategy) == {"source_navigation", "ast_inventory"}
        and order_valid(frame.proposed_strategy)
    ):
        return "inventory"
    if (
        frame.scope == "all"
        and {"definitions", "explanation_per_function"}
        <= frame.obligations
        <= {"definitions", "explanation_per_function", "source_evidence"}
        and set(frame.proposed_strategy)
        == {"source_navigation", "ast_inventory", "grounded_synthesis"}
        and order_valid(frame.proposed_strategy)
    ):
        return "inventory_then_rag"
    return "rag"


def expected_route(case, scenario):
    if scenario.explicit_rag:
        return "rag"
    if "trace" in case.gold.intents and scenario == Scenarios["authorized_gap"]:
        return "investigation"
    return case.expected_route


def replay(case, frame, scenario, corpus):
    actual = route(frame, scenario)
    expected = expected_route(case, scenario)
    inv = {"inventory", "inventory_then_rag"}
    results = (
        corpus.inventories(frame.files, case.question, budget=scenario.read_budget)
        if actual in inv
        else {}
    )
    satisfied = set()
    if (
        actual in inv
        and case.gold.scope == "all"
        and corpus.verified(case.gold.files, results)
    ):
        satisfied.add("definitions")
    response = None
    if actual == "clarify":
        candidates = [path for entity in frame.files for path in matches(entity)]
        response = (
            "Which file and which information do you want? " + " ".join(candidates)
        ).strip()
    elif actual == "missing":
        response = "No indexed match for " + ", ".join(
            entity for entity in frame.files if not matches(entity)
        )
    if response and actual == expected == "clarify" and "unclear" in case.gold.intents:
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
            "intent_correct": frame.intents == case.gold.intents,
            "entities_correct": frame.entities == case.gold.entities,
            "strategy_correct": frame.proposed_strategy == case.gold.proposed_strategy,
            "capabilities_correct": set(frame.proposed_strategy)
            == set(case.gold.proposed_strategy),
            "order_valid": order_valid(frame.proposed_strategy),
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
