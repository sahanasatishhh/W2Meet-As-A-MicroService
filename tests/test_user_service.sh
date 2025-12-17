#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_helpers.sh"

BASE_URL="${GATEWAY_URL:-http://localhost:8080/users}"
CID="test-user-$(date +%s)"

echo "== user-service health =="
http_code="$(curl -s -o /tmp/user_health.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$BASE_URL/health")"

body="$(cat /tmp/user_health.json)"
assert_status "$http_code" "200"
assert_json_field_equals "$body" '.service' "user-service"
assert_json_has_field "$body" '.dependencies.redis.status'
pass "user-service /health returns expected shape"

echo "== user-service create user =="
EMAIL="alice_test@example.com"
payload="$(jq -n \
  --arg email "$EMAIL" \
  --arg pref "first" \
  --argjson av '{"monday":[9,10,11],"tuesday":[14],"wednesday":[],"thursday":[],"friday":[],"saturday":[],"sunday":[]}' \
  '{email:$email, preferences:$pref, availabilities:$av}')"

http_code="$(curl -s -o /tmp/user_create.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -H "Case-ID: $CID" \
  -d "$payload" \
  "$BASE_URL/users")"

body="$(cat /tmp/user_create.json)"
# You return 201 in docs; keep 200/201 acceptable if your code differs
if [[ "$http_code" != "201" && "$http_code" != "200" ]]; then
  echo "Expected HTTP 200/201 but got $http_code"
  echo "$body"
  exit 1
fi
assert_json_field_equals "$body" '.email' "$EMAIL"
pass "user-service POST /users works"

echo "== user-service cache-aside get =="
http_code="$(curl -s -o /tmp/user_cache.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$BASE_URL/user-avail/cache-aside?user1email=$EMAIL")"
body="$(cat /tmp/user_cache.json)"
assert_status "$http_code" "200"
assert_json_field_equals "$body" '.email' "$EMAIL"
assert_json_has_field "$body" '.availabilities.monday'
pass "user-service cache-aside endpoint returns availability"

echo "ALL user-service tests passed."
