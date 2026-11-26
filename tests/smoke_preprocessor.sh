#!/usr/bin/env bash
# Smoke test for the Node preprocessor: it starts and serves the login page.
# Usage: bash tests/smoke_preprocessor.sh [PORT]
# Assumes `npm install` has already run in server-processing/preprocessor.
set -euo pipefail

PORT="${1:-8099}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PRE="$HERE/../server-processing/preprocessor"
cd "$PRE"

# server.js requires PORT, PRE dir and POST dir (relative to its own folder).
node server.js "$PORT" "_smoke_pre" "_smoke_post" > /tmp/preproc_smoke.log 2>&1 &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; rm -rf "$PRE/_smoke_pre" "$PRE/_smoke_post"; }
trap cleanup EXIT

for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/login" 2>/dev/null || true)
  if [ "$code" = "200" ]; then
    echo "preprocessor smoke OK: GET /login -> 200"
    exit 0
  fi
  sleep 1
done

echo "preprocessor smoke FAILED: no 200 from /login within 30s"
echo "--- server log ---"
cat /tmp/preproc_smoke.log || true
exit 1
