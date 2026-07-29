#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./test_toolbox_endpoint.sh "<toolbox-mcp-endpoint>"

Environment variables:
  TOOLBOX_ENDPOINT   Toolbox MCP endpoint, or pass as first argument
  TOKEN_SCOPE        Token scope for Toolbox endpoint
                     Default: https://ai.azure.com/.default

Example:
  export TOOLBOX_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<name>/versions/<version>/mcp?api-version=v1"
  ./test_toolbox_endpoint.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

TOOLBOX_ENDPOINT="${1:-${TOOLBOX_ENDPOINT:-}}"
TOKEN_SCOPE="${TOKEN_SCOPE:-}"

if [[ -z "${TOOLBOX_ENDPOINT}" ]]; then
  echo "TOOLBOX_ENDPOINT is required." >&2
  usage >&2
  exit 1
fi

command -v az >/dev/null 2>&1 || {
  echo "az is required." >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || {
  echo "curl is required." >&2
  exit 1
}

TOKEN="$(az account get-access-token --resource "${TOKEN_SCOPE}" --query accessToken -o tsv 2>/dev/null || true)"
if [[ -z "${TOKEN}" ]]; then
  echo "Failed to acquire an access token for scope '${TOKEN_SCOPE}'. Run 'az login' first." >&2
  exit 1
fi


TMP_DIR="./.toolbox-test-$$"
mkdir -p "$TMP_DIR"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

request() {
  local name="$1"
  local body="$2"
  local session_id="${3:-}"

  local headers_file="${TMP_DIR}/${name}.headers"
  local body_file="${TMP_DIR}/${name}.body"

  local -a curl_args=(
    -sS
    -D "${headers_file}"
    -o "${body_file}"
    -w '%{http_code}'
    -X POST "${TOOLBOX_ENDPOINT}"
    -H "Authorization: Bearer ${TOKEN}"
    -H "Accept: application/json, text/event-stream"
    -H "Content-Type: application/json"
  )

  if [[ -n "${session_id}" ]]; then
    curl_args+=( -H "mcp-session-id: ${session_id}" )
  fi

  curl_args+=( --data-binary "${body}" )

  local status
  status="$(curl "${curl_args[@]}")"

  echo "=== ${name} (HTTP ${status}) ==="
  echo
  echo "Response body:"
  cat "${body_file}"
  echo
  echo
  echo "Response headers:"
  cat "${headers_file}"
  echo
  echo
}

echo "Using toolbox endpoint:"
echo "${TOOLBOX_ENDPOINT}"
echo

echo "Token acquired for scope: ${TOKEN_SCOPE}"
echo

INITIALIZE_BODY='{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"toolbox-test","version":"1.0"}}}'
request "initialize" "${INITIALIZE_BODY}" ""

SESSION_ID="$(
  awk 'BEGIN{IGNORECASE=1} /^mcp-session-id:/ {
    sub(/^mcp-session-id:[[:space:]]*/, "", $0);
    print;
    exit
  }' "${TMP_DIR}/initialize.headers" | tr -d '\r'
)"

if [[ -n "${SESSION_ID}" ]]; then
  echo "Session ID: ${SESSION_ID}"
  echo
else
  echo "No mcp-session-id header returned."
  echo
fi

NOTIFY_BODY='{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
request "notifications_initialized" "${NOTIFY_BODY}" "${SESSION_ID}"

LIST_BODY='{"jsonrpc":"2.0","id":"2","method":"tools/list","params":{}}'
request "tools_list" "${LIST_BODY}" "${SESSION_ID}"
