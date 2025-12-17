#!/usr/bin/env bash
set -euo pipefail

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing dependency: $1"
    exit 1
  }
}

# Use jq for reliable JSON checks
require jq
require curl

assert_status() {
  local actual="$1"
  local expected="$2"
  if [[ "$actual" != "$expected" ]]; then
    echo "Expected HTTP $expected but got $actual"
    exit 1
  fi
}

assert_json_field_equals() {
  local json="$1"
  local jq_path="$2"
  local expected="$3"
  local actual
  actual="$(echo "$json" | jq -r "$jq_path")"
  if [[ "$actual" != "$expected" ]]; then
    echo "Expected $jq_path == '$expected' but got '$actual'"
    echo "Response JSON: $json"
    exit 1
  fi
}

assert_json_has_field() {
  local json="$1"
  local jq_path="$2"
  echo "$json" | jq -e "$jq_path" >/dev/null || {
    echo "Expected JSON to have field at $jq_path"
    echo "Response JSON: $json"
    exit 1
  }
}

pass() {
  echo " got correct $1"
}
