"""Collect a separately approved Ollama classifier run on the local host."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from urllib.request import ProxyHandler, build_opener, Request, HTTPRedirectHandler

from .experiment import load_cases
from .recognition import digest, request_pack


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def collect(pack, revisions, send, output):
    if output.exists():
        raise ValueError("choose a new output file for this run")
    records = {}

    def verify_models():
        tags = {m["name"]: m["digest"] for m in send("/api/tags", None)["models"]}
        if any(tags.get(model) != revision for model, revision in revisions.items()):
            raise ValueError("local model tags differ from the approved revisions")

    verify_models()
    # Retain the attempts if collection or the closing revision check fails.
    partial = output.with_suffix(output.suffix + ".partial.jsonl")
    with partial.open("x", encoding="utf8") as journal:
        for key, req in pack.items():
            start = perf_counter()
            try:
                payload = {"response": send(req["endpoint"], req["body"])}
            except (TimeoutError, ValueError, OSError) as exc:
                payload = {"error": str(exc)}
            records[key] = {
                "request_sha256": digest(req),
                "model_digest": revisions[req["body"]["model"]],
                "latency_ms": (perf_counter() - start) * 1000,
                **payload,
            }
            journal.write(json.dumps({key: records[key]}, allow_nan=False) + "\n")
            journal.flush()
    verify_models()
    with output.open("x", encoding="utf8") as stream:
        json.dump(records, stream, ensure_ascii=False, allow_nan=False)
    partial.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--approved-pack-sha256", required=True)
    parser.add_argument("--llm-model", required=True)
    parser.add_argument("--llm-digest", required=True)
    parser.add_argument("--embed-model", default="mxbai-embed-large:latest")
    parser.add_argument("--embed-digest", required=True)
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pack = json.loads(args.pack.read_bytes())
    ordered_pack = request_pack(load_cases(), args.embed_model, args.llm_model)
    if pack != ordered_pack:
        parser.error("request pack differs from this checkout")
    if digest(pack) != args.approved_pack_sha256:
        parser.error("request pack differs from the approved digest")
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def send(endpoint, body):
        request = Request(
            f"http://127.0.0.1:{args.port}{endpoint}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request, timeout=60) as response:
            return json.load(response)

    collect(
        ordered_pack,
        {args.llm_model: args.llm_digest, args.embed_model: args.embed_digest},
        send,
        args.output,
    )


if __name__ == "__main__":
    main()
