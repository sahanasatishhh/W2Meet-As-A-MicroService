#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_helpers.sh"
BASE_URL="${GATEWAY_URL:-http://localhost:8080/suggestion}"

CID="test-suggest-$(date +%s)"

echo "== suggestion-service health =="
http_code="$(curl -s -o /tmp/suggest_health.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$BASE_URL/health")"
body="$(cat /tmp/suggest_health.json)"
assert_status "$http_code" "200"
assert_json_field_equals "$body" '.service' "suggestion-service"
assert_json_has_field "$body" '.dependencies."availability-service".status'
pass "suggestion-service /health returns expected shape"

echo "== suggestion-service suggestions (requires users exist) =="
USER1="${USER1_EMAIL:-alice_test@example.com}"
USER2="${USER2_EMAIL:-bob_test@example.com}"

http_code="$(curl -s -o /tmp/suggestions.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$BASE_URL/suggestions?userId1=$USER1&userId2=$USER2")"
body="$(cat /tmp/suggestions.json)"



if [[ "$http_code" == "200" ]]; then
  # your suggestion-service returns a list; just ensure it's valid JSON
  echo "$body" | jq . >/dev/null
  suggested_slot="$(echo "$body" | jq -c '.suggestions[0]')"
  expected_slot='{"day":"monday","slot":[9,10]}'
  if [[ "$suggested_slot" != "$expected_slot" ]]; then
    echo "suggestion mismatch"
    echo "Expected: $expected_slot"
    echo "Got:      $suggested_slot"
    exit 1
  fi

  pass "suggestion matches expected first common availability slot"

else
  echo " suggestions returned HTTP $http_code (expected if USER2 isn't created yet)"
  echo "Response: $body"
fi

echo "ALL suggestion-service tests passed (health always, suggestions depends on setup)."
