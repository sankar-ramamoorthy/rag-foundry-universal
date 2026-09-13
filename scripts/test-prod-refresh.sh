#!/usr/bin/env bash
#
# scripts/test-prod-refresh.sh -- lightweight self-test for
# scripts/prod-refresh.sh (WP-D1, issue #111).
#
# No Docker/Compose/DB required: exercises argument parsing and the pure,
# structured-JSON mount checks in isolation by sourcing prod-refresh.sh (its
# `main`/re-exec do not run when sourced -- both are guarded by the
# BASH_SOURCE-vs-$0 check at the bottom of that file). Full end-to-end
# behavior (build/deploy/health-checks) still needs to be exercised by hand
# against a real host, per DOCS/deployment/production-docker-compose.md.

set -uo pipefail

# On Git Bash/MSYS (Windows), any string that looks like a Unix absolute
# path gets silently rewritten (e.g. "/var/lib/postgresql/data" ->
# "C:/Program Files/Git/var/lib/postgresql/data") before it reaches a native
# .exe like python3 -- this affects nothing on the real Linux production
# host prod-refresh.sh actually runs on, but would otherwise break these
# tests when run locally on Windows.
export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/prod-refresh.sh"
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

pass_count=0
fail_count=0

expect_fail() {
  local desc="$1"; shift
  if ( "$@" ) >/tmp/prod-refresh-test-out 2>&1; then
    echo "FAIL (expected failure, got success): $desc"
    fail_count=$((fail_count + 1))
  else
    echo "ok: $desc"
    pass_count=$((pass_count + 1))
  fi
}

expect_success() {
  local desc="$1"; shift
  if ( "$@" ) >/tmp/prod-refresh-test-out 2>&1; then
    echo "ok: $desc"
    pass_count=$((pass_count + 1))
  else
    echo "FAIL (expected success, got failure): $desc"
    cat /tmp/prod-refresh-test-out
    fail_count=$((fail_count + 1))
  fi
}

# --- argument parsing -------------------------------------------------------

expect_fail "missing --ref is rejected" \
  bash -c "source '$TARGET'; parse_args --release x --check"

expect_fail "missing --release is rejected" \
  bash -c "source '$TARGET'; parse_args --ref abc123 --check"

expect_fail "missing --check/--deploy is rejected" \
  bash -c "source '$TARGET'; parse_args --ref abc123 --release x"

expect_fail "unknown flag is rejected" \
  bash -c "source '$TARGET'; parse_args --ref abc123 --release x --check --bogus"

expect_success "valid --check args are accepted" \
  bash -c "source '$TARGET'; parse_args --ref abc123 --release x --check"

expect_success "valid --deploy args are accepted" \
  bash -c "source '$TARGET'; parse_args --ref abc123 --release x --deploy"

expect_success "--record-dir override is accepted" \
  bash -c "source '$TARGET'; parse_args --ref abc123 --release x --check --record-dir /tmp/wherever"

# --- structured mount checks (docker compose config --format json shape) ---
# These fixtures mirror the real `docker compose config --format json`
# output shape confirmed live against this repo's own docker-compose.prod.yml
# (app services -> volumes: null after `!override []`; postgres -> one bind
# mount with a host-specific absolute source path and a fixed target).

cat > "$FIXTURE_DIR/compose_clean.json" <<'JSON'
{
  "services": {
    "rag_orchestrator": {"volumes": null},
    "gradio": {"volumes": null},
    "postgres": {
      "volumes": [
        {"type": "bind", "source": "/media/sankar/llm/rag/rag-foundry-universal/volumes/ingestion-db", "target": "/var/lib/postgresql/data", "bind": {}}
      ]
    }
  }
}
JSON

cat > "$FIXTURE_DIR/compose_leaked_app_mount.json" <<'JSON'
{
  "services": {
    "rag_orchestrator": {
      "volumes": [
        {"type": "bind", "source": "./rag_orchestrator/src", "target": "/app/rag_orchestrator/src", "bind": {}}
      ]
    },
    "postgres": {
      "volumes": [
        {"type": "bind", "source": "/media/sankar/llm/rag/rag-foundry-universal/volumes/ingestion-db", "target": "/var/lib/postgresql/data", "bind": {}}
      ]
    }
  }
}
JSON

cat > "$FIXTURE_DIR/compose_missing_postgres_mount.json" <<'JSON'
{
  "services": {
    "rag_orchestrator": {"volumes": null},
    "postgres": {"volumes": null}
  }
}
JSON

cat > "$FIXTURE_DIR/mounts_clean.json" <<'JSON'
[{"Destination": "/var/lib/postgresql/data"}]
JSON

cat > "$FIXTURE_DIR/mounts_app.json" <<'JSON'
[{"Destination": "/app/rag_orchestrator/src"}]
JSON

expect_success "clean compose config (long-form pg mount, absolute host source) passes" \
  bash -c "source '$TARGET'; check_mounts_json compose 'test' < '$FIXTURE_DIR/compose_clean.json'"

expect_fail "compose config with a leaked /app bind mount fails" \
  bash -c "source '$TARGET'; check_mounts_json compose 'test' < '$FIXTURE_DIR/compose_leaked_app_mount.json'"

expect_fail "compose config missing the Postgres mount fails" \
  bash -c "source '$TARGET'; check_mounts_json compose 'test' < '$FIXTURE_DIR/compose_missing_postgres_mount.json'"

expect_success "clean running-container mounts pass" \
  bash -c "source '$TARGET'; check_mounts_json mounts 'test' < '$FIXTURE_DIR/mounts_clean.json'"

expect_fail "running-container mount targeting /app fails (not in any hardcoded list)" \
  bash -c "source '$TARGET'; check_mounts_json mounts 'test' < '$FIXTURE_DIR/mounts_app.json'"

# --- built-image lookup must never depend on container state ---------------
# Found live: `docker compose images -q <svc>` looks up the image via each
# service's CONTAINER, so it fails ("failed to retrieve image for container
# ...") or reports the wrong (old) image whenever a previous release's
# container is still running for that service -- exactly the state every
# real --check/--deploy run is in right before `up -d`. The fix resolves the
# image reference from parsed compose config instead; these tests pin that
# down as a pure function, plus a regression tripwire so the container-
# dependent lookup can't quietly come back.

expect_success "compose_image_name is pure string composition" \
  bash -c "source '$TARGET'; [[ \"\$(compose_image_name rag-foundry-universal rag_orchestrator)\" == 'rag-foundry-universal-rag_orchestrator' ]]"

expect_fail "regression tripwire: 'compose images' (container-dependent lookup) must not reappear in code" \
  bash -c "grep -vE '^[[:space:]]*#' '$TARGET' | grep -qE 'compose images'"

# --- health checks must be a time budget, not a fixed attempt count --------
# Found live: 5 attempts x 3s (15s total, regardless of --health-timeout-
# seconds) aborted a --deploy run on a transient readiness race, even though
# the deploy itself had already succeeded. Verify the retry loop actually
# waits close to the configured budget before giving up, against a port
# nothing listens on (curl fails fast, so this stays quick to run).

start_ts=$(date +%s)
bash -c "
  source '$TARGET'
  HEALTH_ENDPOINTS=(http://127.0.0.1:1/health)
  HEALTH_TIMEOUT_SECONDS=3
  HEALTH_POLL_INTERVAL_SECONDS=1
  health_check_all
" >/tmp/prod-refresh-test-out 2>&1
health_check_exit=$?
elapsed_ts=$(( $(date +%s) - start_ts ))

if [[ "$health_check_exit" -ne 0 && "$elapsed_ts" -ge 2 ]]; then
  echo "ok: health_check_all respects HEALTH_TIMEOUT_SECONDS as a time budget (waited ${elapsed_ts}s, configured 3s)"
  pass_count=$((pass_count + 1))
else
  echo "FAIL: health_check_all did not behave as a time-budgeted retry (exit=$health_check_exit, elapsed=${elapsed_ts}s)"
  cat /tmp/prod-refresh-test-out
  fail_count=$((fail_count + 1))
fi

# --- release record must survive a post-deploy failure (on_exit trap) ------
# Found live: write_release_summary was only called at the very end of
# main()'s happy path, so a failure anywhere in post-deploy verification
# (like the health-check race above) meant no record was written at all,
# discarding evidence that build + provenance checks had already passed.

RECORDS_DIR="$FIXTURE_DIR/records"
expected_record="$RECORDS_DIR/$(date -u +%Y-%m-%d)-test-release.md"
bash -c "
  source '$TARGET'
  RECORD_DIR='$RECORDS_DIR'
  GIT_SHA=deadbeef
  REF=main
  RELEASE_LABEL=test-release
  BUILD_DATE=2026-01-01T00:00:00Z
  PREV_GIT_SHA=oldsha
  CONFIG_CHECK=pass
  BUILD_CHECK=pass
  BUILT_LABELS_CHECK=pass
  RUNNING_LABELS_CHECK=pass
  RUNNING_MOUNTS_CHECK=pass
  DEPLOY_STARTED=1
  trap on_exit EXIT
  fail 'simulated post-deploy failure (e.g. a health-check timing race)'
" >/tmp/prod-refresh-test-out 2>&1

if [[ -f "$expected_record" ]] && grep -q "status: incomplete" "$expected_record" \
  && grep -q "Health checks: not run" "$expected_record"; then
  echo "ok: on_exit writes a release record (marked incomplete) even after a simulated post-deploy failure"
  pass_count=$((pass_count + 1))
else
  echo "FAIL: expected an 'incomplete' release record at $expected_record after a simulated failure"
  cat /tmp/prod-refresh-test-out
  fail_count=$((fail_count + 1))
fi

echo
echo "$pass_count passed, $fail_count failed"
[[ "$fail_count" -eq 0 ]]
