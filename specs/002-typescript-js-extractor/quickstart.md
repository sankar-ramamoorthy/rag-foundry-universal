# Quickstart: Validating WP-L2 (TypeScript/JavaScript Extractor)

## Prerequisites

- Repo checked out on `feat/wp-l2-typescript-js-extractor-issue-83`.
- `ingestion_service`'s own `.venv` (root `.venv` also works for tests per
  `[[memory:disk-and-test-environment]]`; do not run a full `uv sync` inside
  `ingestion_service` — install the two new grammar packages via
  `uv lock --upgrade-package tree-sitter-typescript --upgrade-package tree-sitter-javascript`
  then `uv sync` from `ingestion_service/`, or use whatever the project's
  established fast path is).

## Run the new unit tests

```sh
cd ingestion_service
uv run pytest tests/codebase/test_typescript_extractor.py -v
uv run pytest tests/codebase/test_ts_repo_graph_golden.py -v
```

Expected: all new tests pass, and existing tests remain green:

```sh
uv run pytest -m unit
```

## Manually exercise the extractor against the fixture repo

```sh
cd ingestion_service
uv run python -c "
from pathlib import Path
from uuid import uuid4
from src.core.codebase.repo_graph_builder import RepoGraphBuilder

builder = RepoGraphBuilder(Path('tests/fixtures/ts_repo'), ingestion_id=uuid4())
graph = builder.build()

for e in sorted(graph.all_entities(), key=lambda x: x['canonical_id']):
    print(e['artifact_type'], e['canonical_id'])
print('---relationships---')
for r in sorted(graph.relationships, key=lambda x: (x['relation_type'], x['from_canonical_id'])):
    print(r['relation_type'], r['from_canonical_id'], '->', r['to_canonical_id'])
"
```

Expected outcome (spot-check, full detail in the golden test):
- MODULE nodes for every file in `tests/fixtures/ts_repo/src/`.
- One INTERFACE node (`Movable`) and one CLASS node (`Animal`) plus `Dog`.
- `Dog` has two INHERITS edges (`Animal` and `Movable`).
- `a.ts`-equivalent (`index.ts`) has an IMPORTS edge into `util.ts`'s module
  node and into `sub/index.ts` (directory-import resolution).
- `external.ts` has an IMPORTS edge to an `EXTERNAL_MODULE:react` node.
- Zero unhandled exceptions during `builder.build()`.

## Determinism check

Run the same script twice (or the dedicated determinism test) and diff the
sorted entity/relationship dumps — they must be byte-identical (ADR-036,
spec SC-005).

## Mixed-language regression check

```sh
cd ingestion_service
uv run pytest tests/codebase/test_repo_graph_builder.py -v
```

This test walks `ingestion_service/src` itself (a Python-only tree) — it
must continue to pass unchanged, proving the new per-suffix module
convention dispatcher doesn't alter Python-only resolution (Required
Non-Regressions in plan.md).
