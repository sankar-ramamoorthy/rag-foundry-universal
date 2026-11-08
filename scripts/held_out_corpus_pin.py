"""Reproducible procedure behind held-out-corpus-pin.json (issue #315).

Two steps, so measured, fetched and inferred evidence stay separate:

1. measure  -- read-only SQL against the ingestion database. The connection
   string comes from the environment variable named by --dsn-env (no default,
   no address or credential lives in this repository). Output: a measurements
   JSON file (not committed; keep it under DOCS/test_results/_raw/).
2. build    -- combines the measurements with two files fetched separately by
   plain read-only GETs (the generation API responses and the Ollama model
   list) and the frozen manifest, and writes the pin file.

The pin states, per fact, whether it was measured, fetched, inferred, reported
by the owner or is unverified. This script never edits the frozen manifest.
"""

from __future__ import annotations

# ruff: noqa: E501  (long evidence-source strings are prose, kept on one line)

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "DOCS/evaluations/code-evidence-held-out"
SCHEMA = "ingestion_service"

# repo -> (repo_id, ingestion_id). Identities come from the ingestion
# runbook flow; every one is re-checked against the database by `measure`.
GENERATIONS = {
    "pypa/hatch": (
        "15f342ab-984c-5727-952c-513b25320d92",
        "c142f7d1-f473-4731-a33e-b0e7431e7b8d",
    ),
    "pdfminer/pdfminer.six": (
        "2dd9827e-3682-5d60-bbb1-973c235b6294",
        "85085698-8251-4471-9bd2-4101f8af471e",
    ),
    "pallets/werkzeug": (
        "520a1d74-1784-561c-a37e-effc32c8fc95",
        "046c6d19-baff-4f1e-912c-2734e9797914",
    ),
}


def load_manifest() -> dict:
    return json.loads((HELD_OUT / "manifest.json").read_text(encoding="utf-8"))


def manifest_functions(manifest: dict) -> dict[str, list[str]]:
    funcs: dict[str, set[str]] = {}
    for case in manifest["cases"]:
        funcs.setdefault(case["repo"], set()).update(case["functions"])
    return {repo: sorted(v) for repo, v in funcs.items()}


def check_manifest_checksum() -> str:
    raw = (HELD_OUT / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    recorded = (HELD_OUT / "manifest.sha256").read_text().strip()
    if digest != recorded:
        raise SystemExit("manifest.json does not match manifest.sha256: refusing")
    return digest


def measure(dsn_env: str, out_path: Path, measured_on: str) -> None:
    import psycopg  # imported here: only `measure` needs a driver

    dsn = os.environ.get(dsn_env)
    if not dsn:
        raise SystemExit(f"environment variable {dsn_env} is not set")
    manifest = load_manifest()
    funcs = manifest_functions(manifest)
    result: dict = {"measured_on": measured_on, "repositories": {}}
    conn = psycopg.connect(dsn, connect_timeout=15)
    conn.read_only = True  # every statement below is a SELECT
    with conn.cursor() as cur:
        for repo, (repo_id, ingestion_id) in GENERATIONS.items():
            cur.execute(
                f"SELECT status, commit_sha, is_incremental, parent_generation_id,"
                f" chunking_config_version, embedding_config_version,"
                f" started_at, finished_at, structural_summary"
                f" FROM {SCHEMA}.ingestion_requests"
                f" WHERE ingestion_id = %s AND repo_id = %s",
                (ingestion_id, repo_id),
            )
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"no ingestion_requests row for {repo}")
            summary = row[8] or {}
            cur.execute(
                f"SELECT count(*) FROM {SCHEMA}.ingestion_requests WHERE repo_id = %s",
                (repo_id,),
            )
            requests_for_repo = cur.fetchone()[0]
            cur.execute(
                f"SELECT ingestion_id::text, count(*) FROM {SCHEMA}.document_nodes"
                f" WHERE repo_id = %s GROUP BY 1",
                (repo_id,),
            )
            node_gens = dict(cur.fetchall())
            cur.execute(
                f"SELECT ingestion_id::text, count(*) FROM {SCHEMA}.vector_chunks"
                f" WHERE repo_id = %s GROUP BY 1",
                (repo_id,),
            )
            chunk_gens = dict(cur.fetchall())
            hashes = {}
            for cid in funcs[repo]:
                cur.execute(
                    f"SELECT encode(sha256(convert_to(text, 'UTF8')), 'hex')"
                    f" FROM {SCHEMA}.document_nodes"
                    f" WHERE repo_id = %s AND ingestion_id = %s AND canonical_id = %s",
                    (repo_id, ingestion_id, cid),
                )
                found = cur.fetchone()
                hashes[cid] = found[0] if found else None
            result["repositories"][repo] = {
                "repo_id": repo_id,
                "ingestion_id": ingestion_id,
                "status": row[0],
                "commit_sha": row[1],
                "is_incremental": row[2],
                "parent_generation_id": str(row[3]) if row[3] else None,
                "chunking_config_version": row[4],
                "embedding_config_version": row[5],
                "started_at": row[6].isoformat(),
                "finished_at": row[7].isoformat(),
                "file_counts": summary.get("file_counts"),
                "ingestion_requests_for_repo": requests_for_repo,
                "document_nodes_by_ingestion": node_gens,
                "vector_chunks_by_ingestion": chunk_gens,
                "stored_text_sha256": hashes,
            }
    out_path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")


def _fact(value, status, source):
    return {"value": value, "status": status, "source": source}


def build(
    measurements: Path,
    generation_json: Path,
    ollama_json: Path,
    out_path: Path,
    fetched_on: str,
) -> None:
    manifest_sha = check_manifest_checksum()
    manifest = load_manifest()
    funcs = manifest_functions(manifest)
    m = json.loads(measurements.read_text(encoding="utf-8"))
    gens = json.loads(generation_json.read_text(encoding="utf-8"))
    tags = json.loads(ollama_json.read_text(encoding="utf-8"))
    on = m["measured_on"]
    sql = (
        f"Read-only SELECT on {on} via scripts/held_out_corpus_pin.py measure "
        "(ingestion_requests, document_nodes, vector_chunks)"
    )
    api = (
        f"GET /v1/repos/{{repo_id}}/generation on the production ingestion "
        f"service, fetched {fetched_on}"
    )
    repos = {}
    for repo, (repo_id, ingestion_id) in GENERATIONS.items():
        r = m["repositories"][repo]
        g = gens[repo]
        pin = manifest["pins"][repo]["commit"]
        expected_commit = (
            "585fb463d91ea384ae35e4d13ecc9294d0c911f2"
            if repo == "pallets/werkzeug"
            else pin
        )
        assert r["repo_id"] == repo_id and r["ingestion_id"] == ingestion_id
        assert r["commit_sha"] == expected_commit, repo
        assert g["ingestion_id"] == ingestion_id and g["commit_sha"] == expected_commit
        assert set(r["document_nodes_by_ingestion"]) == {ingestion_id}
        results = []
        for cid in funcs[repo]:
            stored = r["stored_text_sha256"][cid]
            expected = manifest["sources"][cid]["sha256"]
            results.append(
                {
                    "canonical_id": cid,
                    "manifest_sha256": expected,
                    "stored_text_sha256": stored,
                    "result": "MISSING"
                    if stored is None
                    else ("MATCH" if stored == expected else "MISMATCH"),
                }
            )
        entry = {
            "repo_id": repo_id,
            "ingestion_id": ingestion_id,
            "source": {"pinned_commit": pin, "recorded_commit": expected_commit},
            "generation": {
                "generation_status": _fact(g["generation_status"], "fetched", api),
                "ingestion_status": _fact(r["status"], "measured", sql),
                "ingested_commit_sha": _fact(r["commit_sha"], "measured", sql),
                "started_at": _fact(r["started_at"], "measured", sql),
                "finished_at": _fact(r["finished_at"], "measured", sql),
                "is_incremental": _fact(r["is_incremental"], "measured", sql),
                "parent_generation_id": _fact(
                    r["parent_generation_id"], "measured", sql
                ),
                "node_count": _fact(
                    r["document_nodes_by_ingestion"][ingestion_id], "measured", sql
                ),
                "chunk_count": _fact(
                    r["vector_chunks_by_ingestion"].get(ingestion_id), "measured", sql
                ),
                "file_counts": _fact(r["file_counts"], "measured", sql),
                "only_generation_for_repo": _fact(
                    r["ingestion_requests_for_repo"] == 1
                    and set(r["vector_chunks_by_ingestion"]) <= {ingestion_id},
                    "measured",
                    sql,
                ),
                "chunking_config_version": _fact(
                    r["chunking_config_version"], "measured", sql
                ),
                "embedding_config_version": _fact(
                    r["embedding_config_version"], "measured", sql
                ),
                "deployed_runtime_git_sha": _fact(
                    None,
                    "unverified",
                    "Not stored per ingestion; no evidence of the runtime at "
                    "ingestion time was found. The current deployment SHA is "
                    "deliberately not substituted.",
                ),
            },
            "function_text_sha256_vs_manifest": {
                "status": "measured",
                "method": (
                    "sha256 of document_nodes.text (UTF-8) selected with repo_id AND "
                    "ingestion_id of this generation, compared with the manifest "
                    "sources[].sha256; no normalization. " + sql
                ),
                "matched": sum(x["result"] == "MATCH" for x in results),
                "of": len(results),
                "functions": results,
            },
        }
        repos[repo] = entry
    repos["pypa/hatch"]["rebuild_note"] = (
        "Re-ingested with force_full_rebuild=true after #311 (PR #312) so decorator "
        "lines are stored; the previous generation 184d3d89-6e15-4699-8f6f-1eccd195748b "
        "mismatched 3 of 5 frozen hashes and was superseded."
    )
    repos["pypa/hatch"]["owner_reported"] = {
        "status": "reported",
        "source": "Owner session report 2026-11-08; not independently checked",
        "nodes_processed": "4861/4861",
        "chunks_persisted": 13795,
    }
    repos["pallets/werkzeug"]["snapshot"] = {
        "upstream_pinned_commit": manifest["pins"]["pallets/werkzeug"]["commit"],
        "snapshot_repository": (
            "https://github.com/sankar-ramamoorthy/werkzeug-e1-heldout-pin"
        ),
        "snapshot_main_commit": _fact(
            "585fb463d91ea384ae35e4d13ecc9294d0c911f2",
            "fetched",
            "git ls-remote refs/heads/main, 2026-11-08",
        ),
        "source_tree": _fact(
            "93f10217a04d9b5b3367d57227d3fec46c7990b8",
            "fetched",
            "shallow clone HEAD^{tree}, 2026-11-08; equals the pinned upstream tree "
            "per clarification-snapshot-tree-equivalence.md (#305)",
        ),
    }
    contract = json.loads(
        (ROOT / "DOCS/evaluations/code-evidence-e1/execution-contract.json").read_text(
            encoding="utf-8"
        )
    )
    contract_model = next(x for x in contract["models"] if x["name"].startswith("mxbai"))
    host_model = next(x for x in tags["models"] if x["name"] == contract_model["name"])
    latest_finish = min(v["finished_at"] for v in m["repositories"].values())
    predates = host_model["modified_at"][:10] < latest_finish[:10]
    pin_doc = {
        "schema_version": "2",
        "purpose": (
            "Held-out corpus pin for E1 (issue #315, goal #294); field names follow "
            "code-evidence-e1/dev-corpus-pin.json. The frozen manifest is not edited."
        ),
        "recorded_at": fetched_on,
        "deviations_from_dev_corpus_pin": [
            "One entry per repository under 'repositories' (the dev pin holds one corpus).",
            "Each fact carries value/status/source; status is measured, fetched, "
            "inferred, reported or unverified (the dev pin uses plain fields and notes).",
        ],
        "status_vocabulary": {
            "measured": "read directly from the production database by the cited read-only query",
            "fetched": "returned by a read-only GET or git command on the cited date",
            "inferred": "concluded from other evidence; not an observation of the thing itself",
            "reported": "stated by the repository owner; not independently checked",
            "unverified": "not established; no value is recorded",
        },
        "manifest_sha256": manifest_sha,
        "repositories": repos,
        "embedder": {
            "contract_model": contract_model["name"],
            "contract_digest": contract_model["digest"],
            "current_host_digest": _fact(
                host_model["digest"],
                "fetched",
                f"GET /api/tags on the ingestion host's Ollama, {fetched_on}",
            ),
            "current_host_modified_at": _fact(
                host_model["modified_at"], "fetched", "same response"
            ),
            "current_host_digest_equals_contract": host_model["digest"]
            == contract_model["digest"],
            "digest_used_for_each_ingestion": _fact(
                None,
                "unverified",
                "The digest is not stored per ingestion. The current host model "
                "matches the contract and its modified_at predates every "
                "ingestion, which is consistent with, but does not prove, that "
                "this model produced the vectors.",
            ),
            "inference": _fact(
                "consistent-with-contract" if predates else "not-supported",
                "inferred",
                "current host digest equals the contract digest and modified_at "
                "predates the earliest ingestion finish; current host state, not "
                "historical ingestion-time evidence",
            ),
        },
        "preregistration_merged": _fact(
            "PR #304 (issue #303), commit 2058cf0",
            "fetched",
            "git log of preregistration-named-symbol-first.md; gh pr view 304",
        ),
        "limitations": [
            "Production data was read by scripts/held_out_corpus_pin.py measure on "
            f"{on}; the tests in tests/test_held_out_corpus_pin.py cross-check the "
            "recorded values against the frozen manifest and do NOT re-read production.",
            "Deployed runtime SHA at ingestion time is not recorded anywhere found.",
            "Embedder digest at ingestion time is inferred from current host state only.",
            "pdfminer.six and werkzeug ran before PR #312; their frozen functions "
            "have no decorators and match.",
            "Held-out control harness and control path are not yet agreed; E1 has not run.",
        ],
    }
    out_path.write_text(json.dumps(pin_doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out_path}")


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("measure")
    a.add_argument("--dsn-env", required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--date", required=True)
    b = sub.add_parser("build")
    b.add_argument("--measurements", type=Path, required=True)
    b.add_argument("--generation-json", type=Path, required=True)
    b.add_argument("--ollama-tags-json", type=Path, required=True)
    b.add_argument("--out", type=Path, default=HELD_OUT / "held-out-corpus-pin.json")
    b.add_argument("--date", required=True)
    args = p.parse_args(argv)
    if args.cmd == "measure":
        measure(args.dsn_env, args.out, args.date)
    else:
        build(
            args.measurements,
            args.generation_json,
            args.ollama_tags_json,
            args.out,
            args.date,
        )


if __name__ == "__main__":
    main(sys.argv[1:])
