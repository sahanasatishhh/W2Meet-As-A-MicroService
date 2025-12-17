#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_helpers.sh"

GATEWAY="${GATEWAY_URL:-http://localhost:8080}"
AVAIL_BASE="$GATEWAY/availability"
USER_BASE="$GATEWAY/users"

CID="test-avail-$(date +%s)"
USER1="${USER1_EMAIL:-alice_test@example.com}"
USER2="${USER2_EMAIL:-bob_test@example.com}"

make_user_payload() {
  local email="$1"
  jq -n \
    --arg email "$email" \
    --arg pref "first" \
    --argjson av '{"monday":[9,10,11],"tuesday":[14],"wednesday":[],"thursday":[],"friday":[],"saturday":[],"sunday":[]}' \
    '{email:$email, preferences:$pref, availabilities:$av}'
}

create_user() {
  local email="$1"
  local payload
  payload="$(make_user_payload "$email")"

  http_code="$(curl -s -o /tmp/user_create.json -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -H "Case-ID: $CID" \
    -d "$payload" \
    "$USER_BASE/users")"

  body="$(cat /tmp/user_create.json)"

  # Accept 200/201. If your service returns 409 for "already exists", accept that too.
  if [[ "$http_code" == "200" || "$http_code" == "201" || "$http_code" == "409" ]]; then
    return 0
  fi

  echo "❌ Failed creating user: $email (HTTP $http_code)"
  echo "$body"
  exit 1
}

echo "== availability-service health =="
http_code="$(curl -s -o /tmp/avail_health.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$AVAIL_BASE/health")"
body="$(cat /tmp/avail_health.json)"

assert_status "$http_code" "200"
assert_json_field_equals "$body" '.service' "availability-service"
pass "availability-service /health OK"

echo "== ensure users exist (via gateway user-service) =="
create_user "$USER1"
create_user "$USER2"
pass "users exist (created or already present)"

echo "== availability-service common availability =="
http_code="$(curl -s -o /tmp/common.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$AVAIL_BASE/availabilities?userId1=$USER1&userId2=$USER2")"
body="$(cat /tmp/common.json)"

if [[ "$http_code" != "200" ]]; then
  echo " Expected HTTP 200 from common availability, got $http_code"
  echo "$body"
  exit 1
fi

# Your script had ".common_availabilitiy" (typo). Use the exact field your API returns.
# If your API truly returns "common_availabilitiy", keep it. Otherwise fix here.
assert_json_has_field "$body" '.common_availabilities'
pass "common availability returned expected field"

# === Assert common availability values ===
# This expected object MUST match what your created users produce.
expected_common="$(jq -n '{
  monday: [9,10,11],
  tuesday: [14],
  wednesday: [],
  thursday: [],
  friday: [],
  saturday: [],
  sunday: []
}')"

actual_common="$(echo "$body" | jq '.common_availabilities')"

# Compare day-by-day (better error messages than full-object compare)
for day in monday tuesday wednesday thursday friday saturday sunday; do
  expected="$(echo "$expected_common" | jq -c ".${day}")"
  actual="$(echo "$actual_common" | jq -c ".${day}")"

  if [[ "$expected" != "$actual" ]]; then
    echo " Common availability mismatch on $day"
    echo "Expected: $expected"
    echo "Actual:   $actual"
    exit 1
  fi
done

pass "common availability matches expected values"

echo "ALL availability-service tests passed."
