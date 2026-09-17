# Validation runbook: bounded ingestion memory

Tracking issue: #160
Status: Procedure; acceptance runs have not yet passed

## Environment

uv sync --frozen at root. From ingestion_service run
../.venv/bin/python -m pytest -m unit -q on Linux, or
../.venv/Scripts/python.exe -m pytest -m unit -q on Windows.
Use isolated PostgreSQL+pgvector with applied migrations for paging/progress
tests. Explicitly add new tests to CI's integration job.

## Pin inputs before running

Record runtime/source SHA, model/dimension, settings, CPU/RAM/GPU and cgroup
ceiling. Fixture A is arc53/DocsGPT at the incident commit if recoverable.
A moving default-branch clone is not the same fixture. Use a prepared checkout
until ref pinning ships. Unknown incident SHA/ceiling must remain unknown;
declare any new baseline explicitly instead of claiming exact reproduction.

## Fixtures and assertions

B1: N and 4N small artifacts, same settings, fresh processes.
B2: few large artifacts, 128000-character node, multiple-buffer ordinals.
B3: Unicode, NULL/whitespace, zero artifacts and oversize rejection.
B4: provider/write failures and kill after an acknowledged HTTP batch.

Compare buffers 1/7/128 using normalized text/metadata/ordinals/canonical edges
and deterministic vectors. Expected vectors = SUM(actual emitted chunks).
Node-count equality is never sufficient.

## Memory harness

Implemented probe: `scripts/benchmark_bounded_ingestion.py`. Requires Linux,
a migrated isolated database named `*_test`, and a loopback vector-service
process configured for that same database. It refuses non-test databases and
non-loopback vector URLs. It creates a fresh generated Python repository and
unique ingestion/repo IDs, runs the actual graph builder, paged embedding worker
and HTTP persistence, and cleans up only those fixture IDs/files. Embeddings
are deterministic 1024-D Python float vectors, not Ollama output.

From repository root (replace port with the isolated test service's port):

```bash
.venv/bin/python scripts/benchmark_bounded_ingestion.py --files 512 --vector-url http://127.0.0.1:18002
.venv/bin/python scripts/benchmark_bounded_ingestion.py --files 2048 --vector-url http://127.0.0.1:18002
.venv/bin/python scripts/benchmark_bounded_ingestion.py --files 4 --payload-chars 128000 --vector-url http://127.0.0.1:18002
```

Each invocation must be a fresh process. Capture JSONL stdout separately.
`test_fresh_process_memory_scaling` starts the isolated vector service and runs
all three cases against CI's test database, enforcing the preregistered SC-002
threshold and observed limits. CI uploads `bounded-memory-evidence` containing
N/4N/large raw JSONL and comparison.json (14-day retention). Archive accepted
evidence in the KB before expiration. The first run defaults to phase
`calibration`; set MEMORY_MEASUREMENT_PHASE=acceptance only after inspecting
calibration, without silently changing the criterion.

These runs exercise real graph/SQL/HTTP paths, but do not measure Ollama/GPU
memory or replace the pinned DocsGPT gate. Cgroup mount-root counters can cover
other processes; the JSON records membership and labels those counters, while
the RSS comparison is exclusively for the benchmark PID.

Sample current RSS and cgroup current/peak with timestamps. Emit graph/build/
persist/embedding/completed markers BEFORE each stage allocates.
VmHWM is supplementary, not an embedding-only peak. Record input bytes, nodes,
chunks, max artifact/page/buffer, elapsed time, terminal state and settings.
Separate calibration from SC-002 acceptance; also report whole-run peak.

## Interruption

Kill only an isolated fixture worker after N successful batches. Verify earlier
commits survive, remaining writes may be absent/partial, and #161 reconciles
orphan status. A normal retry is a destructive rebuild, not a resume check.

## Evidence

Write OKF test-results linked to #160, PR/SHA/spec and exact fixture. Include raw
samples/counts/commands and passing/failing/unexecuted gates. No live DocsGPT
OOM/re-ingestion was rerun by the audit; scripts alone cannot close acceptance.
