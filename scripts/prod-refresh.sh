#!/usr/bin/env bash
#
# scripts/prod-refresh.sh -- WP-D1 (issue #111): safe production
# refresh/release mechanics for rag-foundry-universal.
#
# Encodes the manual process in DOCS/deployment/production-docker-compose.md
# (the same steps used for prod-2026-09-12, DOCS/releases/2026-09-12-prod-release.md)
# as a script. Run this ON the production host, from the repo checkout that
# is the production deployment.
#
# Usage:
#   scripts/prod-refresh.sh --ref <sha-or-tag> --release <label> --check
#   scripts/prod-refresh.sh --ref <sha-or-tag> --release <label> --deploy
#
#   --ref REF        Git SHA or tag to deploy. Required. Always resolved to
#                     an exact commit SHA before anything else happens.
#   --release LABEL  Human-readable release label, e.g. prod-2026-09-12 for
#                     a normal release or prod-hotfix-2026-09-12-107 for an
#                     ad hoc refresh (see the "Deployment cadence" section
#                     of DOCS/deployment/production-docker-compose.md for
#                     when an ad hoc refresh is justified -- that judgment
#                     is not made by this script). Required.
#   --check          Validate through image build + provenance checks on the
#                     built images, but do not deploy (no `up -d`).
#   --deploy         Full refresh: build, `up -d`, post-deploy provenance/
#                     mount/health verification, optional smoke check, and a
#                     release-record skeleton under DOCS/releases/.
#   --repo-id ID     Optional. Repo ID to check corpus persistence and run
#                     the RAG smoke query against. Defaults to this repo's
#                     own self-ingested repo_id (the one used for every
#                     prior release's smoke check). Pass "" to skip both.
#   --smoke-query Q  Optional. Overrides the default RAG smoke query text.
#
# This script deliberately never:
#   - runs `docker compose down -v`
#   - runs database migrations
#   - triggers repo re-ingestion
#   - creates or pushes a git tag
#   - chooses which ref to deploy (the operator always passes --ref)
#   - decides whether a refresh is safe or warranted
# Those remain explicit human decisions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)

CONTAINERS=(ingestion-service vector-store-service llm-service rag-orchestrator gradio-ui)
SERVICES=(ingestion_service vector_store_service llm_service rag_orchestrator gradio)
# App services whose source dirs must never appear as a running-container
# bind mount in production (postgres is intentionally excluded -- its
# persistent volume must be present, not absent).
SOURCE_MOUNT_MARKERS=(
  "/app/ingestion_service/src"
  "/app/vector_store_service/src"
  "/app/llm_service/src"
  "/app/rag_orchestrator/src"
  "/app/shared"
)
POSTGRES_MOUNT_MARKER="./volumes/ingestion-db:/var/lib/postgresql/data"

HEALTH_ENDPOINTS=(
  "http://localhost:8001/health"
  "http://localhost:8002/health"
  "http://localhost:8003/health"
  "http://localhost:8004/health"
  "http://localhost:7860"
)

DEFAULT_REPO_ID="f7641840-ba13-5f9d-9ae6-87e1f924709d"
DEFAULT_SMOKE_QUERY="What service handles RAG queries, and what downstream services does it call?"

REF=""
RELEASE_LABEL=""
MODE=""
REPO_ID="$DEFAULT_REPO_ID"
SMOKE_QUERY="$DEFAULT_SMOKE_QUERY"

log()  { printf '[prod-refresh] %s\n' "$*"; }
fail() { printf '[prod-refresh] FAIL: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --ref) REF="$2"; shift 2 ;;
      --release) RELEASE_LABEL="$2"; shift 2 ;;
      --check) MODE="check"; shift ;;
      --deploy) MODE="deploy"; shift ;;
      --repo-id) REPO_ID="$2"; shift 2 ;;
      --smoke-query) SMOKE_QUERY="$2"; shift 2 ;;
      -h|--help) usage 0 ;;
      *) fail "Unknown argument: $1 (use --help)" ;;
    esac
  done
  [[ -n "$REF" ]] || fail "--ref is required"
  [[ -n "$RELEASE_LABEL" ]] || fail "--release is required"
  [[ -n "$MODE" ]] || fail "one of --check or --deploy is required"
}

compose() {
  (cd "$REPO_ROOT" && docker compose "${COMPOSE_FILES[@]}" "$@")
}

# --- Step 1: refuse a dirty working tree -----------------------------------
require_clean_tree() {
  local dirty
  dirty="$(cd "$REPO_ROOT" && git status --short)"
  [[ -z "$dirty" ]] || fail "working tree is not clean -- commit, stash, or discard changes first:
$dirty"
  log "working tree is clean"
}

# --- Steps 2-4: fetch, resolve, checkout the exact ref ----------------------
resolve_and_checkout_ref() {
  (cd "$REPO_ROOT" && git fetch --tags origin)
  local sha
  sha="$(cd "$REPO_ROOT" && git rev-parse --verify "${REF}^{commit}")" \
    || fail "could not resolve --ref '$REF' to a commit after fetching"
  log "resolved --ref '$REF' -> $sha"
  (cd "$REPO_ROOT" && git checkout --detach "$sha")
  GIT_SHA="$sha"
}

# --- Step 5: release metadata ------------------------------------------------
set_release_metadata() {
  export GIT_SHA
  export BUILD_DATE
  export RELEASE_VERSION="$RELEASE_LABEL"
  BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  export BUILD_DATE
  log "GIT_SHA=$GIT_SHA BUILD_DATE=$BUILD_DATE RELEASE_VERSION=$RELEASE_VERSION"
}

# --- Steps 6-8: render config, check no source mounts, check pg mount ------
# Pure checks (no docker calls) so they're testable in isolation --
# scripts/test-prod-refresh.sh exercises these directly with synthetic input.
assert_no_source_mounts() {
  local text="$1" label="$2" marker
  for marker in "${SOURCE_MOUNT_MARKERS[@]}"; do
    if grep -qF "$marker" <<<"$text"; then
      fail "$label still contains a source bind mount target: $marker"
    fi
  done
}

assert_postgres_mount_present() {
  local text="$1" label="$2"
  if ! grep -qF "$POSTGRES_MOUNT_MARKER" <<<"$text"; then
    fail "$label is missing the persistent Postgres mount ($POSTGRES_MOUNT_MARKER)"
  fi
}

render_and_check_config() {
  log "rendering effective compose config"
  RENDERED_CONFIG="$(compose config)"

  assert_no_source_mounts "$RENDERED_CONFIG" "rendered prod config"
  log "no application source bind mounts in rendered config"

  assert_postgres_mount_present "$RENDERED_CONFIG" "rendered prod config"
  log "persistent Postgres mount present in rendered config"
}

# --- Step 9: build ------------------------------------------------------------
build_images() {
  log "building prod images"
  compose build
}

# --- Step 10: verify OCI revision labels on the freshly built images -------
verify_built_image_labels() {
  log "verifying OCI revision labels on built images"
  local svc image_id label
  for svc in "${SERVICES[@]}"; do
    image_id="$(compose images -q "$svc")"
    [[ -n "$image_id" ]] || fail "could not find a built image ID for service $svc"
    label="$(docker image inspect "$image_id" \
      --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')"
    [[ "$label" == "$GIT_SHA" ]] \
      || fail "$svc built image revision label '$label' != requested GIT_SHA '$GIT_SHA'"
    log "  $svc: image $image_id revision=$label (matches)"
  done
}

# --- Step 11: deploy ----------------------------------------------------------
deploy() {
  log "deploying: docker compose up -d"
  compose up -d
}

# --- Step 12: verify running image revision labels --------------------------
verify_running_image_labels() {
  log "verifying OCI revision labels on running containers"
  local name image_id label
  for name in "${CONTAINERS[@]}"; do
    image_id="$(docker inspect "$name" --format '{{.Image}}')"
    label="$(docker image inspect "$image_id" \
      --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')"
    [[ "$label" == "$GIT_SHA" ]] \
      || fail "$name running image revision label '$label' != requested GIT_SHA '$GIT_SHA'"
    log "  $name: image $image_id revision=$label (matches)"
  done
}

# --- Step 13: verify no source mounts on running containers -----------------
verify_no_running_source_mounts() {
  log "verifying no source bind mounts on running containers"
  local name mounts
  for name in "${CONTAINERS[@]}"; do
    mounts="$(docker inspect "$name" --format '{{json .Mounts}}')"
    assert_no_source_mounts "$mounts" "running container $name"
  done
  log "no running container has a source bind mount"
}

# --- Step 14: health checks --------------------------------------------------
health_check_all() {
  log "checking service health endpoints"
  local url attempt status
  for url in "${HEALTH_ENDPOINTS[@]}"; do
    status=""
    for attempt in 1 2 3 4 5; do
      status="$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$url" || true)"
      [[ "$status" == "200" ]] && break
      sleep 3
    done
    [[ "$status" == "200" ]] || fail "$url did not return 200 (last status: $status)"
    log "  $url -> 200"
  done
}

# --- Step 15: corpus persistence check --------------------------------------
# Uses env vars + stdin (not string interpolation into Python source) so
# nothing in REPO_ID/the HTTP response body can break out of a quoted
# Python literal.
verify_corpus_present() {
  [[ -n "$REPO_ID" ]] || { log "no --repo-id given, skipping corpus check"; CORPUS_CHECK="skipped (no repo-id)"; return; }
  log "verifying corpus for repo_id=$REPO_ID is still present"
  local body status
  body="$(curl -s -m 15 "http://localhost:8001/v1/repos")" || fail "failed to reach ingestion_service /v1/repos"
  status="$(REPO_ID="$REPO_ID" python3 -c '
import json, os, sys
repos = json.load(sys.stdin)
target = os.environ["REPO_ID"]
for r in repos:
    if r.get("id") == target:
        print(r.get("status", "unknown"))
        sys.exit(0)
print("not_found")
' <<<"$body" 2>/dev/null || echo "unknown")"
  [[ "$status" == "completed" ]] || fail "repo_id $REPO_ID is not present/completed (status: $status)"
  log "  repo_id $REPO_ID status=completed"
  CORPUS_CHECK="pass (status=completed)"
}

# --- Step 16: RAG smoke query -------------------------------------------------
run_smoke_query() {
  [[ -n "$REPO_ID" ]] || { log "no --repo-id given, skipping RAG smoke query"; SMOKE_RESULT="skipped (no repo-id)"; return; }
  log "running RAG smoke query against repo_id=$REPO_ID"
  local payload response
  payload="$(REPO_ID="$REPO_ID" SMOKE_QUERY="$SMOKE_QUERY" python3 -c '
import json, os
print(json.dumps({"query": os.environ["SMOKE_QUERY"], "repo_id": os.environ["REPO_ID"]}))
')"
  response="$(curl -s -m 60 -X POST "http://localhost:8004/v1/rag" \
    -H "Content-Type: application/json" -d "$payload")" \
    || fail "RAG smoke query request failed"
  if grep -q '"answer"' <<<"$response"; then
    log "  RAG smoke query returned an answer"
    SMOKE_RESULT="pass"
  else
    fail "RAG smoke query did not return an answer: $response"
  fi
}

# --- Step 17: release-record skeleton ---------------------------------------
write_release_summary() {
  local out_path="$REPO_ROOT/DOCS/releases/$(date -u +%Y-%m-%d)-${RELEASE_LABEL}.md"
  log "writing release-record skeleton to $out_path"
  mkdir -p "$(dirname "$out_path")"
  cat > "$out_path" <<SUMMARY
---
title: "Production Release Record: ${RELEASE_LABEL}"
date: $(date -u +%Y-%m-%d)
type: release-record
status: complete
tags: [release, production, provenance]
related:
  - "[Production Docker Compose Release Process](/DOCS/deployment/production-docker-compose.md)"
---

# ${RELEASE_LABEL}

Generated by \`scripts/prod-refresh.sh --deploy\` (WP-D1, issue #111). Fields marked **FILL IN**
require human judgment and were not determined by the script.

## Identity

- Release: ${RELEASE_LABEL}
- Approved runtime SHA: ${GIT_SHA}
- Approved tag/ref: ${REF}
- Build date: ${BUILD_DATE}
- Operator: **FILL IN**

## Release classification

- DB migration: **FILL IN**
- DB backup: **FILL IN**
- Repo re-ingestion: **FILL IN**
- Graph rebuild: **FILL IN**
- Vector re-embedding: **FILL IN**
- Config change: **FILL IN**
- Cadence: **FILL IN** (normal release / ad hoc refresh -- see "Deployment cadence" in
  DOCS/deployment/production-docker-compose.md; if ad hoc, name the qualifying gate criterion and
  the issue it fixes)

## Deployment validation (script-verified)

- Rendered Compose config checked: pass
- Application source bind mounts absent (rendered config): pass
- Application source bind mounts absent (running containers): pass
- Postgres persistent storage present: pass
- Build completed: pass
- Built-image OCI revision labels match ${GIT_SHA}: pass
- Running-container OCI revision labels match ${GIT_SHA}: pass
- Health checks: pass (${HEALTH_ENDPOINTS[*]})
- Corpus persistence check: ${CORPUS_CHECK:-not run}
- RAG smoke query: ${SMOKE_RESULT:-not run}

## RAG smoke query

- Repo ID: ${REPO_ID:-none}
- Query: ${SMOKE_QUERY}
- Result: ${SMOKE_RESULT:-not run}

## Rollback point

- Rollback SHA/tag: **FILL IN** (the previous production SHA, recorded before this refresh)
- Rollback command tested: no
- DB restore required for rollback: **FILL IN**
- Notes: **FILL IN**
SUMMARY
  log "release-record skeleton written -- fill in the FILL IN fields before considering this release fully recorded"
}

main() {
  parse_args "$@"

  require_clean_tree
  resolve_and_checkout_ref
  set_release_metadata
  render_and_check_config
  build_images
  verify_built_image_labels

  if [[ "$MODE" == "check" ]]; then
    log "--check complete: ref $GIT_SHA is buildable and provenance-clean. Not deployed."
    exit 0
  fi

  deploy
  verify_running_image_labels
  verify_no_running_source_mounts
  health_check_all
  verify_corpus_present
  run_smoke_query
  write_release_summary

  log "--deploy complete: $RELEASE_LABEL ($GIT_SHA) is live and verified."
}

# Allow this script to be sourced (e.g. by scripts/test-prod-refresh.sh)
# without running main -- only run main when executed directly.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
