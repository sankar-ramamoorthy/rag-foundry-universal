"""Build Ollama classifier requests and replay independently recorded responses."""

import hashlib
import json
import math

from .experiment import Frame, entities


def digest(value):
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def request_pack(cases, embed_model, llm_model):
    if embed_model.split(":")[0] != "mxbai-embed-large":
        raise ValueError("expected the mxbai-embed-large embedding arm")
    prompt = (
        "Classify the question by intent, scope and every required answer obligation. "
        "Use inventory/all for all definitions, inventory/async for async functions, "
        "file for other file-specific questions and unspecified for unclear scope. "
        "For list and explain use definitions, explanation_per_function "
        "and source_evidence. "
        "Return all intents, literal typed entities and ordered proposed tools."
    )
    requests = {}
    for c in cases:
        requests["embed/" + c.id] = {
            "endpoint": "/api/embed",
            "body": {"model": embed_model, "input": c.question, "truncate": False},
        }
        if c.split != "prototype":
            requests["llm/" + c.id] = {
                "endpoint": "/api/generate",
                "body": {
                    "model": llm_model,
                    "system": prompt,
                    "prompt": c.question,
                    "format": Frame.model_json_schema(),
                    "stream": False,
                    "options": {"temperature": 0, "seed": 398, "num_predict": 256},
                },
            }
    return requests


class Unavailable(ValueError):
    """The requested classifier could not produce a valid prediction."""


def vector(response):
    embeddings = response["embeddings"]
    if len(embeddings) != 1 or len(embeddings[0]) != 1024:
        raise ValueError("expected one 1024-dimensional embedding")
    values = embeddings[0]
    if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
        raise ValueError("invalid embedding values")
    norm = math.hypot(*values)
    if not norm or not math.isfinite(norm):
        raise ValueError("invalid embedding norm")
    return tuple(v / norm for v in values)


class Captures:
    def __init__(self, pack, records):
        self.records = {}
        self.pack = pack
        revisions = {}
        for key, record in records.items():
            if key not in pack or record["request_sha256"] != digest(pack[key]):
                raise ValueError(f"capture request mismatch for {key}")
            arm = key.split("/")[0]
            revision = record["model_digest"]
            if not revision or revisions.setdefault(arm, revision) != revision:
                raise ValueError(f"missing or inconsistent model revision for {arm}")
            latency = record["latency_ms"]
            if (
                type(latency) not in (int, float)
                or not math.isfinite(latency)
                or latency < 0
            ):
                raise ValueError(f"invalid measured latency for {key}")
            self.records[key] = record

    def response(self, key):
        rec = self.records.get(key)
        if rec is None:
            raise Unavailable(f"missing capture {key}")
        if "error" in rec:
            raise Unavailable(str(rec["error"]))
        response = rec["response"]
        if (
            not isinstance(response, dict)
            or response.get("model") != self.pack[key]["body"]["model"]
        ):
            raise Unavailable(f"wrong response model for {key}")
        return response

    def usage(self, key):
        rec = self.records.get(key)
        if rec is None:
            return None
        response = rec.get("response")
        if not isinstance(response, dict):
            response = {}
        return {
            "model_digest": rec["model_digest"],
            "latency_ms": rec["latency_ms"],
            "input_tokens": response.get("prompt_eval_count"),
            "output_tokens": response.get("eval_count"),
            "cost_usd": rec.get("cost_usd"),
        }


class Recognizers:
    def __init__(self, cases, captures):
        self.captures = captures
        self.prototypes = []
        self.missing_prototypes = any(
            "embed/" + case.id not in captures.records
            for case in cases
            if case.split == "prototype"
        )
        self.setup_error = None
        try:
            for case in cases:
                if case.split == "prototype":
                    self.prototypes.append(
                        (case, vector(captures.response("embed/" + case.id)))
                    )
        except (ValueError, KeyError, TypeError) as exc:
            self.setup_error = str(exc)

    def predict(self, arm, case_id, question):
        response = self.captures.response(f"{arm}/{case_id}")
        similarity = None
        if arm == "llm":
            if (
                response.get("done") is not True
                or response.get("done_reason") == "length"
            ):
                raise Unavailable("incomplete LLM response")
            return Frame.model_validate_json(response["response"]), None
        else:
            if self.setup_error:
                raise Unavailable(self.setup_error)
            v = vector(response)
            scores = [
                (sum(a * b for a, b in zip(v, p, strict=True)), case)
                for case, p in self.prototypes
            ]
            similarity, nearest = max(scores, key=lambda pair: pair[0])
            meaning = nearest.gold
        return Frame(
            **meaning.model_dump(exclude={"entities"}), entities=entities(question)
        ), similarity
