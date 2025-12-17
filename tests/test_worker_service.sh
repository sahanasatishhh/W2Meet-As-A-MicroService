#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_helpers.sh"

BASE_URL="${GATEWAY_URL:-http://localhost:8080/worker}"
CID="test-worker-$(date +%s)"

echo "== worker-service health =="
http_code="$(curl -s -o /tmp/worker_health.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$BASE_URL/health")"
body="$(cat /tmp/worker_health.json)"
assert_status "$http_code" "200"
assert_json_field_equals "$body" '.service' "worker-service"
pass "worker-service /health ok"

echo "== worker-service enqueue job =="
payload="$(jq -n \
  --arg u1 "${USER1_EMAIL:-alice_test@example.com}" \
  --arg u2 "${USER2_EMAIL:-bob_test@example.com}" \
  --arg pref "first" \
  '{userId1:$u1, userId2:$u2, preference:$pref}')"

http_code="$(curl -s -o /tmp/worker_task.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -H "Case-ID: $CID" \
  -d "$payload" \
  "$BASE_URL/tasks")"

body="$(cat /tmp/worker_task.json)"
# enqueue should be 202
assert_status "$http_code" "202"
assert_json_field_equals "$body" '.status' "enqueued"
assert_json_has_field "$body" '.job_id'
pass "worker-service POST /tasks enqueues job"

echo "NOTE: check worker logs for JOB_DONE printing suggestion result."
echo "ALL worker-service tests passed."
