# Delivery plan: production correctness

Tracking issues: #160, #161, #166-#171
Spec: [spec.md](./spec.md)
Current execution: [HANDOFF.md](./HANDOFF.md)

## Sequence and branch boundaries

1. Amend/merge existing documentation PR #164 for #160, adding the audit,
   corrected 004 contracts and this issue-backed roadmap. Do not close #160.
2. Implement WP-R1 as its own branch/PR with tests and bounded-buffer evidence.
3. Implement WP-R2 and WP-R3 on separate branches/PRs; agree worker/repository
   ownership interfaces before either is merged. Test them together before
   release. Keep #144 linked to the explicit rebuild-state contract.
4. Implement WP-R5 snapshot/cache identity before quality evaluation so evidence
   can be pinned. Implement WP-R4 with payload tests and clean evaluation.
5. WP-R6 health/provenance and WP-R7 I/O isolation can ship independently while
   higher-risk work is developing; the sequence is not a strict dependency chain.
6. WP-R8 verifies the composed, merged system. Code completion and target-Linux
   acceptance are tracked independently; retain open issues for unmet gates.

September 17 addition: #176 tracks post-delete ANN recall failure discovered
by real #160 benchmark churn. Diagnose with exact-search/maintenance controls,
then fix in a separate WP-R3/R4 PR; include post-delete query availability in
WP-R8. [Plan and acceptance](./issues/post-delete-ann.md).

Every implementation branch starts from updated main after prior PR merge.
Avoid giant omnibus commits. A PR body states the concrete failure, final
behavior, issue, validation and remaining deployment gates; no AI attribution.
Do not auto-close an issue with unexecuted mandatory acceptance criteria.

## Contract design before code

WP-R2/R3: use one coherent database-backed ownership approach. Full-operation
repository exclusivity must cover graph commit, embedding and final status;
delete acquires the same guard. Durable repo_id on attempts survives node
deletion and supports admin state for failed/pre-graph attempts. Migration
backfill uses current nodes and derivable source metadata; unresolved historical
identity is disclosed, never guessed. Graph/request deletion is one DB
transaction after idempotent vector cleanup; no transaction spans remote calls.

WP-R4: keep stored chunk ordinal distinct from fetch position. Add an explicit
query-aware, generation-scoped passage-fetch contract with deterministic ties;
seed artifacts can receive supplementary evidence. Context assembly returns
selected chunks and text once, from which sources and manifest derive. Budget
accounts for code/text and labels plus prompt/output reserves. Use conservative
deterministic accounting unless the active model's tokenizer is available; do
not mislabel whitespace words as tokens. Selection changes require evaluation.

WP-R5: resolved source SHA is stored at ingestion; local dirty worktrees need a
fingerprint/explicit dirty provenance. Cache keys include repo_id+generation,
with bounded eviction; generation changes during query cause retry/failure,
not silent combination. Include runtime revision in query/evaluation evidence.

WP-R6: executable CMD healthchecks, correct internal ports, finite timeouts.
Read-only version API consumes image build variables, returning unknown for
unlabeled development builds. OCI labels remain required release evidence.

WP-R7: synchronous handlers use a bounded framework worker pool; mixed async
pipelines explicitly offload blocking embedding/graph/rerank work. Separate
provider deadlines from outer request deadlines. Saturation/cancellation tests
must prove bounded work rather than merely that one task moved to a thread.

## Verification commands and environments

Root: uv sync --frozen; uv run ruff check .; uv run pyright .
Use the ROOT environment for all service tests, matching CI:
from ingestion_service: ../.venv/bin/python -m pytest -m unit -q
from vector_store_service: ../.venv/bin/python -m pytest -m unit -q
from rag_orchestrator: ../.venv/bin/python -m pytest -q
from llm_service: ../.venv/bin/python -m pytest tests/ -q
Windows substitutes ../.venv/Scripts/python.exe.

Database tests need isolated PostgreSQL+pgvector and applied migrations; add
new tests explicitly to .github/workflows/ci.yml integration selection. Quality
evaluation follows DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md.
Record exact commands, SHAs, outcomes and missing evidence under DOCS/test_results.

GitHub access in this Windows session requires sandbox escalation, not new
login: gh auth status succeeds outside the sandbox. Do not log out or print
credentials. Git network/index mutations may also need escalation. Push and
merge are explicitly authorized by the user; inspect required CI first.

## Linux production boundary

Production: Tailscale 100.105.24.12, Linux, GTX 1080 Ti; no SSH. Current HTTP
health is reachable. No Docker daemon is running locally at planning time.
Do not infer container provenance, cgroup settings or successful redeployment
from health HTTP 200. Prepare concrete release scripts/commands and collect
operator results where no remote command capability exists. Use a uniquely
named isolated smoke repository; never delete/re-ingest existing user corpora
as incidental validation. Benchmark/OOM/kill tests belong in an isolated stack.
