#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_helpers.sh"

BASE_URL="${GATEWAY_BASE_URL:-http://localhost:8080}"
CID="test-gateway-$(date +%s)"

echo "== gateway health =="
http_code="$(curl -s -o /tmp/gw_health.txt -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$BASE_URL/health")"
body="$(cat /tmp/gw_health.txt)"

# If gateway returns plain "ok"
assert_status "$http_code" "200"
if [[ "$body" != "ok" && "$body" != "OK" ]]; then
  echo "Expected gateway /health to return ok"
  echo "Got: $body"
  exit 1
fi
pass "gateway /health ok"

echo "ALL gateway tests passed."
