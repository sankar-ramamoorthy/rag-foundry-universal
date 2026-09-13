#!/usr/bin/env bash
#
# scripts/test-prod-refresh.sh -- lightweight self-test for
# scripts/prod-refresh.sh (WP-D1, issue #111).
#
# No Docker/Compose/DB required: exercises argument parsing and the pure
# mount-marker checks in isolation by sourcing prod-refresh.sh (its `main`
# does not run when sourced -- see the guard at the bottom of that file).
# Full end-to-end behavior (build/deploy/health-checks) still needs to be
# exercised by hand against a real host, per
# DOCS/deployment/production-docker-compose.md.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/prod-refresh.sh"

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

# --- source-mount / postgres-mount detection --------------------------------

DEV_MOUNT_SNIPPET='      - ./ingestion_service/src:/app/ingestion_service/src'
CLEAN_SNIPPET='    volumes: []'
PG_MOUNT_SNIPPET='      - ./volumes/ingestion-db:/var/lib/postgresql/data'

expect_fail "detects a leaked source bind mount" \
  bash -c "source '$TARGET'; assert_no_source_mounts '$DEV_MOUNT_SNIPPET' 'test config'"

expect_success "clean config has no source bind mounts" \
  bash -c "source '$TARGET'; assert_no_source_mounts '$CLEAN_SNIPPET' 'test config'"

expect_fail "detects a missing Postgres mount" \
  bash -c "source '$TARGET'; assert_postgres_mount_present '$CLEAN_SNIPPET' 'test config'"

expect_success "detects a present Postgres mount" \
  bash -c "source '$TARGET'; assert_postgres_mount_present '$PG_MOUNT_SNIPPET' 'test config'"

echo
echo "$pass_count passed, $fail_count failed"
[[ "$fail_count" -eq 0 ]]
