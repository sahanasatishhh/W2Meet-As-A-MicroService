#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_helpers.sh"

GATEWAY="${GATEWAY_URL:-http://localhost:8080}"
CID="test-errors-$(date +%s)"

NON_EXISTENT="ghost_user_$(date +%s)@example.com"
VALID_USER="${USER1_EMAIL:-alice_test@example.com}"

echo "== ERROR HANDLING TESTS =="

########################################
# 1️ User-Service: get non-existent user
########################################
echo "== user-service: fetch non-existent user =="

http_code="$(curl -s -o /tmp/user_404.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$GATEWAY/users/user-avail/cache_aside/$NON_EXISTENT")"

body="$(cat /tmp/user_404.json)"

assert_status "$http_code" "404"
assert_json_has_field "$body" '.detail'
pass "user-service returns 404 for non-existent user"

##########################################################
# 2️ Availability-Service: one valid + one missing user
##########################################################
echo "== availability-service: one user missing =="

http_code="$(curl -s -o /tmp/avail_404.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$GATEWAY/availability/availabilities?userId1=$VALID_USER&userId2=$NON_EXISTENT")"

body="$(cat /tmp/avail_404.json)"

assert_status "$http_code" "404"
assert_json_field_equals "$body" '.detail[0].msg' "One or both users not found"
pass "availability-service handles missing user correctly"

##########################################################
# 3️Suggestion-Service: one valid + one missing user
##########################################################
echo "== suggestion-service: one user missing =="

http_code="$(curl -s -o /tmp/suggest_404.json -w "%{http_code}" \
  -H "Case-ID: $CID" \
  "$GATEWAY/suggestion/suggestions?userId1=$VALID_USER&userId2=$NON_EXISTENT")"

body="$(cat /tmp/suggest_404.json)"

assert_status "$http_code" "404"
assert_json_field_equals "$body" '.detail[0].msg' "One or both users not found"
pass "suggestion-service propagates error correctly"

########################################
echo "ALL error-handling tests passed ✔️"
