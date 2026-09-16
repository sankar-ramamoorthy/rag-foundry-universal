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
